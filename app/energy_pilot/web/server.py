"""aiohttp-Webserver: Ingress-SPA + JSON-API.

Für M0/M1 bewusst einfach/funktional gehalten (vanilla SPA, siehe Decision D-010).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aiohttp import web

from energy_pilot.collector import StateCollector, run_poller
from energy_pilot.config import AddonConfig
from energy_pilot.constraints import build_constraints
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import RingBufferHandler, log
from energy_pilot.objectives import objectives_from_config
from energy_pilot.plan_schema import PLAN_JSON_SCHEMA, SCHEMA_VERSION, suggestion_keys
from energy_pilot.roles import MEASUREMENT_ROLES

TEMPLATES = Path(__file__).parent / "templates"


def create_app(
    config: AddonConfig,
    db: sqlite3.Connection,
    ring: RingBufferHandler,
    ha_client: HAClient | None = None,
    collector: StateCollector | None = None,
    device_collector: object | None = None,
    forecast_collector: object | None = None,
    *,
    hems_client: object | None = None,
    allowlist: object | None = None,
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
    app["device_collector"] = device_collector
    app["forecast_collector"] = forecast_collector
    app["hems_client"] = hems_client
    app["allowlist"] = allowlist
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
            web.get("/api/devices", devices_get),
            web.get("/api/forecast", forecast_get),
            web.get("/api/allowlist", allowlist_get),
            web.get("/api/constraints", constraints_get),
            web.get("/api/objectives", objectives_get),
            web.get("/api/plan/schema", plan_schema_get),
            web.get("/api/diagnostics", diagnostics),
        ]
    )
    if ha_client is not None:
        app.on_startup.append(_ha_selftest)
    if device_collector is not None:
        app.on_startup.append(_discover_devices)
        app.on_cleanup.append(_close_hems_client)
    if enable_poller and collector is not None:
        app.on_startup.append(_start_poller)
        app.on_cleanup.append(_stop_poller)
    return app


async def _discover_devices(app: web.Application) -> None:
    """Erkennt die Geräte beim Start (HEMS-Schema primär, Config-Fallback, D-036).

    Nach der Discovery sind alle drei Allowlist-Quellen vollständig: die Geräte-
    Entitäten werden registriert und das komplette Register einmal persistiert
    und auditiert (Soft-Guard, D-038).
    """
    from energy_pilot.allowlist import collect_entity_ids
    from energy_pilot.devices import discover

    device_collector = app["device_collector"]
    logger = app["logger"]
    devices, source = await discover(app.get("hems_client"), app["config"].values, logger)
    device_collector.set_devices(devices, source)

    allowlist = app.get("allowlist")
    if allowlist is not None:
        allowlist.register_all(collect_entity_ids(devices=devices))
        allowlist.persist(app["db"])

    if logger is not None:
        log(
            logger, "info", "Geräte erkannt",
            context={"quelle": source, "anzahl": len(devices),
                     "geraete": [d.name for d in devices]},
        )


async def _close_hems_client(app: web.Application) -> None:
    client = app.get("hems_client")
    if client is not None and hasattr(client, "close"):
        await client.close()


async def _ha_selftest(app: web.Application) -> None:
    """Einmaliger Verbindungstest beim Start – Ergebnis landet sichtbar im Log."""
    client: HAClient | None = app["ha_client"]
    logger = app["logger"]
    if client is None or logger is None:
        return
    try:
        await client.test_connection()
        log(logger, "info", "HA-Verbindung erfolgreich getestet")
    except Exception as exc:
        log(logger, "error", "HA-Verbindungstest fehlgeschlagen", context={"error": str(exc)})


async def _start_poller(app: web.Application) -> None:
    app["_poll_task"] = asyncio.create_task(
        run_poller(
            app["collector"],
            app["poll_interval_s"],
            app["logger"],
            device_collector=app.get("device_collector"),
            forecast_collector=app.get("forecast_collector"),
        )
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


async def diagnostics(request: web.Request) -> web.Response:
    """Diagnose für die Statusseite: HA-Verbindung, Poller, letzter Lauf/Fehler."""
    app = request.app
    collector: StateCollector | None = app["collector"]
    device_collector = app.get("device_collector")
    allowlist = app.get("allowlist")
    poll_task = app.get("_poll_task")
    payload: dict[str, Any] = {
        "ha_configured": app["ha_client"] is not None,
        "poller_active": bool(poll_task is not None and not poll_task.done()),
        "poll_interval_s": app["poll_interval_s"],
        "mapped_roles": sorted(collector.mapping) if collector else [],
        "last_collect_ts": getattr(collector, "last_collect_ts", None) if collector else None,
        "last_sources": collector.last_source if collector else {},
        "last_error": getattr(collector, "last_error", None) if collector else None,
        "device_discovery_source": getattr(device_collector, "discovery_source", "none")
        if device_collector
        else "none",
        "device_count": len(getattr(device_collector, "devices", [])) if device_collector else 0,
        "forecast_orientations": len(getattr(app.get("forecast_collector"), "orientations", [])),
        "allowlist_count": allowlist.snapshot()["count"] if allowlist is not None else 0,
    }
    return web.json_response(payload)


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


async def devices_get(request: web.Request) -> web.Response:
    """Liefert die erkannten Geräte samt gelesener `ems_*`-Werte (read-only).

    Discovery: HEMS-Schema primär, Addon-Config als Fallback (D-036). Die Quelle
    steht zusätzlich in der Diagnose.
    """
    device_collector = request.app.get("device_collector")
    if device_collector is None:
        return web.json_response({"source": "none", "devices": []})
    return web.json_response(
        {
            "source": getattr(device_collector, "discovery_source", "none"),
            "devices": device_collector.snapshot(),
        }
    )


async def forecast_get(request: web.Request) -> web.Response:
    """Liefert die summierte PV-Prognose je Wert + Aufschlüsselung pro Ausrichtung."""
    forecast_collector = request.app.get("forecast_collector")
    if forecast_collector is None:
        return web.json_response({})
    return web.json_response(forecast_collector.snapshot())


async def allowlist_get(request: web.Request) -> web.Response:
    """Liefert das Register der freigegebenen Lese-Entitäten (read-only, Transparenz)."""
    allowlist = request.app.get("allowlist")
    if allowlist is None:
        return web.json_response({"count": 0, "by_source": {}, "entries": []})
    return web.json_response(allowlist.snapshot())


async def constraints_get(request: web.Request) -> web.Response:
    """Liefert die abgeleiteten **harten Grenzen** je Gerät + den Schreibvertrag (Transparenz).

    Grundlage sind die zuletzt gelesenen `ems_*`-Werte des DeviceCollectors; die
    harten Grenzen sind read-only und nie durch die KI änderbar.
    """
    device_collector = request.app.get("device_collector")
    if device_collector is None:
        return web.json_response({"devices": []})
    constraints = build_constraints(device_collector.devices, device_collector.last_values)
    payload = []
    for constraint in constraints:
        entry = asdict(constraint)
        # Geräteklasse als `class` ausgeben – gleicher JSON-Vertrag wie /api/devices,
        # auf den das UI (loadConstraints) baut. Das Dataclass-Feld heißt `device_class`,
        # da `class` in Python reserviert ist; ohne dieses Mapping ist `d.class` im UI
        # undefined → der Binär-Zweig greift nie und es würden für Binärgeräte
        # fälschlich Min./Max.-Leistung statt der festen Leistung angezeigt.
        entry["class"] = entry.pop("device_class")
        entry["suggestion_keys"] = suggestion_keys(constraint)
        payload.append(entry)
    return web.json_response({"devices": payload})


async def objectives_get(request: web.Request) -> web.Response:
    """Liefert die aktiven weichen Zielgewichte (Defaults §7 + Addon-Config-Overrides)."""
    config: AddonConfig = request.app["config"]
    objectives = [asdict(obj) for obj in objectives_from_config(config.values)]
    return web.json_response({"objectives": objectives})


async def plan_schema_get(request: web.Request) -> web.Response:
    """Liefert das versionierte Plan-JSON-Schema (Transparenz / spätere HEMS-Abstimmung)."""
    return web.json_response({"schema_version": SCHEMA_VERSION, "schema": PLAN_JSON_SCHEMA})
