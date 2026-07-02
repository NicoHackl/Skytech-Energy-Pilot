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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from energy_pilot.ai_provider import AIProvider
from energy_pilot.config import AddonConfig
from energy_pilot.constraints import build_constraints
from energy_pilot.logging_setup import log
from energy_pilot.objectives import objectives_from_config
from energy_pilot.plan_context import build_context, build_prompt, build_response_schema
from energy_pilot.plan_schema import (
    SCHEMA_VERSION,
    SUGGESTION_FIELDS,
    CandidatePlan,
    DeviceSuggestion,
    is_extra_field,
    plan_to_dict,
)
from energy_pilot.settings import PLANNING_PROMPT_KEY, get_setting
from energy_pilot.suggestion_publisher import publish_suggestions
from energy_pilot.validator import validate
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


def _as_int(value: object) -> int | None:
    """Wandelt einen Modellwert defensiv in int (z.B. 2.0 → 2); sonst None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


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
        objectives = objectives_from_config(self.config.values)

        valid_from = now.isoformat()
        window_min = int(self.config.planning_interval_min)
        valid_until = (now + timedelta(minutes=window_min)).isoformat()

        weather_detail = weather_config_from_options(self.config.values).llm_detail
        context = build_context(
            state, forecast, constraints, objectives,
            valid_from=valid_from, valid_until=valid_until,
            weather=weather,
            horizon_h=int(self.config.forecast_horizon_h),
            weather_detail=weather_detail,
        )
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
                context=context,
                error="provider_not_configured",
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

        plan_dict = self._assemble_plan(
            response.data, plan_id=run_id, valid_from=valid_from, valid_until=valid_until
        )
        result = validate(plan_dict, constraints, now=now)
        stored = result.normalized_plan or plan_dict
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
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
                "ok": True,
            },
            context=context,
            published=published,
        )

    def latest_plan(self) -> dict | None:
        """Liefert den zuletzt gespeicherten Plan inkl. Validierungsergebnis (für /api/plan)."""
        if self.db is None:
            return None
        row = self.db.execute(
            "SELECT ts, plan_id, ok, plan_json, errors_json, clamped_json "
            "FROM plans ORDER BY id DESC LIMIT 1"
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

    def _assemble_plan(
        self, model_data: dict, *, plan_id: str, valid_from: str, valid_until: str
    ) -> dict:
        """Baut den vollständigen Plan: EP-Metadaten + Modell-Vorschläge (D-041)."""
        suggestions: list[DeviceSuggestion] = []
        for entry in model_data.get("devices", []):
            if not isinstance(entry, dict):
                continue
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
