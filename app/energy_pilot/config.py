"""Laden der Addon-Konfiguration aus /data/options.json mit Defaults und Env-Override."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# Unterstützte KI-Anbieter (D-056) + Default-Modell je Anbieter. Der aktive Anbieter wird über
# die Top-Level-Option `provider` gewählt; jeder Anbieter hat ein eigenes Untermenü unter
# `providers.<name>` (api_key/model/timeout_s/rate_limit_per_min).
PROVIDER_CHOICES = ("gemini", "claude", "openai")
DEFAULT_PROVIDER = "gemini"
DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "claude": "claude-sonnet-5",
    "openai": "gpt-5",
}
DEFAULT_TIMEOUT_S = 30
# Rate-Limit-Default je Anbieter (Gemini-Free ~10/min; Claude/OpenAI höher).
DEFAULT_RATE_LIMITS: dict[str, int] = {"gemini": 10, "claude": 50, "openai": 60}

# Standardwerte gemäß Decision Log (siehe docs/design-entscheidungen.md).
DEFAULTS: dict[str, object] = {
    "log_level": "info",
    # Aktiver KI-Anbieter (D-056); je Anbieter ein eigenes Untermenü unter `providers`.
    "provider": DEFAULT_PROVIDER,
    "providers": {
        name: {
            "api_key": "",
            "model": DEFAULT_MODELS[name],
            "timeout_s": DEFAULT_TIMEOUT_S,
            "rate_limit_per_min": DEFAULT_RATE_LIMITS[name],
        }
        for name in PROVIDER_CHOICES
    },
    # Determinismus des KI-Aufrufs (D-050): niedrige Temperatur + fixer Seed => bei gleichem
    # Kontext stabil dieselben Vorschlagsfelder (behebt schwankende Ausgaben je Lauf/Modell).
    # Geteilt über alle Anbieter (Gemini/OpenAI nutzen sie; Claude ignoriert Sampling-Params).
    "ai_temperature": 0.0,
    "ai_seed": 42,
    # Denkbudget des Modells (D-063, derzeit nur Gemini): bei Flash-Modellen ist „Thinking"
    # standardmäßig aktiv und eine eigene Varianzquelle. 0 = aus (reproduzierbar), >0 = begrenzt,
    # leer/nicht gesetzt = Anbieter-Default unangetastet.
    "ai_thinking_budget": 0,
    # Fehlende Pflicht-Vorschlagsfelder per gezieltem Nachforder-Aufruf ergänzen (ein Versuch),
    # bevor der Validator sie deterministisch auffüllt (D-050).
    "ai_repair_missing": True,
    "planning_interval_min": 60,
    "plan_update_interval_min": 15,
    "forecast_horizon_h": 24,
    "min_confidence_percent": 70,
    "collect_interval_s": 30,
    # Vorschlagswerte als sensor.ep_*_vorschlag nach HA schreiben (M2-Schreibweg, D-008).
    # False => reiner Beobachten-Modus: Plan bleibt in UI/DB, EP schreibt nichts nach HA.
    "publish_suggestions": True,
    # Basis-URL des HEMS-Addons für die Geräte-Discovery (D-036) UND die Status-Rückkopplung
    # (M3). Leer => keine HEMS-Anbindung, damit auch keine Geräte: der frühere Geräte-Fallback
    # aus der Addon-Config wurde ersatzlos entfernt ("EP ohne HEMS ist sinnlos", D-046).
    "hems_base_url": "",
    # HEMS-Status-Rückkopplung (M3): Intervall (s), in dem EP /api/status pollt, die
    # beobachtete Plan-Übereinstimmung ableitet und nach HA spiegelt (entkoppelt vom
    # collect_interval_s; der Collector drosselt sich selbst).
    "hems_status_interval_s": 60,
    # Plan-/HEMS-Status als sensor.ep_plan_status / sensor.ep_hems_verbindung nach HA
    # schreiben (M3). False => nur in UI/DB, kein HA-Schreibweg (eiserne Regel 13 bleibt aktiv).
    "publish_status": True,
    # PV-Prognose (D-006/D-018/D-026): je Ausrichtung 4 Sensoren, EP summiert je Wert.
    "pv_forecast": [],
    # Anzeigeeinheit der PV-Prognosewerte (EP konvertiert nicht, summiert nur).
    "pv_forecast_unit": "kWh",
    # Wetterprognose (OpenWeatherMap, direkt im EP abgerufen). api_key leer => Wetterabruf
    # deaktiviert; Koordinaten aus der HA-Zone (Attribute latitude/longitude). Schlüssel wird
    # nie geloggt (eiserne Regel 7). Nur EP-intern, noch nicht als HA-Sensor/HEMS-Übergabe.
    # source: forecast3h (5-Tage/3-Stunden, Default) | onecall (One Call API 4.0, Abo-pflichtig).
    "weather": {
        "api_key": "",
        "zone_entity": "zone.home",
        "units": "metric",
        "lang": "de",
        "source": "forecast3h",
        "refresh_min": 60,
        # Detailgrad ans LLM (nur forecast3h): "compact" (Bewölkung/Regen/Temp bis Horizont)
        # oder "full" (volle 5 Tage, alle Felder).
        "llm_detail": "compact",
        # One Call API 4.0: je Vorhersagemodell (15min/1h/1day) per Schalter aktivierbar mit
        # eigenem Refresh-Intervall. Jedes aktivierte Modell ist ein eigener bezahlter Call UND
        # fließt in den KI-Kontext (D-054) — beliebige Kombination wählbar, kein Einzel-Select.
        # pages_*: paginierte Seiten je Modell und Abruf (mehr Horizont, je Seite ein eigener
        # bezahlter Call). daily_call_budget: harte Tagesobergrenze ALLER bezahlten One-Call-
        # Anfragen (UTC-Tag, D-045). enable_alerts/refresh_alerts: Unwetterwarnungen (nur Anzeige).
        "onecall": {
            "enable_15min": False,
            "enable_1h": True,
            "enable_1day": True,
            "refresh_15min": 15,
            "refresh_1h": 60,
            "refresh_1day": 180,
            "pages_15min": 1,
            "pages_1h": 1,
            "pages_1day": 1,
            "daily_call_budget": 1000,
            "enable_alerts": True,
            "refresh_alerts": 30,
        },
    },
    # Zuordnung der 9 festen Mess-Rollen (roles.py) auf reale HA-Entity-IDs (D-027). Leer =>
    # Rolle ohne Wert; Änderungen greifen erst nach einem Addon-Neustart (Mapping wird beim
    # Boot geladen). Die beiden Temperatur-Rollen (D-061) liefern der KI den Verlauf, nicht
    # nur den Momentanwert.
    "sensoren": {
        "entity_pv_power": "",
        "entity_house_load": "",
        "entity_grid_power": "",
        "entity_grid_import": "",
        "entity_grid_export": "",
        "entity_battery_power": "",
        "entity_battery_soc": "",
        "entity_hot_water_temp": "",
        "entity_outdoor_temp": "",
    },
}

DEFAULT_OPTIONS_PATH = "/data/options.json"


@dataclass
class AddonConfig:
    """Gekapselte Addon-Konfiguration; Zugriff per Attribut (cfg.model)."""

    values: dict[str, object]

    @classmethod
    def load(
        cls,
        options_path: str = DEFAULT_OPTIONS_PATH,
        env: dict[str, str] | None = None,
    ) -> AddonConfig:
        env = os.environ if env is None else env
        values: dict[str, object] = dict(DEFAULTS)

        # Von Home Assistant geschriebene Addon-Optionen einlesen (falls vorhanden)
        try:
            with open(options_path, encoding="utf-8") as handle:
                loaded = json.load(handle)
            values.update({k: v for k, v in loaded.items() if v is not None})
        except FileNotFoundError:
            pass

        # Optionaler Override für lokale Entwicklung
        if "LOG_LEVEL" in env:
            values["log_level"] = env["LOG_LEVEL"]

        return cls(values)

    def __getattr__(self, name: str) -> object:
        # Greift nur, wenn das Attribut nicht regulär existiert (z.B. nicht "values")
        if name == "values":
            raise AttributeError(name)
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    @property
    def supervisor_token(self) -> str | None:
        """Token für die HA-Core-API (SUPERVISOR_TOKEN, sonst HASSIO_TOKEN/HA_TOKEN)."""
        return (
            os.environ.get("SUPERVISOR_TOKEN")
            or os.environ.get("HASSIO_TOKEN")
            or os.environ.get("HA_TOKEN")
        )


@dataclass(frozen=True)
class ActiveProvider:
    """Aufgelöste Verbindungs-Config des aktiven KI-Anbieters (D-056)."""

    name: str
    api_key: str
    model: str
    timeout_s: float
    rate_limit_per_min: int
    temperature: float | None
    seed: int | None
    thinking_budget: int | None


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def resolve_active_provider(values: dict) -> ActiveProvider:
    """Löst den aktiven Anbieter + seine Verbindungs-Config aus den Addon-Optionen auf (D-056).

    Liest `provider` (Selektor) und die passende Untergruppe `providers.<name>`; fehlende Felder
    fallen auf die Anbieter-Defaults zurück. `temperature`/`seed` sind geteilt (Top-Level).

    Legacy-Migration: Bestehende Gemini-Installationen hatten die Felder flach auf oberster Ebene
    (`api_key`/`model`/`ai_request_timeout_s`/`ai_rate_limit_per_min`). Ist die Gemini-Untergruppe
    (noch) leer, wird auf diese alten Top-Level-Werte zurückgefallen – so verliert ein Update den
    Schlüssel nicht. Nur für Gemini, da frühere Installationen ausschließlich Gemini kannten.
    """
    name = str(values.get("provider") or "").strip().lower()
    if name not in PROVIDER_CHOICES:
        name = DEFAULT_PROVIDER

    providers = values.get("providers")
    group = providers.get(name) if isinstance(providers, dict) else None
    group = group if isinstance(group, dict) else {}

    is_legacy_gemini = name == DEFAULT_PROVIDER

    def _pick(field: str, legacy_key: str, default: object) -> object:
        raw = group.get(field)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if is_legacy_gemini:
                legacy = values.get(legacy_key)
                if legacy is not None and not (isinstance(legacy, str) and not legacy.strip()):
                    return legacy
            return default
        return raw

    api_key = str(_pick("api_key", "api_key", "") or "").strip()
    model = str(_pick("model", "model", DEFAULT_MODELS[name]) or DEFAULT_MODELS[name]).strip()
    timeout_s = _coerce_float(
        _pick("timeout_s", "ai_request_timeout_s", DEFAULT_TIMEOUT_S), float(DEFAULT_TIMEOUT_S)
    )
    rate_limit = _coerce_int(
        _pick("rate_limit_per_min", "ai_rate_limit_per_min", DEFAULT_RATE_LIMITS[name]),
        DEFAULT_RATE_LIMITS[name],
    )

    temperature_raw = values.get("ai_temperature")
    temperature = _coerce_float(temperature_raw, 0.0) if temperature_raw is not None else None
    seed_raw = values.get("ai_seed")
    seed = _coerce_int(seed_raw, 0) if seed_raw is not None else None
    budget_raw = values.get("ai_thinking_budget")
    thinking_budget = max(0, _coerce_int(budget_raw, 0)) if budget_raw is not None else None

    return ActiveProvider(
        name=name,
        api_key=api_key,
        model=model,
        timeout_s=timeout_s,
        rate_limit_per_min=rate_limit,
        temperature=temperature,
        seed=seed,
        thinking_budget=thinking_budget,
    )
