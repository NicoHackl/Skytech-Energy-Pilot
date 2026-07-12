"""Planning-Engine: orchestriert die Erzeugung eines Kandidatenplans (Doc 07, D-041).

Ablauf: Snapshots holen → harte Grenzen + Ziele ableiten → verdichteten Kontext +
Prompt + Antwort-Schema bauen → KI-Aufruf (Single-Shot) → Plan **montieren** (EP
setzt die Metadaten plan_id/Zeiten selbst, nie das Modell) → lokal **validieren**
(`validator.py`) → in DB protokollieren (`ai_calls`, `plans`, `audit`).

V1 (D-008): Ergebnis sind reine Vorschlagswerte – kein Schreiben nach HA, keine
Übernahme durch HEMS. Provider-Fehler werden kontrolliert abgefangen; die App
blockiert nie (Iron Rule 8).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from energy_pilot.ai_provider import AIProvider
from energy_pilot.config import AddonConfig
from energy_pilot.constraints import build_constraints
from energy_pilot.logging_setup import log
from energy_pilot.objectives import load_ziele, objectives_from_classification
from energy_pilot.plan_context import (
    build_classification_context,
    build_classification_prompt,
    build_classification_response_schema,
    build_context,
    build_prompt,
    build_repair_prompt,
    build_response_schema,
)
from energy_pilot.plan_schema import (
    SCHEMA_VERSION,
    SUGGESTION_FIELDS,
    CandidatePlan,
    DeviceSuggestion,
    is_extra_field,
    plan_to_dict,
)
from energy_pilot.settings import CLASSIFICATION_PROMPT_KEY, PLANNING_PROMPT_KEY, get_setting
from energy_pilot.suggestion_publisher import publish_suggestions
from energy_pilot.validator import (
    StabilityLimits,
    missing_suggestion_fields,
    smooth_plan,
    validate,
)
from energy_pilot.weather import weather_config_from_options


@dataclass
class PlanRunResult:
    """Ergebnis eines Planungslaufs für Endpoint/UI."""

    ok: bool
    plan: dict | None
    validation: dict  # {ok, errors, clamped}
    ai_call: dict  # {provider, model, tokens_in, tokens_out, ok, error?}
    context: dict | None
    error: str | None = None
    published: dict | None = None  # {ok, written, failed, reason} – HA-Schreibergebnis


@dataclass
class ClassificationRunResult:
    """Ergebnis eines eigenständigen Klassifizierungslaufs (D-055 Testbutton im Plan-Tab)."""

    ok: bool
    objectives: list[dict] | None  # [{key, label, weight}], None bei Fehler
    reasoning: str | None
    ai_call: dict  # {provider, model, ok, tokens_in?, tokens_out?, error?}
    context: dict | None
    error: str | None = None


@dataclass
class _ClassificationOutcome:
    """Rohes Ergebnis des Klassifizierungs-Aufrufs (intern, von `run()` und
    `run_classification()` gemeinsam genutzt)."""

    ok: bool
    context: dict
    data: dict | None
    tokens_in: int | None
    tokens_out: int | None
    error: str | None


def _as_int(value: object) -> int | None:
    """Wandelt einen Modellwert defensiv in int (z.B. 2.0 → 2); sonst None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _gap_count(missing: dict[str, list[str]]) -> int:
    """Anzahl fehlender Pflichtfelder über alle Geräte (Vergleich Erst- vs. Nachforder-Plan)."""
    return sum(len(fields) for fields in missing.values())


def _sum_tokens(first: int | None, second: int | None) -> int | None:
    """Addiert zwei optionale Token-Zähler (None wirkt wie 0; beide None => None)."""
    if first is None and second is None:
        return None
    return (first or 0) + (second or 0)


def _describe_exc(exc: BaseException) -> str:
    """Liefert nie einen leeren Fehlertext – fällt sonst auf den Klassennamen zurück.

    Hintergrund: `str(TimeoutError())` ist leer. Ohne diesen Fallback landete ein
    leerer String in Log, UI und `ai_calls` (Iron Rule 8: kontrollierte, lesbare Fehler).
    """
    return str(exc).strip() or exc.__class__.__name__


class Planner:
    """Erzeugt validierte Kandidatenpläne über einen austauschbaren KI-Provider."""

    def __init__(
        self,
        provider: AIProvider | None,
        config: AddonConfig,
        db: sqlite3.Connection | None,
        *,
        ha_client: object | None = None,
        collector: object | None = None,
        forecast_collector: object | None = None,
        device_collector: object | None = None,
        weather_collector: object | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.db = db
        self.ha_client = ha_client
        self.collector = collector
        self.forecast_collector = forecast_collector
        self.device_collector = device_collector
        self.weather_collector = weather_collector
        self.logger = logger

    async def run(self, *, now: datetime | None = None) -> PlanRunResult:
        """Führt einen kompletten Planungslauf aus (siehe Modul-Docstring)."""
        now = now or datetime.now(UTC)

        state = self.collector.snapshot() if self.collector is not None else {}
        forecast = (
            self.forecast_collector.snapshot() if self.forecast_collector is not None else {}
        )
        weather = (
            self.weather_collector.snapshot() if self.weather_collector is not None else {}
        )
        dc = self.device_collector
        devices = getattr(dc, "devices", []) if dc is not None else []
        readings = getattr(dc, "last_values", {}) if dc is not None else {}
        constraints = build_constraints(devices, readings)

        valid_from = now.isoformat()
        window_min = int(self.config.planning_interval_min)
        valid_until = (now + timedelta(minutes=window_min)).isoformat()

        # Vorplan als Anker laden (A1): stabilisiert Lauf-zu-Lauf, indem die KI ihn als
        # `previous_plan` mitbekommt (verdichtet in build_context). Der zuletzt GÜLTIGE Plan
        # ist zusätzlich die Delta-Limit-Basis der Anti-Flatter-Schicht (A2). Vor dem KI-Aufruf
        # geladen, damit der noch nicht gespeicherte neue Plan ihn nicht überschreibt.
        previous_plan = self.latest_plan()
        previous_valid = self.latest_plan(only_ok=True)

        weather_detail = weather_config_from_options(self.config.values).llm_detail
        run_id = uuid4().hex[:12]

        if self.provider is None:
            return PlanRunResult(
                ok=False,
                plan=None,
                validation={
                    "ok": False,
                    "errors": ["KI nicht konfiguriert (api_key fehlt)"],
                    "clamped": [],
                },
                ai_call={},
                context=None,
                error="provider_not_configured",
            )

        # Vorgelagerter Klassifizierungs-Aufruf (D-055): leitet aus den user-definierten Zielen
        # (Ziele-Tab) je Lauf eine Gewichtung ab, bevor der eigentliche Plan-Aufruf läuft. Ohne
        # konfigurierte Ziele entfällt der Aufruf ersatzlos (objectives bleibt leer). Scheitert der
        # Aufruf, gilt der GESAMTE Planungslauf als gescheitert (kein stiller Fallback).
        ziele = load_ziele(self.db)
        objectives: list = []
        class_tokens_in: int | None = None
        class_tokens_out: int | None = None
        if ziele:
            outcome = await self._run_classification_call(
                now=now, state=state, forecast=forecast, weather=weather, constraints=constraints,
                valid_from=valid_from, valid_until=valid_until, weather_detail=weather_detail,
                previous_plan=previous_plan, ziele=ziele, run_id=run_id,
            )
            if not outcome.ok:
                return PlanRunResult(
                    ok=False,
                    plan=None,
                    validation={
                        "ok": False,
                        "errors": [f"Klassifizierungs-Aufruf fehlgeschlagen: {outcome.error}"],
                        "clamped": [],
                    },
                    ai_call={
                        "provider": self.provider.name,
                        "model": str(self.config.model),
                        "ok": False,
                        "error": outcome.error,
                    },
                    context=outcome.context,
                    error="classification_error",
                )
            class_tokens_in = outcome.tokens_in
            class_tokens_out = outcome.tokens_out
            objectives = objectives_from_classification(
                ziele, (outcome.data or {}).get("gewichtung") or {}
            )

        context = build_context(
            state, forecast, constraints, objectives,
            valid_from=valid_from, valid_until=valid_until,
            weather=weather,
            horizon_h=int(self.config.forecast_horizon_h),
            weather_detail=weather_detail,
            now=now,
            previous_plan=previous_plan,
            quantize=self._quantize_config(),
        )

        # Editierbare Instruktion aus der EP-Oberfläche (sonst Default); Daten-Block hängt
        # build_prompt selbst an, das Antwort-Schema bleibt code-kontrolliert.
        prompt = build_prompt(context, get_setting(self.db, PLANNING_PROMPT_KEY))
        schema = build_response_schema(constraints)
        try:
            response = await self.provider.generate(prompt, schema)
        except Exception as exc:  # kontrolliert: nie Crash (Iron Rule 8)
            detail = _describe_exc(exc)
            self._record_ai_call(ok=False, tokens_in=None, tokens_out=None, error=detail)
            self._log(
                "error", "KI-Planung fehlgeschlagen",
                context={"error": detail}, run_id=run_id,
                provider=self.provider.name, model=str(self.config.model),
            )
            return PlanRunResult(
                ok=False,
                plan=None,
                validation={
                    "ok": False,
                    "errors": [f"KI-Aufruf fehlgeschlagen: {detail}"],
                    "clamped": [],
                },
                ai_call={
                    "provider": self.provider.name,
                    "model": str(self.config.model),
                    "ok": False,
                    "error": detail,
                },
                context=context,
                error="provider_error",
            )

        self._record_ai_call(
            ok=True, tokens_in=response.tokens_in, tokens_out=response.tokens_out, error=None
        )
        tokens_in = _sum_tokens(class_tokens_in, response.tokens_in)
        tokens_out = _sum_tokens(class_tokens_out, response.tokens_out)

        plan_dict = self._assemble_plan(
            response.data, plan_id=run_id, valid_from=valid_from, valid_until=valid_until
        )

        # Vollständigkeits-Nachforderung (D-050): fehlen dem Modell-Plan Pflicht-Vorschlagsfelder,
        # genau diese einmalig gezielt nachfordern. Der Validator würde sie sonst deterministisch
        # füllen; ein echter KI-Wert ist aber besser (v.a. für die Prio). Scheitert der Aufruf,
        # bleibt der erste Plan und die Validator-Füllung greift (Iron Rule 8).
        missing = missing_suggestion_fields(plan_dict, constraints)
        if missing and bool(self.config.values.get("ai_repair_missing", True)):
            try:
                repair = await self.provider.generate(
                    build_repair_prompt(prompt, missing), schema
                )
                self._record_ai_call(
                    ok=True, tokens_in=repair.tokens_in, tokens_out=repair.tokens_out, error=None
                )
                tokens_in = _sum_tokens(tokens_in, repair.tokens_in)
                tokens_out = _sum_tokens(tokens_out, repair.tokens_out)
                repaired = self._assemble_plan(
                    repair.data, plan_id=run_id, valid_from=valid_from, valid_until=valid_until
                )
                # Nur übernehmen, wenn die Nachforderung tatsächlich weniger Lücken hat.
                if _gap_count(missing_suggestion_fields(repaired, constraints)) < _gap_count(
                    missing
                ):
                    plan_dict = repaired
                self._log(
                    "info", "KI-Nachforderung fehlender Felder ausgeführt",
                    context={"missing": missing}, run_id=run_id,
                    provider=self.provider.name, model=str(self.config.model),
                )
            except Exception as exc:  # optional: Fehler blockiert nie (Iron Rule 8)
                self._log(
                    "warning", "KI-Nachforderung fehlgeschlagen (Fallback-Füllung greift)",
                    context={"error": _describe_exc(exc)}, run_id=run_id,
                    provider=self.provider.name, model=str(self.config.model),
                )

        min_conf = self.config.values.get("min_confidence_percent")
        result = validate(
            plan_dict, constraints, now=now,
            min_confidence=int(min_conf) if min_conf is not None else None,
        )
        stored = result.normalized_plan or plan_dict

        # Anti-Flatter (A2 / Validator Stufe 5): nur gültige Pläne glätten; abgelehnte werden
        # nicht veröffentlicht und dürfen den Pro-Gerät-Zustand nicht fortschreiben.
        if result.ok:
            self._apply_stability(stored, previous_valid, constraints, result, now)

        self._store_plan(stored, result)
        self._audit("plan_created" if result.ok else "plan_rejected", run_id, result)
        self._log(
            "info" if result.ok else "warning",
            "Plan erzeugt" if result.ok else "Plan abgelehnt (Validierung)",
            context={"ok": result.ok, "errors": result.errors, "clamped": result.clamped},
            run_id=run_id, plan_id=run_id,
            provider=self.provider.name, model=str(self.config.model),
        )

        # Vorschlagswerte nach HA schreiben – nur bei gültigem Plan und aktivem Schalter
        # (geklemmte Pläne sind gültig; abgelehnte werden nie geschrieben). D-008-Schreibweg.
        published = None
        if result.ok and self._publish_enabled():
            pub = await publish_suggestions(
                self.ha_client, stored, devices, logger=self.logger, db=self.db
            )
            published = pub.as_dict()

        return PlanRunResult(
            ok=result.ok,
            plan=stored,
            validation={"ok": result.ok, "errors": result.errors, "clamped": result.clamped},
            ai_call={
                "provider": self.provider.name,
                "model": str(self.config.model),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "ok": True,
            },
            context=context,
            published=published,
        )

    async def _run_classification_call(
        self,
        *,
        now: datetime,
        state: dict,
        forecast: dict,
        weather: dict,
        constraints: list,
        valid_from: str,
        valid_until: str,
        weather_detail: str,
        previous_plan: dict | None,
        ziele: list,
        run_id: str,
    ) -> _ClassificationOutcome:
        """Führt den Klassifizierungs-Aufruf aus (D-055); gemeinsamer Kern von `run()` und
        `run_classification()`. Baut Kontext/Prompt/Schema, ruft den Provider, protokolliert den
        Aufruf (`ai_calls`) und fängt Provider-Exceptions kontrolliert ab (Iron Rule 8)."""
        classification_context = build_classification_context(
            state, forecast, constraints, ziele,
            valid_from=valid_from, valid_until=valid_until,
            weather=weather,
            horizon_h=int(self.config.forecast_horizon_h),
            weather_detail=weather_detail,
            now=now,
            previous_plan=previous_plan,
            quantize=self._quantize_config(),
        )
        classification_prompt = build_classification_prompt(
            classification_context, get_setting(self.db, CLASSIFICATION_PROMPT_KEY)
        )
        classification_schema = build_classification_response_schema(ziele)
        try:
            response = await self.provider.generate(classification_prompt, classification_schema)
        except Exception as exc:  # kontrolliert: nie Crash (Iron Rule 8)
            detail = _describe_exc(exc)
            self._record_ai_call(ok=False, tokens_in=None, tokens_out=None, error=detail)
            self._log(
                "error", "Ziel-Klassifizierung fehlgeschlagen",
                context={"error": detail}, run_id=run_id,
                provider=self.provider.name, model=str(self.config.model),
            )
            return _ClassificationOutcome(
                ok=False, context=classification_context, data=None,
                tokens_in=None, tokens_out=None, error=detail,
            )
        self._record_ai_call(
            ok=True, tokens_in=response.tokens_in, tokens_out=response.tokens_out, error=None
        )
        return _ClassificationOutcome(
            ok=True, context=classification_context, data=response.data,
            tokens_in=response.tokens_in, tokens_out=response.tokens_out, error=None,
        )

    async def run_classification(self, *, now: datetime | None = None) -> ClassificationRunResult:
        """Führt NUR den Klassifizierungs-Aufruf aus (D-055 Testbutton im Plan-Tab), unabhängig
        vom eigentlichen Plan-Aufruf. Nützlich, um Ziele-Definitionen/Klassifizierungs-Prompt
        gezielt zu testen, ohne einen vollständigen (teureren) Planungslauf auszulösen."""
        now = now or datetime.now(UTC)
        ziele = load_ziele(self.db)
        if not ziele:
            return ClassificationRunResult(
                ok=False, objectives=None, reasoning=None, ai_call={},
                context=None, error="keine_ziele_konfiguriert",
            )
        if self.provider is None:
            return ClassificationRunResult(
                ok=False, objectives=None, reasoning=None, ai_call={},
                context=None, error="provider_not_configured",
            )

        state = self.collector.snapshot() if self.collector is not None else {}
        forecast = (
            self.forecast_collector.snapshot() if self.forecast_collector is not None else {}
        )
        weather = (
            self.weather_collector.snapshot() if self.weather_collector is not None else {}
        )
        dc = self.device_collector
        devices = getattr(dc, "devices", []) if dc is not None else []
        readings = getattr(dc, "last_values", {}) if dc is not None else {}
        constraints = build_constraints(devices, readings)

        valid_from = now.isoformat()
        window_min = int(self.config.planning_interval_min)
        valid_until = (now + timedelta(minutes=window_min)).isoformat()
        previous_plan = self.latest_plan()
        weather_detail = weather_config_from_options(self.config.values).llm_detail
        run_id = uuid4().hex[:12]

        outcome = await self._run_classification_call(
            now=now, state=state, forecast=forecast, weather=weather, constraints=constraints,
            valid_from=valid_from, valid_until=valid_until, weather_detail=weather_detail,
            previous_plan=previous_plan, ziele=ziele, run_id=run_id,
        )
        if not outcome.ok:
            return ClassificationRunResult(
                ok=False, objectives=None, reasoning=None,
                ai_call={
                    "provider": self.provider.name, "model": str(self.config.model),
                    "ok": False, "error": outcome.error,
                },
                context=outcome.context, error="classification_error",
            )
        gewichtung = (outcome.data or {}).get("gewichtung") or {}
        reasoning = (outcome.data or {}).get("reasoning")
        objectives = objectives_from_classification(ziele, gewichtung)
        return ClassificationRunResult(
            ok=True,
            objectives=[asdict(o) for o in objectives],
            reasoning=str(reasoning) if reasoning is not None else None,
            ai_call={
                "provider": self.provider.name, "model": str(self.config.model),
                "ok": True, "tokens_in": outcome.tokens_in, "tokens_out": outcome.tokens_out,
            },
            context=outcome.context,
            error=None,
        )

    def latest_plan(self, *, only_ok: bool = False) -> dict | None:
        """Liefert den zuletzt gespeicherten Plan inkl. Validierungsergebnis (für /api/plan).

        `only_ok=True` liefert den zuletzt **gültigen** Plan (Delta-Limit-Basis der A2-Glättung).
        """
        if self.db is None:
            return None
        row = self.db.execute(
            "SELECT ts, plan_id, ok, plan_json, errors_json, clamped_json FROM plans "
            + ("WHERE ok=1 " if only_ok else "")
            + "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "ts": row["ts"],
            "ok": bool(row["ok"]),
            "plan": json.loads(row["plan_json"]),
            "validation": {
                "ok": bool(row["ok"]),
                "errors": json.loads(row["errors_json"] or "[]"),
                "clamped": json.loads(row["clamped_json"] or "[]"),
            },
        }

    async def publish_latest(self) -> dict:
        """Schreibt den zuletzt **gültigen** Plan erneut als HA-Sensoren (manueller Button).

        Liefert das Schreibergebnis (`ok`/`written`/`failed`/`reason`); ohne gültigen Plan
        bzw. ohne HA-Client kommt eine klare Begründung statt eines Fehlers (Iron Rule 8).
        """
        latest = self.latest_plan()
        if latest is None or not latest.get("ok"):
            return {
                "ok": False, "written": [], "failed": [],
                "reason": "kein gültiger Plan vorhanden",
            }
        dc = self.device_collector
        devices = getattr(dc, "devices", []) if dc is not None else []
        result = await publish_suggestions(
            self.ha_client, latest["plan"], devices, logger=self.logger, db=self.db
        )
        return result.as_dict()

    async def aclose(self) -> None:
        """Schließt die Provider-Ressourcen (aiohttp-Session)."""
        if self.provider is not None:
            await self.provider.close()

    # -- intern -------------------------------------------------------------

    def _publish_enabled(self) -> bool:
        """Ob Vorschlagswerte nach HA geschrieben werden (Addon-Option, Default an)."""
        return bool(self.config.values.get("publish_suggestions", True))

    def _quantize_config(self) -> dict:
        """Snap-Schritte für die Eingangs-Quantisierung (A3) aus der Addon-Config."""
        v = self.config.values
        return {
            "power_w": v.get("snap_power_w", 50),
            "soc_percent": v.get("snap_soc_percent", 1),
            "amp_a": v.get("snap_amp_a", 0.1),
            "forecast_kwh": v.get("snap_forecast_kwh", 0.1),
        }

    def _apply_stability(
        self, plan: dict, previous_valid: dict | None, constraints: list, result: object,
        now: datetime,
    ) -> None:
        """Glättet einen gültigen Plan (A2) in-place und persistiert den Pro-Gerät-Zustand.

        Delta-Limit gegen den zuletzt gültigen Plan + Freigabe-Hysterese/Mindesthaltezeit; die
        Glättungs-Notizen werden wie Klemmungen an `result.clamped` gehängt (UI/Audit).
        """
        v = self.config.values
        limits = StabilityLimits(
            power_percent=float(v.get("delta_limit_power_percent", 20)),
            battery_percent=float(v.get("delta_limit_battery_percent", 10)),
            hysteresis_runs=int(v.get("freigabe_hysteresis_runs", 2)),
            min_hold_minutes=float(v.get("min_hold_minutes", 15)),
        )
        prev_plan = (previous_valid or {}).get("plan") or {}
        previous_by_name = {
            d["name"]: d
            for d in prev_plan.get("devices", [])
            if isinstance(d, dict) and d.get("name")
        }
        constraints_by_name = {c.name: c for c in constraints}
        smoothed = smooth_plan(
            plan.get("devices", []), previous_by_name, constraints_by_name,
            self._load_device_state(), limits=limits, now=now,
        )
        result.clamped.extend(smoothed.notes)
        self._save_device_state(smoothed.state)

    def _load_device_state(self) -> dict[str, dict]:
        """Lädt den Pro-Gerät-Anti-Flatter-Zustand aus der DB (leer bei Fehler/ohne DB)."""
        if self.db is None:
            return {}
        try:
            rows = self.db.execute(
                "SELECT device_name, last_freigabe, last_prio, pending_freigabe, "
                "pending_count, last_change_ts FROM device_plan_state"
            ).fetchall()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert die Planung nie
            return {}
        return {
            row["device_name"]: {
                "last_freigabe": row["last_freigabe"],
                "last_prio": row["last_prio"],
                "pending_freigabe": row["pending_freigabe"],
                "pending_count": row["pending_count"],
                "last_change_ts": row["last_change_ts"],
            }
            for row in rows
        }

    def _save_device_state(self, state: dict[str, dict]) -> None:
        """Persistiert den Pro-Gerät-Anti-Flatter-Zustand (Upsert; DB-Fehler blockieren nie)."""
        if self.db is None:
            return
        try:
            for name, st in state.items():
                self.db.execute(
                    "INSERT INTO device_plan_state (device_name, last_freigabe, last_prio, "
                    "pending_freigabe, pending_count, last_change_ts) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(device_name) DO UPDATE SET "
                    "last_freigabe=excluded.last_freigabe, last_prio=excluded.last_prio, "
                    "pending_freigabe=excluded.pending_freigabe, "
                    "pending_count=excluded.pending_count, last_change_ts=excluded.last_change_ts",
                    (name, st.get("last_freigabe"), st.get("last_prio"),
                     st.get("pending_freigabe"), st.get("pending_count"),
                     st.get("last_change_ts")),
                )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive
            pass

    @staticmethod
    def _device_entries(raw: object) -> list[dict]:
        """Normalisiert die Modell-Geräte auf eine Liste von Einträgen mit `name`.

        Neues Antwort-Schema (D-050): `devices` ist ein Objekt `{Gerätename: {...}}` – der
        Schlüssel ist der autoritative Name. Fällt ein Modell/Provider auf die frühere Array-Form
        zurück, wird auch diese akzeptiert (Robustheit über Provider-/Modellwechsel hinweg).
        """
        if isinstance(raw, dict):
            entries: list[dict] = []
            for name, entry in raw.items():
                if isinstance(entry, dict):
                    merged = dict(entry)
                    merged["name"] = name  # Schlüssel gewinnt über evtl. abweichenden inneren name
                    entries.append(merged)
            return entries
        if isinstance(raw, list):
            return [entry for entry in raw if isinstance(entry, dict)]
        return []

    def _assemble_plan(
        self, model_data: dict, *, plan_id: str, valid_from: str, valid_until: str
    ) -> dict:
        """Baut den vollständigen Plan: EP-Metadaten + Modell-Vorschläge (D-041)."""
        suggestions: list[DeviceSuggestion] = []
        for entry in self._device_entries(model_data.get("devices")):
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            fields = {key: entry[key] for key in SUGGESTION_FIELDS if entry.get(key) is not None}
            # Dynamische Zusatz-Vorschläge (D-047) mitnehmen – sonst fielen sie hier heraus.
            extras = {
                key: value
                for key, value in entry.items()
                if key != "name" and is_extra_field(key) and value is not None
            }
            suggestions.append(DeviceSuggestion(name=name, extras=extras, **fields))
        plan = CandidatePlan(
            plan_id=plan_id,
            valid_from=valid_from,
            valid_until=valid_until,
            devices=suggestions,
            provider=self.provider.name if self.provider else "",
            model=str(self.config.model),
            confidence=_as_int(model_data.get("confidence")),
            reasoning=str(model_data.get("reasoning") or ""),
            warnings=[str(w) for w in (model_data.get("warnings") or [])],
            schema_version=SCHEMA_VERSION,
        )
        return plan_to_dict(plan)

    def _record_ai_call(
        self, *, ok: bool, tokens_in: int | None, tokens_out: int | None, error: str | None
    ) -> None:
        if self.db is None:
            return
        provider_name = self.provider.name if self.provider else ""
        try:
            self.db.execute(
                "INSERT INTO ai_calls (provider, model, tokens_in, tokens_out, est_cost, ok, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (provider_name, str(self.config.model), tokens_in, tokens_out, 0.0,
                 1 if ok else 0, error),
            )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert die Planung nie
            pass

    def _store_plan(self, plan_dict: dict, result: object) -> None:
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO plans (plan_id, valid_from, valid_until, ok, provider, model, "
                "confidence, plan_json, errors_json, clamped_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan_dict.get("plan_id"),
                    plan_dict.get("valid_from"),
                    plan_dict.get("valid_until"),
                    1 if result.ok else 0,
                    plan_dict.get("provider"),
                    plan_dict.get("model"),
                    plan_dict.get("confidence"),
                    json.dumps(plan_dict, ensure_ascii=False),
                    json.dumps(result.errors, ensure_ascii=False),
                    json.dumps(result.clamped, ensure_ascii=False),
                ),
            )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive
            pass

    def _audit(self, action: str, plan_id: str, result: object) -> None:
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
                (
                    "planner",
                    action,
                    plan_id,
                    json.dumps(
                        {"ok": result.ok, "errors": result.errors, "clamped": result.clamped},
                        ensure_ascii=False,
                    ),
                ),
            )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive
            pass

    def _log(self, level: str, message: str, **fields: object) -> None:
        if self.logger is not None:
            log(self.logger, level, message, **fields)
