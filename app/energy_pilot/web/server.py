"""aiohttp-Webserver: Ingress-SPA + JSON-API.

Für M0 bewusst einfach/funktional gehalten (vanilla SPA, siehe Decision D-010).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from aiohttp import web

from energy_pilot.config import AddonConfig
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import RingBufferHandler

TEMPLATES = Path(__file__).parent / "templates"


def create_app(
    config: AddonConfig,
    db: sqlite3.Connection,
    ring: RingBufferHandler,
    ha_client: HAClient | None = None,
    *,
    version: str = "0.0.1",
) -> web.Application:
    """Baut die aiohttp-Anwendung mit allen Routen und Abhängigkeiten."""
    app = web.Application()
    app["config"] = config
    app["db"] = db
    app["ring"] = ring
    app["ha_client"] = ha_client
    app["version"] = version
    app.add_routes(
        [
            web.get("/", index),
            web.get("/api/health", health),
            web.get("/api/logs", logs),
            web.get("/api/logs/export", logs_export),
            web.get("/api/ha/test", ha_test),
        ]
    )
    return app


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
