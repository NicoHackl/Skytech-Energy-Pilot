"""Einstiegspunkt: initialisiert Logging, Datenbank, HA-Client und Webserver."""

from __future__ import annotations

import os

from aiohttp import web

from energy_pilot import __version__
from energy_pilot.aggregation import RollingAggregator
from energy_pilot.collector import StateCollector
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.entity_map import mapping_from_options
from energy_pilot.ha_client import HAClient
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

    poll_interval = float(config.collect_interval_s)
    return create_app(
        config,
        db,
        ring,
        ha_client,
        collector,
        version=__version__,
        logger=logger,
        enable_poller=ha_client is not None,
        poll_interval_s=poll_interval,
    )


def main() -> None:
    web.run_app(build(), host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
