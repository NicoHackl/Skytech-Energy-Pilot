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
    "planning_interval_min": 60,
    "plan_update_interval_min": 15,
    "forecast_horizon_h": 24,
    "min_confidence_percent": 70,
    "collect_interval_s": 30,
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
