"""aiohttp-Webserver: Ingress-SPA + JSON-API.

Für M0/M1 bewusst einfach/funktional gehalten (vanilla SPA, siehe Decision D-010).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

from aiohttp import web

from energy_pilot.collector import StateCollector, run_poller
from energy_pilot.config import AddonConfig
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import RingBufferHandler
from energy_pilot.roles import MEASUREMENT_ROLES

TEMPLATES = Path(__file__).parent / "templates"


def create_app(
    config: AddonConfig,
    db: sqlite3.Connection,
    ring: RingBufferHandler,
    ha_client: HAClient | None = None,
    collector: StateCollector | None = None,
    *,
    version: str = "0.0.1",
    logger: logging.Logger | None = None,
    enable_poller: bool = False,
    poll_interval_s: float = 30.0,
) -> web.Application:
    """Baut die aiohttp-Anwendung mit allen Routen und Abhängigkeiten."""
    app = web.Application()
    app["config"] = config
    app["db"] = db
    app["ring"] = ring
    app["ha_client"] = ha_client
    app["collector"] = collector
    app["version"] = version
    app["logger"] = logger
    app["poll_interval_s"] = poll_interval_s
    app.add_routes(
        [
            web.get("/", index),
            web.get("/api/health", health),
            web.get("/api/logs", logs),
            web.get("/api/logs/export", logs_export),
            web.get("/api/ha/test", ha_test),
            web.get("/api/state", state),
            web.get("/api/entities", entities_get),
        ]
    )
    if enable_poller and collector is not None:
        app.on_startup.append(_start_poller)
        app.on_cleanup.append(_stop_poller)
    return app


async def _start_poller(app: web.Application) -> None:
    app["_poll_task"] = asyncio.create_task(
        run_poller(app["collector"], app["poll_interval_s"], app["logger"])
    )


async def _stop_poller(app: web.Application) -> None:
    task = app.get("_poll_task")
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def index(request: web.Request) -> web.Response:
    """Liefert die Ingress-SPA aus."""
    html = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def health(request: web.Request) -> web.Response:
    """Statusendpunkt für UI und Überwachung."""
    config: AddonConfig = request.app["config"]
    payload: dict[str, Any] = {
        "status": "ok",
        "version": request.app["version"],
        "provider": config.provider,
        "model": config.model,
        "ha_configured": request.app["ha_client"] is not None,
    }
    return web.json_response(payload)


async def logs(request: web.Request) -> web.Response:
    """Liefert die letzten Log-Einträge (optional nach Level/Anzahl gefiltert)."""
    ring: RingBufferHandler = request.app["ring"]
    level = request.query.get("level")
    limit_param = request.query.get("limit")
    limit = int(limit_param) if limit_param else None
    return web.json_response(ring.records(level=level, limit=limit))


async def logs_export(request: web.Request) -> web.Response:
    """Maschinenlesbarer Log-Export (JSONL) für die KI-gestützte Fehleranalyse."""
    ring: RingBufferHandler = request.app["ring"]
    level = request.query.get("level")
    body = ring.export_jsonl(level=level)
    return web.Response(
        text=body,
        content_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=energy_pilot_logs.jsonl"},
    )


async def ha_test(request: web.Request) -> web.Response:
    """Testet die Verbindung zu Home Assistant."""
    client: HAClient | None = request.app["ha_client"]
    if client is None:
        return web.json_response(
            {"connected": False, "reason": "kein HA-Client konfiguriert"}, status=503
        )
    try:
        result = await client.test_connection()
        return web.json_response({"connected": True, "result": result})
    except Exception as exc:
        # Der Verbindungstest meldet jeden Fehler kontrolliert zurück (kein Crash)
        return web.json_response({"connected": False, "reason": str(exc)}, status=502)


async def state(request: web.Request) -> web.Response:
    """Aktuelle Messwerte je Rolle inkl. 1/15/60-min-Mittelwerte."""
    collector: StateCollector | None = request.app["collector"]
    if collector is None:
        return web.json_response({})
    return web.json_response(collector.snapshot())


async def entities_get(request: web.Request) -> web.Response:
    """Liefert alle Rollen mit der in der Addon-Konfiguration gepflegten Zuordnung.

    Reine Anzeige: Die Pflege erfolgt in der Addon-Konfiguration (Decision-Änderung).
    """
    collector: StateCollector | None = request.app["collector"]
    mapping = collector.mapping if collector is not None else {}
    payload = []
    for role in MEASUREMENT_ROLES:
        current = mapping.get(role.key)
        payload.append(
            {
                "role": role.key,
                "label": role.label,
                "unit": role.unit,
                "averaged": role.averaged,
                "entity_id": current.entity_id if current else None,
                "fallback_value": current.fallback_value if current else None,
            }
        )
    return web.json_response(payload)
