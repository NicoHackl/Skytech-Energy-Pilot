"""Einstiegspunkt: initialisiert Logging, Datenbank, HA-Client und Webserver."""

from __future__ import annotations

import os

from aiohttp import web

from energy_pilot import __version__
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import log, setup_logging
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

    return create_app(config, db, ring, ha_client, version=__version__)


def main() -> None:
    web.run_app(build(), host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
