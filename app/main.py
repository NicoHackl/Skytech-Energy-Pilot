"""Einstiegspunkt: initialisiert Logging, Datenbank, HA-Client und Webserver."""

from __future__ import annotations

import os

from aiohttp import web

from energy_pilot import __version__
from energy_pilot.aggregation import RollingAggregator
from energy_pilot.allowlist import SOURCE_WEATHER, EntityAllowlist, collect_entity_ids
from energy_pilot.claude_provider import ClaudeProvider
from energy_pilot.collector import StateCollector
from energy_pilot.config import AddonConfig, resolve_active_provider
from energy_pilot.database import init_db
from energy_pilot.device_collector import DeviceCollector
from energy_pilot.entity_map import mapping_from_options
from energy_pilot.forecast import orientations_from_config
from energy_pilot.forecast_collector import ForecastCollector
from energy_pilot.gemini_provider import GeminiProvider
from energy_pilot.ha_client import HAClient
from energy_pilot.hems_client import HEMSClient
from energy_pilot.hems_status_collector import HEMSStatusCollector
from energy_pilot.logging_setup import log, setup_logging
from energy_pilot.onecall_client import OneCallClient
from energy_pilot.openai_provider import OpenAIProvider
from energy_pilot.planner import Planner
from energy_pilot.roles import MEASUREMENT_ROLES
from energy_pilot.weather import SOURCE_ONECALL, weather_config_from_options
from energy_pilot.weather_client import OpenWeatherClient
from energy_pilot.weather_collector import OneCallCollector, WeatherCollector
from energy_pilot.web.server import create_app

DB_PATH = os.environ.get("EP_DB_PATH", "/data/energy_pilot.db")
PORT = int(os.environ.get("EP_PORT", "8098"))


def build() -> web.Application:
    """Stellt alle Komponenten zusammen und liefert die aiohttp-App."""
    config = AddonConfig.load()
    logger, ring = setup_logging(str(config.log_level).upper())
    log(logger, "info", "Energy Pilot startet", context={"version": __version__})

    # Diagnose: welche Token-Variablen sind vorhanden (nur Boolean, nie der Wert)
    token_presence = {
        name: bool(os.environ.get(name))
        for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN", "HA_TOKEN")
    }
    log(logger, "info", "Token-Diagnose", context={"vorhanden": token_presence})

    db = init_db(DB_PATH)

    # Entity Allowlist: Register der freigegebenen Lese-Entitäten (Soft-Guard, D-038).
    # Geräte-IDs kommen erst nach der Discovery hinzu (siehe _discover_devices).
    allowlist = EntityAllowlist(db, logger)

    token = config.supervisor_token
    ha_client = HAClient(token, allowlist=allowlist) if token else None
    if ha_client is None:
        log(logger, "warning", "SUPERVISOR_TOKEN fehlt – HA-Verbindung deaktiviert")

    # State Collector mit der in der Addon-Konfiguration gepflegten Zuordnung aufbauen
    collector = StateCollector(ha_client, RollingAggregator(), MEASUREMENT_ROLES, logger)
    mapping = mapping_from_options(config.values)
    collector.set_mapping(mapping)
    allowlist.register_all(collect_entity_ids(mapping=mapping))
    log(logger, "info", "Entitätszuordnung geladen", context={"rollen": sorted(mapping)})

    # HEMS-Client für die Geräte-Discovery (D-036); ohne Basis-URL kennt EP keine Geräte —
    # einen Config-Fallback gibt es bewusst nicht (D-046).
    hems_base_url = str(config.hems_base_url or "").strip()
    hems_client = HEMSClient(hems_base_url) if hems_base_url else None
    # Gerätewerte werden über denselben HA-Client gelesen (es sind HA-Helfer).
    device_collector = DeviceCollector(ha_client, logger)

    # PV-Prognose aus der Addon-Config (mehrere Ausrichtungen, EP summiert je Wert).
    forecast_collector = ForecastCollector(ha_client, logger, unit=str(config.pv_forecast_unit))
    orientations = orientations_from_config(config.values)
    forecast_collector.set_orientations(orientations)
    allowlist.register_all(collect_entity_ids(orientations=orientations))
    log(
        logger, "info", "PV-Prognose geladen",
        context={"ausrichtungen": [o.label for o in orientations]},
    )

    # Wetterprognose (OpenWeatherMap, direkt im EP): Koordinaten aus der HA-Zone. Die Quelle ist
    # in der Addon-Config umschaltbar (D-044): forecast3h (5-Tage/3-Stunden) oder onecall (One Call
    # API 4.0). Ohne API-Schlüssel bzw. ohne HA-Client bleibt der Collector inaktiv (Iron Rule 8).
    weather_config = weather_config_from_options(config.values)
    if weather_config.source == SOURCE_ONECALL:
        onecall_client = (
            OneCallClient(
                weather_config.api_key,
                units=weather_config.units,
                lang=weather_config.lang,
            )
            if weather_config.enabled
            else None
        )
        # db für den persistenten Tages-Call-Budget-Zähler (O2, D-045).
        weather_collector = OneCallCollector(
            ha_client, weather_config, onecall_client, logger, db=db
        )
    else:
        weather_client = (
            OpenWeatherClient(
                weather_config.api_key,
                units=weather_config.units,
                lang=weather_config.lang,
            )
            if weather_config.enabled
            else None
        )
        weather_collector = WeatherCollector(ha_client, weather_config, weather_client, logger)
    if weather_config.enabled:
        # Die Zone ist eine Lese-Entität → in die Soft-Allowlist aufnehmen (D-038).
        allowlist.register_all({weather_config.zone_entity: SOURCE_WEATHER})
        context = {"zone": weather_config.zone_entity, "source": weather_config.source}
        if weather_config.source == SOURCE_ONECALL:
            context["timelines"] = list(weather_config.onecall.enabled_timelines)
        else:
            context["refresh_min"] = weather_config.refresh_min
        log(logger, "info", "Wetterprognose aktiv", context=context)
    else:
        log(logger, "info", "Wetterprognose inaktiv (kein OpenWeatherMap-Schlüssel)")

    # KI-Provider (D-007/D-041/D-056): aktiver Anbieter + Verbindungs-Config aus den Optionen
    # auflösen (Radio-Selektor `provider` + Untermenü `providers.<name>`). Nur bei vorhandenem
    # Schlüssel aktiv; ohne Schlüssel bleibt die Planung deaktiviert (EP blockiert nie,
    # Iron Rule 8).
    active = resolve_active_provider(config.values)
    provider = None
    if active.api_key:
        if active.name == "claude":
            # Claude akzeptiert keine festen Sampling-Parameter (temperature/seed) mehr.
            provider = ClaudeProvider(
                active.api_key,
                model=active.model,
                timeout_s=active.timeout_s,
                rate_limit_per_min=active.rate_limit_per_min,
            )
        elif active.name == "openai":
            provider = OpenAIProvider(
                active.api_key,
                model=active.model,
                timeout_s=active.timeout_s,
                rate_limit_per_min=active.rate_limit_per_min,
                temperature=active.temperature,
                seed=active.seed,
            )
        else:  # gemini (Default)
            provider = GeminiProvider(
                active.api_key,
                model=active.model,
                timeout_s=active.timeout_s,
                rate_limit_per_min=active.rate_limit_per_min,
                temperature=active.temperature,
                seed=active.seed,
            )
        log(logger, "info", "KI-Provider aktiv", provider=active.name, model=active.model)
    else:
        log(logger, "warning", "KI-Provider nicht konfiguriert (api_key fehlt) – Planung inaktiv")

    # Planner immer bauen (auch ohne Provider), damit /api/plan die Historie zeigen kann.
    planner = Planner(
        provider,
        config,
        db,
        ha_client=ha_client,
        collector=collector,
        forecast_collector=forecast_collector,
        device_collector=device_collector,
        weather_collector=weather_collector,
        logger=logger,
    )

    # HEMS-Status-Rückkopplung (M3): nur bei konfiguriertem HEMS. Liest /api/status,
    # leitet die beobachtete Plan-Übereinstimmung ab und spiegelt sie als EP-Sensoren.
    hems_status_collector = (
        HEMSStatusCollector(
            hems_client,
            logger=logger,
            planner=planner,
            device_collector=device_collector,
            ha_client=ha_client,
            db=db,
            publish_status_enabled=bool(config.values.get("publish_status", True)),
            interval_s=float(config.hems_status_interval_s),
        )
        if hems_client is not None
        else None
    )

    poll_interval = float(config.collect_interval_s)
    return create_app(
        config,
        db,
        ring,
        ha_client,
        collector,
        device_collector,
        forecast_collector,
        weather_collector=weather_collector,
        hems_client=hems_client,
        hems_status_collector=hems_status_collector,
        allowlist=allowlist,
        planner=planner,
        version=__version__,
        logger=logger,
        enable_poller=ha_client is not None,
        poll_interval_s=poll_interval,
    )


def main() -> None:
    web.run_app(build(), host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
