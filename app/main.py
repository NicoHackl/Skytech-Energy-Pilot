"""Einstiegspunkt: initialisiert Logging, Datenbank, HA-Client und Webserver."""

from __future__ import annotations

import os

from aiohttp import web

from energy_pilot import __version__
from energy_pilot.aggregation import RollingAggregator
from energy_pilot.collector import StateCollector
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.device_collector import DeviceCollector
from energy_pilot.entity_map import mapping_from_options
from energy_pilot.forecast import orientations_from_config
from energy_pilot.forecast_collector import ForecastCollector
from energy_pilot.ha_client import HAClient
from energy_pilot.hems_client import HEMSClient
from energy_pilot.logging_setup import log, setup_logging
from energy_pilot.roles import MEASUREMENT_ROLES
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

    token = config.supervisor_token
    ha_client = HAClient(token) if token else None
    if ha_client is None:
        log(logger, "warning", "SUPERVISOR_TOKEN fehlt – HA-Verbindung deaktiviert")

    # State Collector mit der in der Addon-Konfiguration gepflegten Zuordnung aufbauen
    collector = StateCollector(ha_client, RollingAggregator(), MEASUREMENT_ROLES, logger)
    mapping = mapping_from_options(config.values)
    collector.set_mapping(mapping)
    log(logger, "info", "Entitätszuordnung geladen", context={"rollen": sorted(mapping)})

    # HEMS-Client für die Geräte-Discovery (D-036); leer => nur Config-Fallback.
    hems_base_url = str(config.hems_base_url or "").strip()
    hems_client = HEMSClient(hems_base_url) if hems_base_url else None
    # Gerätewerte werden über denselben HA-Client gelesen (es sind HA-Helfer).
    device_collector = DeviceCollector(ha_client, logger)

    # PV-Prognose aus der Addon-Config (mehrere Ausrichtungen, EP summiert je Wert).
    forecast_collector = ForecastCollector(ha_client, logger, unit=str(config.pv_forecast_unit))
    orientations = orientations_from_config(config.values)
    forecast_collector.set_orientations(orientations)
    log(
        logger, "info", "PV-Prognose geladen",
        context={"ausrichtungen": [o.label for o in orientations]},
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
        hems_client=hems_client,
        version=__version__,
        logger=logger,
        enable_poller=ha_client is not None,
        poll_interval_s=poll_interval,
    )


def main() -> None:
    web.run_app(build(), host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
