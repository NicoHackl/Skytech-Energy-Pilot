"""Planning-Engine: erzeugt einen Kandidatenplan (docs/planungs-engine.md, D-041).

Ablauf: Snapshots holen → harte Grenzen + Ziele ableiten → verdichteten Kontext +
Prompt + Antwort-Schema bauen → KI-Aufruf (Single-Shot) → Plan **montieren** (EP
setzt die Metadaten plan_id/Zeiten selbst, nie das Modell) → lokal **validieren**
(`validator.py`) → in DB protokollieren (`ai_calls`, `plans`, `audit`).

V1 (D-008): Ergebnis sind reine Vorschlagswerte – kein Schreiben nach HA, keine
Übernahme durch HEMS. Provider-Fehler werden kontrolliert abgefangen; die App
blockiert nie (eiserne Regel 13).
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
from energy_pilot.device_regeln import get_global_regeln
from energy_pilot.device_speicher import load_speicher
from energy_pilot.features import build_device_features, build_system_features
from energy_pilot.history_collector import energy_sources_for
from energy_pilot.logging_setup import log
from energy_pilot.objectives import load_ziele, objectives_from_classification
from energy_pilot.plan_context import (
    build_classification_context,
    build_classification_response_schema,
    build_context,
    build_data_block,
    build_prompt,
    build_repair_prompt,
    build_response_schema,
    classification_instruction,
    context_hash,
    planning_instruction,
)
from energy_pilot.plan_schema import (
    SCHEMA_VERSION,
    SUGGESTION_FIELDS,
    CandidatePlan,
    DeviceSuggestion,
    aggregate_confidence,
    is_extra_field,
    plan_to_dict,
)
from energy_pilot.settings import CLASSIFICATION_PROMPT_KEY, PLANNING_PROMPT_KEY, get_setting
from energy_pilot.suggestion_publisher import publish_suggestions
from energy_pilot.validator import missing_suggestion_fields, validate
from energy_pilot.weather import weather_config_from_options

# Zeitraster des Kontexts (D-063): `valid_from`/`valid_until` werden darauf abgerundet, damit
# zwei Läufe innerhalb desselben Rasterfensters bei gleicher Sachlage denselben Prompt-String und
# damit denselben Kontext-Hash ergeben. Mit rohem `datetime.now()` war das unmöglich.
CONTEXT_TIME_GRID_MIN = 15


def _floor_to_grid(moment: datetime, grid_min: int = CONTEXT_TIME_GRID_MIN) -> datetime:
    """Rundet einen Zeitpunkt auf das Kontext-Zeitraster ab (Sekunden/Mikrosekunden entfallen)."""
    step = max(1, int(grid_min))
    minutes = (moment.hour * 60 + moment.minute) // step * step
    return moment.replace(
        hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0
    )


@dataclass
class PlanRunResult:
    """Ergebnis eines Planungslaufs für Endpoint/UI."""

    ok: bool
    plan: dict | None
    validation: dict  # {ok, errors, clamped, publish_blocked?}
    ai_call: dict  # {provider, model, tokens_in, tokens_out, ok, error?, sampling_dropped?}
    context: dict | None
    error: str | None = None
    published: dict | None = None  # {ok, written, failed, reason} – HA-Schreibergebnis
    # D-063: Kontext unverändert => kein KI-Aufruf, der gespeicherte Plan gilt weiter.
    reused: bool = False
    context_hash: str | None = None


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


def _parse_iso(value: object) -> datetime | None:
    """Liest einen ISO-Zeitstempel defensiv; fehlendes Offset gilt als UTC (wie im Validator)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _describe_exc(exc: BaseException) -> str:
    """Liefert nie einen leeren Fehlertext – fällt sonst auf den Klassennamen zurück.

    Hintergrund: `str(TimeoutError())` ist leer. Ohne diesen Fallback landete ein
    leerer String in Log, UI und `ai_calls` (eiserne Regel 13: kontrollierte, lesbare Fehler).
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
        history_collector: object | None = None,
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
        self.history_collector = history_collector
        self.logger = logger

    @property
    def model_name(self) -> str:
        """Modell des aktiven Providers (D-056). Das Modell liegt seit dem Multi-Provider-Umbau
        pro Anbieter-Untermenü, nicht mehr top-level – der Provider trägt es selbst."""
        return self.provider.model if self.provider is not None else ""

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

        # Zeitfenster auf dem Kontext-Raster (D-063): sonst unterscheidet sich der Prompt
        # zwangsläufig in jedem Lauf und weder Seed noch Kontext-Hash können wirken.
        anchor = _floor_to_grid(now)
        valid_from = anchor.isoformat()
        window_min = int(self.config.planning_interval_min)
        valid_until = (anchor + timedelta(minutes=window_min)).isoformat()

        # Vorplan als Anker laden (A1): stabilisiert Lauf-zu-Lauf, indem die KI ihn als
        # `previous_plan` mitbekommt (verdichtet in build_context). Vor dem KI-Aufruf geladen,
        # damit der noch nicht gespeicherte neue Plan ihn nicht überschreibt.
        previous_plan = self.latest_plan()

        weather_detail = weather_config_from_options(self.config.values).llm_detail
        global_regeln = get_global_regeln(self.db)
        # Rückblick + gerechnete Merkmale (D-065/D-066): die Grundlage, auf der „reicht es die
        # nächsten Tage?" eine Bilanz statt einer Vermutung ist.
        rueckblick, merkmale, system_merkmale = self._bilanz(state, forecast, devices)
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
                global_regeln=global_regeln, rueckblick=rueckblick,
                features=merkmale, system_features=system_merkmale,
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
                        "model": self.model_name,
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
            global_regeln=global_regeln,
            rueckblick=rueckblick,
            features=merkmale,
            system_features=system_merkmale,
        )

        # Editierbare Instruktion aus der EP-Oberfläche (sonst Default). Sie geht als
        # System-Anweisung an den Provider (D-062), die Daten als User-Nachricht; das
        # Antwort-Schema bleibt code-kontrolliert.
        template = get_setting(self.db, PLANNING_PROMPT_KEY)
        instruction = planning_instruction(template)
        data_block = build_data_block(context)
        # Zusammengesetzte Form für UI, Persistenz und Hash (dokumentierte Sicht, D-063).
        prompt = build_prompt(context, template)
        ctx_hash = context_hash(context, prompt=instruction, model=self.model_name)

        # Unveränderter Kontext => kein KI-Aufruf (D-063). Das beendet „fünfmal drücken, fünf
        # Antworten": bei identischer Sachlage gilt weiter derselbe Plan, statt neu zu würfeln.
        reused = self._reusable_plan(previous_plan, ctx_hash, now)
        if reused is not None:
            return await self._reuse_result(reused, context, ctx_hash, devices, run_id)

        schema = build_response_schema(constraints)
        try:
            response = await self.provider.generate(data_block, schema, system=instruction)
        except Exception as exc:  # kontrolliert: nie Crash (eiserne Regel 13)
            detail = _describe_exc(exc)
            self._record_ai_call(ok=False, tokens_in=None, tokens_out=None, error=detail)
            self._log(
                "error", "KI-Planung fehlgeschlagen",
                context={"error": detail}, run_id=run_id,
                provider=self.provider.name, model=self.model_name,
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
                    "model": self.model_name,
                    "ok": False,
                    "error": detail,
                },
                context=context,
                error="provider_error",
            )

        self._record_ai_call(
            ok=True, tokens_in=response.tokens_in, tokens_out=response.tokens_out, error=None,
            context_hash=ctx_hash, sampling_dropped=response.sampling_dropped,
        )
        # Verworfene Sampling-Parameter sichtbar machen (D-063): vorher wurde eine eingestellte
        # Temperatur 0 stillschweigend zum Anbieter-Default, ohne jede Spur in Log oder UI.
        if response.sampling_dropped:
            self._log(
                "warning",
                "Determinismus nicht aktiv: Modell verwirft temperature/seed",
                run_id=run_id, provider=self.provider.name, model=self.model_name,
            )
        tokens_in = _sum_tokens(class_tokens_in, response.tokens_in)
        tokens_out = _sum_tokens(class_tokens_out, response.tokens_out)

        plan_dict = self._assemble_plan(
            response.data, plan_id=run_id, valid_from=valid_from, valid_until=valid_until
        )

        # Vollständigkeits-Nachforderung (D-050): fehlen dem Modell-Plan Pflicht-Vorschlagsfelder,
        # genau diese einmalig gezielt nachfordern. Der Validator würde sie sonst deterministisch
        # füllen; ein echter KI-Wert ist aber besser (v.a. für die Prio). Scheitert der Aufruf,
        # bleibt der erste Plan und die Validator-Füllung greift (eiserne Regel 13).
        missing = missing_suggestion_fields(plan_dict, constraints)
        if missing and bool(self.config.values.get("ai_repair_missing", True)):
            try:
                repair = await self.provider.generate(
                    build_repair_prompt(data_block, missing), schema, system=instruction
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
                    provider=self.provider.name, model=self.model_name,
                )
            except Exception as exc:  # optional: Fehler blockiert nie (eiserne Regel 13)
                self._log(
                    "warning", "KI-Nachforderung fehlgeschlagen (Fallback-Füllung greift)",
                    context={"error": _describe_exc(exc)}, run_id=run_id,
                    provider=self.provider.name, model=self.model_name,
                )

        result = validate(
            plan_dict, constraints, now=now,
            context=context, min_confidence=self._min_confidence(),
        )
        stored = result.normalized_plan or plan_dict
        self._store_plan(
            stored, result, prompt=prompt, context=context,
            response=response.data, context_hash=ctx_hash,
        )
        self._audit("plan_created" if result.ok else "plan_rejected", run_id, result)
        self._log(
            "info" if result.ok else "warning",
            "Plan erzeugt" if result.ok else "Plan abgelehnt (Validierung)",
            context={
                "ok": result.ok, "errors": result.errors, "clamped": result.clamped,
                "confidence": stored.get("confidence"),
                "publish_blocked": result.publish_blocked,
            },
            run_id=run_id, plan_id=run_id,
            provider=self.provider.name, model=self.model_name,
        )

        # Vorschlagswerte nach HA schreiben – nur bei gültigem Plan, aktivem Schalter und
        # ausreichender Konfidenz (geklemmte Pläne sind gültig; abgelehnte oder zu unsichere
        # werden nie geschrieben). D-008-Schreibweg, Konfidenz-Gate D-064.
        published = None
        if result.ok and not result.publish_blocked and self._publish_enabled():
            pub = await publish_suggestions(
                self.ha_client, stored, devices, logger=self.logger, db=self.db
            )
            published = pub.as_dict()
        elif result.ok and result.publish_blocked:
            # Nur für einen ansonsten gültigen Plan: ein abgelehnter Plan wird aus einem anderen
            # Grund nicht geschrieben, und `published` bleibt dort wie bisher leer.
            published = {
                "ok": False, "written": [], "failed": [], "reason": result.publish_blocked,
            }
            self._log(
                "warning", "Plan nicht veröffentlicht (Konfidenz-Gate)",
                context={"reason": result.publish_blocked},
                run_id=run_id, plan_id=run_id,
            )

        return PlanRunResult(
            ok=result.ok,
            plan=stored,
            validation={
                "ok": result.ok,
                "errors": result.errors,
                "clamped": result.clamped,
                "publish_blocked": result.publish_blocked,
            },
            ai_call={
                "provider": self.provider.name,
                "model": self.model_name,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "ok": True,
                "sampling_dropped": response.sampling_dropped,
            },
            context=context,
            published=published,
            context_hash=ctx_hash,
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
        global_regeln: str = "",
        rueckblick: list | None = None,
        features: list | None = None,
        system_features: dict | None = None,
    ) -> _ClassificationOutcome:
        """Führt den Klassifizierungs-Aufruf aus (D-055); gemeinsamer Kern von `run()` und
        `run_classification()`. Baut Kontext/Prompt/Schema, ruft den Provider, protokolliert den
        Aufruf (`ai_calls`) und fängt Provider-Exceptions kontrolliert ab (eiserne Regel 13)."""
        classification_context = build_classification_context(
            state, forecast, constraints, ziele,
            valid_from=valid_from, valid_until=valid_until,
            weather=weather,
            horizon_h=int(self.config.forecast_horizon_h),
            weather_detail=weather_detail,
            now=now,
            previous_plan=previous_plan,
            global_regeln=global_regeln,
            rueckblick=rueckblick,
            features=features,
            system_features=system_features,
        )
        classification_template = get_setting(self.db, CLASSIFICATION_PROMPT_KEY)
        classification_schema = build_classification_response_schema(ziele)
        try:
            # Instruktion in den System-Kanal, Daten als User-Nachricht (D-062).
            response = await self.provider.generate(
                build_data_block(classification_context),
                classification_schema,
                system=classification_instruction(classification_template),
            )
        except Exception as exc:  # kontrolliert: nie Crash (eiserne Regel 13)
            detail = _describe_exc(exc)
            self._record_ai_call(ok=False, tokens_in=None, tokens_out=None, error=detail)
            self._log(
                "error", "Ziel-Klassifizierung fehlgeschlagen",
                context={"error": detail}, run_id=run_id,
                provider=self.provider.name, model=self.model_name,
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

        anchor = _floor_to_grid(now)
        valid_from = anchor.isoformat()
        window_min = int(self.config.planning_interval_min)
        valid_until = (anchor + timedelta(minutes=window_min)).isoformat()
        previous_plan = self.latest_plan()
        weather_detail = weather_config_from_options(self.config.values).llm_detail
        run_id = uuid4().hex[:12]

        rueckblick, merkmale, system_merkmale = self._bilanz(state, forecast, devices)
        outcome = await self._run_classification_call(
            now=now, state=state, forecast=forecast, weather=weather, constraints=constraints,
            valid_from=valid_from, valid_until=valid_until, weather_detail=weather_detail,
            previous_plan=previous_plan, ziele=ziele, run_id=run_id,
            global_regeln=get_global_regeln(self.db), rueckblick=rueckblick,
            features=merkmale, system_features=system_merkmale,
        )
        if not outcome.ok:
            return ClassificationRunResult(
                ok=False, objectives=None, reasoning=None,
                ai_call={
                    "provider": self.provider.name, "model": self.model_name,
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
                "provider": self.provider.name, "model": self.model_name,
                "ok": True, "tokens_in": outcome.tokens_in, "tokens_out": outcome.tokens_out,
            },
            context=outcome.context,
            error=None,
        )

    def latest_plan(self) -> dict | None:
        """Liefert den zuletzt gespeicherten Plan inkl. Validierungsergebnis (für /api/plan)."""
        if self.db is None:
            return None
        row = self.db.execute(
            "SELECT ts, plan_id, ok, plan_json, errors_json, clamped_json, context_hash, "
            "publish_blocked FROM plans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "ts": row["ts"],
            "ok": bool(row["ok"]),
            "plan": json.loads(row["plan_json"]),
            "context_hash": row["context_hash"],
            "validation": {
                "ok": bool(row["ok"]),
                "errors": json.loads(row["errors_json"] or "[]"),
                "clamped": json.loads(row["clamped_json"] or "[]"),
                "publish_blocked": row["publish_blocked"],
            },
        }

    def _bilanz(self, state: dict, forecast: dict, devices: list) -> tuple[list, list, dict]:
        """Rückblick und gerechnete Merkmale für den Kontext (D-065/D-066).

        Liefert `(rueckblick, geraete_merkmale, system_merkmale)`. Merkmale entstehen nur für
        Geräte mit gepflegten Speicher-Kennwerten — ohne Volumen und Komfortminimum gibt es
        nichts zu rechnen, und eine erfundene Zahl wäre schlimmer als keine.
        """
        hc = self.history_collector
        rueckblick = hc.snapshot() if hc is not None else []
        quellen = tuple(getattr(hc, "sources", ())) if hc is not None else ()
        speicher = load_speicher(self.db)  # einmal lesen, nicht je Gerät
        merkmale = [
            build_device_features(
                device.name,
                speicher[device.name],
                state,
                rueckblick,
                strom_quellen=energy_sources_for(device.name, quellen),
            )
            for device in devices
            if device.name in speicher
        ]
        system = build_system_features(forecast, rueckblick) if rueckblick else {}
        return rueckblick, merkmale, system

    def _min_confidence(self) -> int | None:
        """Schwelle des Konfidenz-Gates (D-064); 0 oder fehlend => kein Gate."""
        raw = self.config.values.get("min_confidence_percent")
        threshold = _as_int(raw) if raw is not None else None
        return threshold if threshold and threshold > 0 else None

    def _reusable_plan(
        self, previous: dict | None, ctx_hash: str, now: datetime
    ) -> dict | None:
        """Liefert den Vorplan zurück, wenn er bei identischem Kontext weiter gilt (D-063).

        Bedingungen, alle nötig: gleicher Kontext-Hash, der Vorplan war gültig, und er ist noch
        nicht abgelaufen. Weil `valid_from`/`valid_until` auf dem Zeitraster liegen, hätte ein
        erneuter KI-Aufruf hier per Konstruktion denselben Prompt — er würde nur neu würfeln.
        """
        if not previous or not previous.get("ok"):
            return None
        if not ctx_hash or previous.get("context_hash") != ctx_hash:
            return None
        plan = previous.get("plan") or {}
        end = _parse_iso(plan.get("valid_until"))
        if end is None or end <= now:
            return None
        return previous

    async def _reuse_result(
        self, previous: dict, context: dict, ctx_hash: str, devices: list, run_id: str
    ) -> PlanRunResult:
        """Baut das Ergebnis eines Laufs ohne KI-Aufruf (Kontext unverändert, D-063).

        Der Plan wird **nicht** erneut gespeichert (er ist derselbe), aber auditiert — sonst
        wäre in der Historie nicht erkennbar, dass ein Lauf stattgefunden hat. Die HA-Sensoren
        werden erneut geschrieben, damit sie unabhängig vom Wiederverwenden aktuell bleiben.
        """
        plan = previous.get("plan") or {}
        validation = dict(previous.get("validation") or {})
        self._log(
            "info", "Plan unverändert übernommen (Kontext identisch)",
            context={"context_hash": ctx_hash, "plan_id": plan.get("plan_id")},
            run_id=run_id,
        )
        if self.db is not None:
            try:
                self.db.execute(
                    "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
                    (
                        "planner", "plan_reused", str(plan.get("plan_id") or ""),
                        json.dumps({"context_hash": ctx_hash}, ensure_ascii=False),
                    ),
                )
                self.db.commit()
            except sqlite3.Error:  # pragma: no cover - DB-Defensive
                pass
        published = None
        if validation.get("ok") and not validation.get("publish_blocked"):
            if self._publish_enabled():
                pub = await publish_suggestions(
                    self.ha_client, plan, devices, logger=self.logger, db=self.db
                )
                published = pub.as_dict()
        return PlanRunResult(
            ok=bool(validation.get("ok")),
            plan=plan,
            validation=validation,
            ai_call={
                "provider": self.provider.name if self.provider else "",
                "model": self.model_name,
                "ok": True,
                "reused": True,
            },
            context=context,
            published=published,
            reused=True,
            context_hash=ctx_hash,
        )

    async def publish_latest(self) -> dict:
        """Schreibt den zuletzt **gültigen** Plan erneut als HA-Sensoren (manueller Button).

        Liefert das Schreibergebnis (`ok`/`written`/`failed`/`reason`); ohne gültigen Plan
        bzw. ohne HA-Client kommt eine klare Begründung statt eines Fehlers (eiserne Regel 13).
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
            regeln = entry.get("angewandte_regeln")
            suggestions.append(
                DeviceSuggestion(
                    name=name,
                    extras=extras,
                    begruendung=str(entry.get("begruendung") or ""),
                    angewandte_regeln=[str(r) for r in regeln] if isinstance(regeln, list) else [],
                    **fields,
                )
            )
        # Konfidenz-Teilnoten (D-064) übernehmen; die Gesamtnote rechnet EP, nicht das Modell.
        # Ältere Templates liefern nur eine flache `confidence` — die bleibt dann gültig.
        teilnoten = self._confidence_parts(model_data.get("konfidenz"))
        plan = CandidatePlan(
            plan_id=plan_id,
            valid_from=valid_from,
            valid_until=valid_until,
            devices=suggestions,
            provider=self.provider.name if self.provider else "",
            model=self.model_name,
            confidence=(
                aggregate_confidence(teilnoten)
                if teilnoten
                else _as_int(model_data.get("confidence"))
            ),
            konfidenz_teilnoten=teilnoten,
            unsicherheiten=[str(u) for u in (model_data.get("unsicherheiten") or [])],
            reasoning=str(model_data.get("reasoning") or ""),
            warnings=[str(w) for w in (model_data.get("warnings") or [])],
            schema_version=SCHEMA_VERSION,
        )
        return plan_to_dict(plan)

    @staticmethod
    def _confidence_parts(raw: object) -> dict[str, int]:
        """Liest die Konfidenz-Teilnoten defensiv als ganze Zahlen 0–100 (D-064)."""
        if not isinstance(raw, dict):
            return {}
        parts: dict[str, int] = {}
        for key, value in raw.items():
            number = _as_int(value)
            if number is None and isinstance(value, int | float) and not isinstance(value, bool):
                number = int(round(float(value)))
            if number is not None:
                parts[str(key)] = max(0, min(100, number))
        return parts

    def _record_ai_call(
        self,
        *,
        ok: bool,
        tokens_in: int | None,
        tokens_out: int | None,
        error: str | None,
        context_hash: str | None = None,
        sampling_dropped: bool = False,
    ) -> None:
        if self.db is None:
            return
        provider_name = self.provider.name if self.provider else ""
        try:
            self.db.execute(
                "INSERT INTO ai_calls (provider, model, tokens_in, tokens_out, est_cost, ok, "
                "error, context_hash, sampling_dropped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (provider_name, self.model_name, tokens_in, tokens_out, 0.0,
                 1 if ok else 0, error, context_hash, 1 if sampling_dropped else 0),
            )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert die Planung nie
            pass

    def _store_plan(
        self,
        plan_dict: dict,
        result: object,
        *,
        prompt: str | None = None,
        context: dict | None = None,
        response: dict | None = None,
        context_hash: str | None = None,
    ) -> None:
        """Speichert den Plan samt Prompt, Kontext, Roh-Antwort und Kontext-Hash (D-063).

        Ohne diese vier Felder ist ein Lauf nachträglich nicht reproduzierbar und zwei Läufe sind
        nicht vergleichbar — genau die Diagnose, die beim Nachstellen schwankender Ergebnisse
        fehlte.
        """
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO plans (plan_id, valid_from, valid_until, ok, provider, model, "
                "confidence, plan_json, errors_json, clamped_json, prompt, context_json, "
                "response_json, context_hash, publish_blocked) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    prompt,
                    json.dumps(context, ensure_ascii=False) if context is not None else None,
                    json.dumps(response, ensure_ascii=False) if response is not None else None,
                    context_hash,
                    getattr(result, "publish_blocked", None),
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
