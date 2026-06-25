"""Laden der Addon-Konfiguration aus /data/options.json mit Defaults und Env-Override."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# Standardwerte gemäß Decision Log (siehe plan/entscheidungen.md).
DEFAULTS: dict[str, object] = {
    "log_level": "info",
    "provider": "gemini",
    "model": "gemini-3.5-flash",
    # KI-Provider-Schlüssel (D-007/D-041); leer => Planung deaktiviert. Wird nie geloggt.
    "api_key": "",
    # Timeout je KI-Aufruf (s) und Rate-Limit-Drossel (Aufrufe/min; Gemini-Free ~10).
    "ai_request_timeout_s": 30,
    "ai_rate_limit_per_min": 10,
    "planning_interval_min": 60,
    "plan_update_interval_min": 15,
    "forecast_horizon_h": 24,
    "min_confidence_percent": 70,
    "collect_interval_s": 30,
    # Vorschlagswerte als sensor.ep_*_vorschlag nach HA schreiben (M2-Schreibweg, D-008).
    # False => reiner Beobachten-Modus: Plan bleibt in UI/DB, EP schreibt nichts nach HA.
    "publish_suggestions": True,
    # Basis-URL des HEMS-Addons für die Geräte-Discovery (D-036). Leer => nur Config-Fallback.
    "hems_base_url": "",
    # Geräteliste als Fallback, falls HEMS nicht erreichbar ist (entity_prefix/class/output_unit).
    "devices": [],
    # PV-Prognose (D-006/D-018/D-026): je Ausrichtung 4 Sensoren, EP summiert je Wert.
    "pv_forecast": [],
    # Anzeigeeinheit der PV-Prognosewerte (EP konvertiert nicht, summiert nur).
    "pv_forecast_unit": "kWh",
    # Wetterprognose (OpenWeatherMap 5-Tage/3-Stunden, direkt im EP abgerufen).
    # api_key leer => Wetterabruf deaktiviert; Koordinaten aus der HA-Zone (Attribute
    # latitude/longitude). Schlüssel wird nie geloggt (Iron Rule 6). Nur EP-intern,
    # noch nicht als HA-Sensor/HEMS-Übergabe.
    "weather": {
        "api_key": "",
        "zone_entity": "zone.home",
        "units": "metric",
        "lang": "de",
        "refresh_min": 30,
    },
    # Weiche Zielgewichte (Prozent, D-011); leeres Dict => Defaults aus info.md §7 (objectives.py).
    "objective_weights": {},
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
