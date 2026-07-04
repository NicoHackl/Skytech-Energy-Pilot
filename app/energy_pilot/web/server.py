"""aiohttp-Webserver: Ingress-SPA + JSON-API.

Für M0/M1 bewusst einfach/funktional gehalten (vanilla SPA, siehe Decision D-010).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aiohttp import web

from energy_pilot.collector import StateCollector, run_poller
from energy_pilot.config import AddonConfig
from energy_pilot.constraints import build_constraints
from energy_pilot.device_extras import (
    apply_extras,
    delete_extra,
    is_valid_entity_id,
    load_extras,
    seed_defaults,
    suggestion_conflict,
    upsert_extra,
)
from energy_pilot.device_prompts import load_device_prompts, set_device_prompt
from energy_pilot.devices import DeviceExtra
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import RingBufferHandler, log
from energy_pilot.objectives import objectives_from_config
from energy_pilot.plan_context import DEFAULT_PLANNING_PROMPT
from energy_pilot.plan_schema import PLAN_JSON_SCHEMA, SCHEMA_VERSION, suggestion_keys
from energy_pilot.roles import MEASUREMENT_ROLES
from energy_pilot.settings import (
    PLANNING_PROMPT_KEY,
    delete_setting,
    get_setting,
    set_setting,
)

TEMPLATES = Path(__file__).parent / "templates"

# Auto-Retry der Geräte-Discovery (D-046): HA garantiert keine Addon-Startreihenfolge,
# daher kann das HEMS beim EP-Start noch nicht erreichbar sein. Ohne Config-Fallback liefe
# EP sonst dauerhaft ohne Geräte. Darum bis zu N Wiederholungen im Abstand von M Sekunden,
# Abbruch beim ersten Erfolg; danach hilft der manuelle HEMS-Sync-Button im HEMS-Tab.
DISCOVERY_RETRY_ATTEMPTS = 5
DISCOVERY_RETRY_DELAY_S = 30


def create_app(
    config: AddonConfig,
    db: sqlite3.Connection,
    ring: RingBufferHandler,
    ha_client: HAClient | None = None,
    collector: StateCollector | None = None,
    device_collector: object | None = None,
    forecast_collector: object | None = None,
    *,
    weather_collector: object | None = None,
    hems_client: object | None = None,
    hems_status_collector: object | None = None,
    allowlist: object | None = None,
    planner: object | None = None,
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
    app["weather_collector"] = weather_collector
    app["hems_client"] = hems_client
    app["hems_status_collector"] = hems_status_collector
    app["allowlist"] = allowlist
    app["planner"] = planner
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
            web.post("/api/devices/extras", device_extra_post),
            web.delete("/api/devices/extras", device_extra_delete),
            web.post("/api/devices/prompt", device_prompt_post),
            web.get("/api/forecast", forecast_get),
            web.get("/api/weather", weather_get),
            web.get("/api/weather/test", weather_test),
            web.get("/api/hems/status", hems_status_get),
            web.get("/api/hems/test", hems_test),
            web.post("/api/hems/rediscover", hems_rediscover),
            web.get("/api/allowlist", allowlist_get),
            web.get("/api/constraints", constraints_get),
            web.get("/api/objectives", objectives_get),
            web.get("/api/plan/schema", plan_schema_get),
            web.get("/api/prompt", prompt_get),
            web.post("/api/prompt", prompt_post),
            web.post("/api/plan/run", plan_run),
            web.post("/api/plan/publish", plan_publish),
            web.get("/api/plan", plan_get),
            web.get("/api/ai/test", ai_test),
            web.get("/api/diagnostics", diagnostics),
        ]
    )
    if ha_client is not None:
        app.on_startup.append(_ha_selftest)
    if device_collector is not None:
        app.on_startup.append(_discover_devices)
        app.on_cleanup.append(_close_hems_client)
        app.on_cleanup.append(_stop_discovery_retry)
    if planner is not None:
        app.on_cleanup.append(_close_planner)
    if weather_collector is not None:
        app.on_cleanup.append(_close_weather_client)
    if enable_poller and collector is not None:
        app.on_startup.append(_start_poller)
        app.on_cleanup.append(_stop_poller)
    return app


async def rediscover_devices(app: web.Application) -> tuple[list, str]:
    """Führt die Geräte-Discovery (HEMS-Schema, D-036) aus und übernimmt das Ergebnis.

    Gemeinsame Logik für Start-Discovery, Auto-Retry und den manuellen HEMS-Sync (Button
    im HEMS-Tab, D-046): erkennt die Geräte, aktualisiert den DeviceCollector und baut die
    Allowlist neu auf – so fallen die `ems_*`-Leichen umbenannter/entfernter Geräte raus
    (Soft-Guard, D-038). Liefert (devices, source) mit source ∈ {"hems", "none"}.
    """
    from energy_pilot.allowlist import collect_entity_ids
    from energy_pilot.devices import discover

    device_collector = app["device_collector"]
    logger = app["logger"]
    db = app.get("db")
    devices, source = await discover(app.get("hems_client"), logger)

    # Zusatz-Entitäten (D-047) an die erkannten Geräte mergen: einmalig den Heizstab-Default
    # anlegen (ersetzt Hardcode D-035), dann die user-gepflegte Konfiguration aus der DB anhängen.
    seed_defaults(db, devices)
    devices = apply_extras(devices, load_extras(db), load_device_prompts(db))
    device_collector.set_devices(devices, source)

    allowlist = app.get("allowlist")
    if allowlist is not None:
        allowlist.rebuild(collect_entity_ids(devices=devices))
        allowlist.persist(db)

    if logger is not None:
        log(
            logger, "info", "Geräte erkannt",
            context={"quelle": source, "anzahl": len(devices),
                     "geraete": [d.name for d in devices]},
        )
    return devices, source


def reapply_device_extras(app: web.Application) -> None:
    """Übernimmt geänderte Zusatz-Entitäten (D-047) und Geräte-Prompts (D-051) ohne HEMS-Discovery.

    Lädt Zusatz-Konfiguration und KI-Beschreibungen neu aus der DB, hängt sie an die aktuell
    bekannten Geräte an und baut die Allowlist neu auf (die neuen Lese-Entitäten werden so
    freigegeben). Wird nach jeder CRUD-Änderung im Geräte-Tab aufgerufen – die HEMS-Geräteliste
    bleibt unangetastet.
    """
    from energy_pilot.allowlist import collect_entity_ids

    device_collector = app.get("device_collector")
    if device_collector is None:
        return
    db = app.get("db")
    devices = apply_extras(
        list(device_collector.devices), load_extras(db), load_device_prompts(db)
    )
    device_collector.set_devices(devices, device_collector.discovery_source)

    allowlist = app.get("allowlist")
    if allowlist is not None:
        allowlist.rebuild(collect_entity_ids(devices=devices))
        allowlist.persist(db)


async def _discover_devices(app: web.Application) -> None:
    """Start-Hook: erkennt die Geräte über das HEMS-Schema (D-036).

    Ist das HEMS beim Start noch nicht erreichbar (Addon-Startreihenfolge, D-046), wird die
    Discovery im Hintergrund begrenzt wiederholt (siehe _discovery_retry).
    """
    _, source = await rediscover_devices(app)
    if source != "hems":
        app["_discovery_retry_task"] = asyncio.create_task(_discovery_retry(app))


async def _discovery_retry(app: web.Application) -> None:
    """Wiederholt die Discovery, bis das HEMS Geräte liefert (begrenzt, D-046).

    Bis zu DISCOVERY_RETRY_ATTEMPTS Versuche im Abstand von DISCOVERY_RETRY_DELAY_S s,
    Abbruch beim ersten Erfolg. Danach bleibt es bei „keine Geräte", bis der User im
    HEMS-Tab den Sync-Button drückt.
    """
    logger = app["logger"]
    for attempt in range(1, DISCOVERY_RETRY_ATTEMPTS + 1):
        await asyncio.sleep(DISCOVERY_RETRY_DELAY_S)
        _, source = await rediscover_devices(app)
        if source == "hems":
            if logger is not None:
                log(logger, "info", "HEMS-Geräte nach Wiederholung erkannt",
                    context={"versuch": attempt})
            return
    if logger is not None:
        log(logger, "warning",
            "HEMS nach mehreren Versuchen ohne Geräte – manuellen HEMS-Sync nutzen",
            context={"versuche": DISCOVERY_RETRY_ATTEMPTS})


async def _stop_discovery_retry(app: web.Application) -> None:
    """Bricht den laufenden Auto-Retry-Task beim Herunterfahren sauber ab."""
    task = app.get("_discovery_retry_task")
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _close_hems_client(app: web.Application) -> None:
    client = app.get("hems_client")
    if client is not None and hasattr(client, "close"):
        await client.close()


async def _close_planner(app: web.Application) -> None:
    planner = app.get("planner")
    if planner is not None and hasattr(planner, "aclose"):
        await planner.aclose()


async def _close_weather_client(app: web.Application) -> None:
    collector = app.get("weather_collector")
    client = getattr(collector, "client", None) if collector is not None else None
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
            weather_collector=app.get("weather_collector"),
            hems_status_collector=app.get("hems_status_collector"),
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
        "weather_enabled": bool(getattr(app.get("weather_collector"), "enabled", False)),
        "weather_last_fetch_ts": getattr(app.get("weather_collector"), "last_fetch_ts", None),
        "weather_last_error": getattr(app.get("weather_collector"), "last_error", None),
        "hems_configured": bool(getattr(app.get("hems_status_collector"), "configured", False)),
        "hems_online": bool(getattr(app.get("hems_status_collector"), "online", False)),
        "hems_last_fetch_ts": getattr(app.get("hems_status_collector"), "last_fetch_ts", None),
        "hems_last_error": getattr(app.get("hems_status_collector"), "last_error", None),
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


def _extras_payload(device_collector: object, device_name: str) -> list[dict]:
    """Baut die Zusatz-Entitäten-Konfiguration (D-047) eines Geräts inkl. aktuellem Lesewert."""
    devices = getattr(device_collector, "devices", [])
    last_values = getattr(device_collector, "last_values", {})
    device = next((d for d in devices if d.name == device_name), None)
    if device is None:
        return []
    values = last_values.get(device_name, {})
    payload = []
    for ex in device.extras:
        current = values.get(ex.read_key, {"value": None, "source": "none", "attrs": {}})
        payload.append(
            {
                "read_entity_id": ex.read_entity_id,
                "ai_suggestion": ex.ai_suggestion,
                "ai_hint": ex.ai_hint,
                "label": ex.label,
                "unit": ex.unit,
                "display_label": ex.display_label,
                "domain": ex.domain,
                "kind": ex.kind,
                "plan_field": ex.plan_field,
                "suggestion_entity_id": ex.suggestion_entity_id if ex.ai_suggestion else None,
                # D-052: rohes Flag + Helfer-Fähigkeit + effektiver Original-Schreibweg (fürs UI:
                # Checkbox nur bei is_writable_helper anzeigbar, wirksam nur bei
                # should_write_original).
                "write_original": ex.write_original,
                "is_writable_helper": ex.is_writable_helper,
                "should_write_original": ex.should_write_original,
                "value": current.get("value"),
                "source": current.get("source", "none"),
                # Gelesene HA-Attribute (D-048): input_number min/max, input_datetime has_date/time.
                "attrs": current.get("attrs", {}),
            }
        )
    return payload


async def devices_get(request: web.Request) -> web.Response:
    """Liefert die erkannten Geräte samt gelesener `ems_*`-Werte und Zusatz-Entitäten (read-only).

    Discovery ausschließlich über das HEMS-Schema (D-036); die Quelle ("hems"|"none")
    steht zusätzlich in der Diagnose. Je Gerät liefert `extras` die im Geräte-Tab gepflegten
    Zusatz-Entitäten (D-047) inkl. aktuellem Lesewert.
    """
    device_collector = request.app.get("device_collector")
    if device_collector is None:
        return web.json_response({"source": "none", "devices": []})
    devices = device_collector.snapshot()
    for dev in devices:
        dev["extras"] = _extras_payload(device_collector, dev["name"])
    return web.json_response(
        {
            "source": getattr(device_collector, "discovery_source", "none"),
            "devices": devices,
        }
    )


async def device_extra_post(request: web.Request) -> web.Response:
    """Legt eine Zusatz-Entität (D-047) an oder aktualisiert sie (Geräte-Tab).

    Body: `{device_name, read_entity_id, ai_suggestion, ai_hint?, label?, unit?, write_original?}`.
    Validiert Gerät, Entity-ID-Format, Vorschlags-Sensor-Kollision und den Original-Schreibweg
    (D-052: `write_original` nur zusammen mit `ai_suggestion` erlaubt); übernimmt die Änderung
    sofort (kein HEMS-Reload nötig). Liefert den abgeleiteten Vorschlags-Sensor zurück.
    """
    db = request.app.get("db")
    device_collector = request.app.get("device_collector")
    if db is None or device_collector is None:
        return web.json_response({"ok": False, "reason": "keine Datenbank/Geräte"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "reason": "ungültiger Request-Body"}, status=400)

    device_name = str(body.get("device_name") or "").strip()
    read_entity_id = str(body.get("read_entity_id") or "").strip()
    ai_suggestion = bool(body.get("ai_suggestion"))
    ai_hint = str(body.get("ai_hint") or "").strip()
    label = str(body.get("label") or "").strip()
    unit = str(body.get("unit") or "").strip()
    write_original = bool(body.get("write_original"))

    known = {d.name for d in getattr(device_collector, "devices", [])}
    if device_name not in known:
        return web.json_response(
            {"ok": False, "reason": f"unbekanntes Gerät: {device_name or '(leer)'}"}, status=400
        )
    if not is_valid_entity_id(read_entity_id):
        return web.json_response(
            {"ok": False, "reason": "ungültige Entity-ID (Format: <domain>.<object_id>)"},
            status=400,
        )
    if write_original and not ai_suggestion:
        return web.json_response(
            {"ok": False, "reason": "„In Original schreiben“ setzt einen KI-Vorschlag voraus"},
            status=400,
        )
    if ai_suggestion:
        clash = suggestion_conflict(
            load_extras(db), device_name=device_name, read_entity_id=read_entity_id
        )
        if clash is not None:
            entity = DeviceExtra(read_entity_id=read_entity_id).suggestion_entity_id
            return web.json_response(
                {"ok": False, "reason": f"Vorschlags-Sensor {entity} kollidiert mit {clash}"},
                status=409,
            )

    upsert_extra(
        db,
        device_name=device_name,
        read_entity_id=read_entity_id,
        ai_suggestion=ai_suggestion,
        ai_hint=ai_hint,
        label=label,
        unit=unit,
        write_original=write_original,
    )
    reapply_device_extras(request.app)
    _audit_extra(db, "device_extra_upserted", device_name, read_entity_id)
    extra = DeviceExtra(
        read_entity_id=read_entity_id, ai_suggestion=ai_suggestion, write_original=write_original
    )
    return web.json_response(
        {
            "ok": True,
            "device_name": device_name,
            "read_entity_id": read_entity_id,
            "suggestion_entity_id": extra.suggestion_entity_id if ai_suggestion else None,
            "should_write_original": extra.should_write_original,
        }
    )


async def device_extra_delete(request: web.Request) -> web.Response:
    """Entfernt eine Zusatz-Entität (D-047). Body: `{device_name, read_entity_id}`."""
    db = request.app.get("db")
    if db is None:
        return web.json_response({"ok": False, "reason": "keine Datenbank"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "reason": "ungültiger Request-Body"}, status=400)
    device_name = str(body.get("device_name") or "").strip()
    read_entity_id = str(body.get("read_entity_id") or "").strip()
    if not device_name or not read_entity_id:
        return web.json_response(
            {"ok": False, "reason": "device_name und read_entity_id erforderlich"}, status=400
        )
    delete_extra(db, device_name=device_name, read_entity_id=read_entity_id)
    reapply_device_extras(request.app)
    _audit_extra(db, "device_extra_deleted", device_name, read_entity_id)
    return web.json_response({"ok": True})


async def device_prompt_post(request: web.Request) -> web.Response:
    """Speichert die KI-Beschreibung eines Geräts (D-051). Body: `{device_name, prompt}`.

    Leerer `prompt` löscht die Beschreibung (zurück auf „keine"). Der Text ist advisorisch:
    er geht als Kontext-Feld `funktion` in den Planungs-Prompt ein, nie an das HEMS. Übernimmt
    die Änderung sofort (kein HEMS-Reload nötig) via `reapply_device_extras`.
    """
    db = request.app.get("db")
    device_collector = request.app.get("device_collector")
    if db is None or device_collector is None:
        return web.json_response({"ok": False, "reason": "keine Datenbank/Geräte"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "reason": "ungültiger Request-Body"}, status=400)

    device_name = str(body.get("device_name") or "").strip()
    prompt = str(body.get("prompt") or "").strip()
    known = {d.name for d in getattr(device_collector, "devices", [])}
    if device_name not in known:
        return web.json_response(
            {"ok": False, "reason": f"unbekanntes Gerät: {device_name or '(leer)'}"}, status=400
        )

    is_custom = set_device_prompt(db, device_name, prompt)
    reapply_device_extras(request.app)
    _audit_prompt(
        db, "device_prompt_updated" if is_custom else "device_prompt_reset", len(prompt),
        subject=device_name,
    )
    return web.json_response({"ok": True, "device_name": device_name, "is_custom": is_custom})


def _audit_extra(db: sqlite3.Connection, action: str, device_name: str, entity_id: str) -> None:
    """Protokolliert eine Zusatz-Entität-Änderung (Geräte-Tab); blockiert nie."""
    try:
        db.execute(
            "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
            ("user", action, device_name, f'{{"entity_id": "{entity_id}"}}'),
        )
        db.commit()
    except sqlite3.Error:  # pragma: no cover - Audit darf den Vorgang nie stören
        pass


async def forecast_get(request: web.Request) -> web.Response:
    """Liefert die summierte PV-Prognose je Wert + Aufschlüsselung pro Ausrichtung."""
    forecast_collector = request.app.get("forecast_collector")
    if forecast_collector is None:
        return web.json_response({})
    return web.json_response(forecast_collector.snapshot())


async def weather_get(request: web.Request) -> web.Response:
    """Liefert die OWM-Wetterprognose (5 Tage/3 h) – read-only, nur EP-intern."""
    weather_collector = request.app.get("weather_collector")
    if weather_collector is None:
        return web.json_response({"enabled": False, "forecast": None})
    return web.json_response(weather_collector.snapshot())


async def weather_test(request: web.Request) -> web.Response:
    """Live-Einzelabruf der Wetterprognose (Diagnose-Button), umgeht den Refresh-Guard.

    Meldet jeden Fehler kontrolliert zurück – inkl. OWM-Originalgrund und maskierter
    Anfrage-URL, damit ein 401 (Schlüssel ungültig/inaktiv) direkt erkennbar ist.
    """
    weather_collector = request.app.get("weather_collector")
    if weather_collector is None:
        return web.json_response(
            {"connected": False, "reason": "Wetter nicht konfiguriert"}, status=503
        )
    result = await weather_collector.test_fetch()
    status = 200 if result.get("ok") else 502
    return web.json_response(
        {"connected": result.get("ok", False), "result": result}, status=status
    )


async def hems_status_get(request: web.Request) -> web.Response:
    """Liefert den HEMS-Zustand + die abgeleitete Plan-Rückkopplung (M3, read-only)."""
    collector = request.app.get("hems_status_collector")
    if collector is None:
        return web.json_response({"configured": False, "online": False, "feedback": None})
    payload = collector.snapshot()
    payload["feedback"] = getattr(collector, "last_feedback", None)
    return web.json_response(payload)


async def hems_test(request: web.Request) -> web.Response:
    """Live-Einzelabruf des HEMS-Status (Diagnose-Button) – meldet Fehler kontrolliert zurück."""
    collector = request.app.get("hems_status_collector")
    if collector is None:
        return web.json_response(
            {"connected": False, "reason": "HEMS nicht konfiguriert (hems_base_url leer)"},
            status=503,
        )
    result = await collector.test_fetch()
    status = 200 if result.get("ok") else 502
    return web.json_response(
        {"connected": result.get("ok", False), "result": result}, status=status
    )


async def hems_rediscover(request: web.Request) -> web.Response:
    """Manueller HEMS-Sync (Button im HEMS-Tab, D-046): erkennt die Geräte neu.

    Zieht die aktuelle HEMS-Geräteliste (D-036) und baut die Allowlist neu auf. Meldet
    Quelle und erkannte Geräte zurück; bei source "none" ist das HEMS nicht erreichbar
    oder liefert keine Geräte.
    """
    device_collector = request.app.get("device_collector")
    if device_collector is None:
        return web.json_response(
            {"source": "none", "device_count": 0, "devices": []}, status=503
        )
    devices, source = await rediscover_devices(request.app)
    return web.json_response(
        {
            "source": source,
            "device_count": len(devices),
            "devices": [d.name for d in devices],
        }
    )


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


async def prompt_get(request: web.Request) -> web.Response:
    """Liefert die aktuell wirksame Planungs-Instruktion + den Standard (für den Editor).

    `is_custom` zeigt an, ob ein eigener Prompt gespeichert ist; `default` ist der
    eingebaute Standard (zum Zurücksetzen/Vergleich).
    """
    db = request.app.get("db")
    custom = get_setting(db, PLANNING_PROMPT_KEY)
    return web.json_response(
        {
            "prompt": custom or DEFAULT_PLANNING_PROMPT,
            "is_custom": bool(custom),
            "default": DEFAULT_PLANNING_PROMPT,
        }
    )


async def prompt_post(request: web.Request) -> web.Response:
    """Speichert die editierte Planungs-Instruktion; leerer Text setzt auf Standard zurück.

    Der Datenblock und das JSON-Antwort-Schema bleiben code-kontrolliert und die harten
    Grenzen erzwingt der Validator unabhängig vom Prompt (Iron Rules 5/6).
    """
    db = request.app.get("db")
    if db is None:
        return web.json_response({"ok": False, "reason": "keine Datenbank"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "reason": "ungültiger Request-Body"}, status=400)
    prompt = str(body.get("prompt") or "").strip()
    if prompt:
        set_setting(db, PLANNING_PROMPT_KEY, prompt)
        action, is_custom = "prompt_updated", True
    else:
        delete_setting(db, PLANNING_PROMPT_KEY)
        action, is_custom = "prompt_reset", False
    _audit_prompt(db, action, len(prompt))
    return web.json_response({"ok": True, "is_custom": is_custom})


def _audit_prompt(
    db: sqlite3.Connection, action: str, length: int, *, subject: str = PLANNING_PROMPT_KEY
) -> None:
    """Protokolliert eine Prompt-Änderung (nur Länge, kein Volltext); blockiert nie.

    `subject` ist der globale Planungs-Prompt (Default) oder ein Gerätename (Geräte-Prompt, D-051).
    """
    try:
        db.execute(
            "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
            ("user", action, subject, f'{{"length": {length}}}'),
        )
        db.commit()
    except sqlite3.Error:  # pragma: no cover - Audit darf den Vorgang nie stören
        pass


def _safe_dumps(data: object) -> str:
    """JSON-Dump, der unbekannte Typen (z.B. ein datetime im Transparenz-`context`) zu ihrem
    String entschärft, statt den ganzen Endpoint mit einem 500 (HTML-Seite) zu sprengen.

    Nur ein Sicherheitsnetz für Diagnose-/Anzeigewerte (Iron Rule 8): der eigentliche Plan
    (`plan`) besteht aus validierten Primitivwerten und ist ohnehin JSON-sicher.
    """
    return json.dumps(data, ensure_ascii=False, default=str)


async def plan_run(request: web.Request) -> web.Response:
    """Stößt einen Planungslauf an (KI-Aufruf → Validierung → Persistenz, D-008/D-041).

    Liefert immer eine strukturierte Antwort (`ok` + Validierung + KI-Metadaten +
    gesendeter Kontext für Transparenz). Ist keine KI konfiguriert, kommt `ok=false`
    mit klarer Meldung – kein Crash (Iron Rule 8).
    """
    planner = request.app.get("planner")
    if planner is None:
        return web.json_response(
            {"ok": False, "error": "KI nicht konfiguriert (api_key fehlt)"}, status=503
        )
    # Iron Rule 8: NICHTS aus diesem Handler darf als HTTP-500 (HTML-Fehlerseite) nach außen
    # dringen – sonst scheitert im Frontend `response.json()` mit „SyntaxError: Unexpected
    # token '<'..." statt einer lesbaren Ursache. Deshalb liegen der Lauf UND die JSON-
    # Serialisierung der Antwort komplett im try: der Transparenz-`context` enthält beliebige
    # gelesene Werte, von denen einer (z.B. ein datetime aus einem Wetter-Slot) `json.dumps`
    # sprengen kann. `_safe_dumps` entschärft solche Typen zusätzlich zu ihrem String, damit
    # ein Diagnosewert nie die ganze Antwort blockiert; jeder verbleibende Fehler wird zu einer
    # garantiert serialisierbaren JSON-Antwort (klarer Text für die UI) + geloggtem Traceback.
    try:
        result = await planner.run()
        payload: dict[str, Any] = {
            "ok": result.ok,
            "plan": result.plan,
            "validation": result.validation,
            "ai_call": result.ai_call,
            "context": result.context,
            "published": result.published,
        }
        if result.error:
            payload["error"] = result.error
        return web.json_response(payload, dumps=_safe_dumps)
    except Exception as exc:  # noqa: BLE001 - bewusst breit (kontrollierte, lesbare Fehler)
        detail = f"{exc.__class__.__name__}: {exc}".strip()
        logger = request.app.get("logger")
        if logger is not None:
            logger.error(
                "Planungslauf abgebrochen (unerwarteter Fehler)",
                exc_info=exc,
                extra={"context": {"error": detail}},
            )
        # status=200: die UI soll die Meldung parsen und anzeigen können (kein erneuter
        # 500-JSON-Bruch). Konsistent damit, dass der Endpoint auch bei Validierungs-
        # ablehnungen `ok=false` mit HTTP 200 liefert.
        return web.json_response(
            {
                "ok": False,
                "error": detail,
                "validation": {"ok": False, "errors": [detail], "clamped": []},
            }
        )


async def plan_publish(request: web.Request) -> web.Response:
    """Schreibt den zuletzt gültigen Plan (erneut) als HA-`sensor.ep_*`-Vorschläge.

    Manueller Re-Publish-Button im Plan-Tab. Liefert das Schreibergebnis kontrolliert
    zurück (ohne gültigen Plan/HA-Client: `ok=false` mit Begründung, kein Crash).
    """
    planner = request.app.get("planner")
    if planner is None:
        return web.json_response(
            {"ok": False, "reason": "KI nicht konfiguriert (api_key fehlt)"}, status=503
        )
    try:
        result = await planner.publish_latest()
        return web.json_response(result, dumps=_safe_dumps)
    except Exception as exc:  # noqa: BLE001 - kontrollierte, lesbare Fehler (Iron Rule 8)
        logger = request.app.get("logger")
        if logger is not None:
            logger.error("Plan-Publish fehlgeschlagen", exc_info=exc)
        return web.json_response(
            {"ok": False, "reason": f"{exc.__class__.__name__}: {exc}"}
        )


async def plan_get(request: web.Request) -> web.Response:
    """Liefert den zuletzt erzeugten Plan inkl. Validierungsergebnis (read-only).

    Läuft beim Öffnen des Plan-Tabs. Ein Lesefehler (z.B. beschädigtes `plan_json`
    in der DB) darf hier nicht als HTTP-500 enden – sonst bricht im Frontend das
    `response.json()` genauso wie beim Lauf (Iron Rule 8). Fehler ⇒ `{plan: null}`.
    """
    planner = request.app.get("planner")
    if planner is None:
        return web.json_response({"plan": None})
    try:
        latest = planner.latest_plan()
        return web.json_response(latest or {"plan": None}, dumps=_safe_dumps)
    except Exception as exc:  # noqa: BLE001 - kontrollierte, lesbare Fehler (Iron Rule 8)
        logger = request.app.get("logger")
        if logger is not None:
            logger.error("Letzten Plan lesen fehlgeschlagen", exc_info=exc)
        return web.json_response({"plan": None, "error": f"{exc.__class__.__name__}: {exc}"})


async def ai_test(request: web.Request) -> web.Response:
    """Testet die KI-Verbindung (Mini-Aufruf) – meldet jeden Fehler kontrolliert zurück."""
    planner = request.app.get("planner")
    provider = getattr(planner, "provider", None) if planner is not None else None
    if provider is None:
        return web.json_response(
            {"connected": False, "reason": "KI nicht konfiguriert (api_key fehlt)"}, status=503
        )
    if not hasattr(provider, "test_connection"):
        return web.json_response(
            {"connected": False, "reason": "Provider unterstützt keinen Verbindungstest"},
            status=501,
        )
    try:
        result = await provider.test_connection()
        return web.json_response({"connected": True, "result": result})
    except Exception as exc:
        return web.json_response({"connected": False, "reason": str(exc)}, status=502)
