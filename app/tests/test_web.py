"""Tests für den aiohttp-Webserver und die JSON-API."""

import io

import pytest

from energy_pilot.aggregation import RollingAggregator
from energy_pilot.allowlist import EntityAllowlist
from energy_pilot.collector import StateCollector
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.device_collector import DeviceCollector
from energy_pilot.entity_map import mapping_from_options
from energy_pilot.forecast import PVOrientation
from energy_pilot.forecast_collector import ForecastCollector
from energy_pilot.logging_setup import log, setup_logging
from energy_pilot.roles import MEASUREMENT_ROLES
from energy_pilot.web.server import create_app


@pytest.fixture
def app(tmp_path):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    log(logger, "info", "test-eintrag")
    db = init_db(str(tmp_path / "ep.db"))
    collector = StateCollector(None, RollingAggregator(), MEASUREMENT_ROLES, logger)
    # enable_poller bleibt False, damit Tests keine Hintergrundaufgabe starten
    return create_app(config, db, ring, ha_client=None, collector=collector, version="test")


async def test_index_serves_spa(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/")
    assert resp.status == 200
    assert "Skytech Energy Pilot" in await resp.text()


async def test_health_reports_config(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"
    assert data["model"] == "gemini-3.5-flash"
    assert data["ha_configured"] is False


async def test_logs_endpoint_returns_records(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/logs")
    assert resp.status == 200
    records = await resp.json()
    assert any(r["message"] == "test-eintrag" for r in records)


async def test_logs_export_is_ndjson(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/logs/export")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("application/x-ndjson")


async def test_ha_test_without_client_returns_503(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/ha/test")
    assert resp.status == 503
    data = await resp.json()
    assert data["connected"] is False


async def test_state_lists_all_roles(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert "pv_power" in data
    assert "battery_soc" in data


async def test_diagnostics_reports_status(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/diagnostics")
    assert resp.status == 200
    data = await resp.json()
    assert data["ha_configured"] is False
    assert data["poller_active"] is False
    assert "last_sources" in data


async def test_entities_get_reflects_configured_mapping(aiohttp_client, app):
    # Zuordnung kommt aus der Konfiguration und wird in den Collector geladen
    app["collector"].set_mapping(mapping_from_options({"entity_pv_power": "sensor.pv"}))
    client = await aiohttp_client(app)
    payload = await (await client.get("/api/entities")).json()
    pv = next(row for row in payload if row["role"] == "pv_power")
    assert pv["entity_id"] == "sensor.pv"


async def test_devices_endpoint_without_collector_is_empty(aiohttp_client, app):
    client = await aiohttp_client(app)
    data = await (await client.get("/api/devices")).json()
    assert data == {"source": "none", "devices": []}


class _FakeHEMSClient:
    """Minimaler HEMS-Client: liefert ein Geräteschema für die Start-Discovery im Test."""

    def __init__(self, schema):
        self._schema = schema

    async def device_schema(self):
        return self._schema

    async def close(self):
        pass


_HEIZSTAB_SCHEMA = [
    {
        "name": "heizstab", "label": "Heizstab",
        "items": [
            {"entity": "input_boolean.ems_heizstab_technische_freigabe"},
            {"entity": "input_number.ems_heizstab_min_technisch_w"},
            {"entity": "input_number.ems_heizstab_max_technisch_w"},
        ],
    },
]


async def test_devices_endpoint_reflects_hems_discovery(aiohttp_client, tmp_path):
    # Geräte werden beim Start ausschließlich aus dem HEMS-Schema erkannt (D-036/D-046).
    options = tmp_path / "options.json"
    options.write_text("{}")
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    app = create_app(
        config, db, ring, device_collector=device_collector,
        hems_client=_FakeHEMSClient(_HEIZSTAB_SCHEMA), version="test",
    )

    client = await aiohttp_client(app)
    data = await (await client.get("/api/devices")).json()

    assert data["source"] == "hems"
    heizstab = data["devices"][0]
    assert heizstab["name"] == "heizstab"
    keys = {f["key"] for f in heizstab["fields"]}
    assert {"technische_freigabe", "min_technisch", "max_technisch"} <= keys
    # Zusatz-Entitäten erscheinen separat (D-047), nicht in den Standard-`fields`.
    assert not any(k.startswith("extra_") for k in keys)
    # Der Heizstab-Default (ersetzt Hardcode D-035) wird beim ersten HEMS-Sync geseedet.
    extras = {e["read_entity_id"]: e for e in heizstab["extras"]}
    assert "input_number.ep_heizstab_max_temperatur" in extras
    seeded = extras["input_number.ep_heizstab_max_temperatur"]
    assert seeded["ai_suggestion"] is True
    assert seeded["suggestion_entity_id"] == "sensor.ep_heizstab_max_temperatur_vorschlag"


async def _discovered_client(aiohttp_client, tmp_path):
    """Startet die App mit HEMS-Heizstab-Discovery (inkl. Seed) und liefert (client, db)."""
    options = tmp_path / "options.json"
    options.write_text("{}")
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    app = create_app(
        config, db, ring, device_collector=device_collector,
        hems_client=_FakeHEMSClient(_HEIZSTAB_SCHEMA), version="test",
    )
    client = await aiohttp_client(app)  # on_startup: Discovery + Seed
    return client, db


async def test_device_extra_post_creates_and_lists(aiohttp_client, tmp_path):
    client, _ = await _discovered_client(aiohttp_client, tmp_path)
    res = await client.post("/api/devices/extras", json={
        "device_name": "heizstab",
        "read_entity_id": "input_number.min_soc_auto",
        "ai_suggestion": True,
        "ai_hint": "Minimaler Ladezustand",
        "unit": "%",
    })
    body = await res.json()
    assert res.status == 200 and body["ok"] is True
    assert body["suggestion_entity_id"] == "sensor.ep_min_soc_auto_vorschlag"

    data = await (await client.get("/api/devices")).json()
    extras = {e["read_entity_id"] for e in data["devices"][0]["extras"]}
    assert "input_number.min_soc_auto" in extras  # neu
    assert "input_number.ep_heizstab_max_temperatur" in extras  # Seed bleibt


async def test_device_extra_delete_removes(aiohttp_client, tmp_path):
    client, _ = await _discovered_client(aiohttp_client, tmp_path)
    res = await client.request("DELETE", "/api/devices/extras", json={
        "device_name": "heizstab",
        "read_entity_id": "input_number.ep_heizstab_max_temperatur",
    })
    assert (await res.json())["ok"] is True
    data = await (await client.get("/api/devices")).json()
    assert data["devices"][0]["extras"] == []


async def test_device_extra_post_rejects_unknown_device(aiohttp_client, tmp_path):
    client, _ = await _discovered_client(aiohttp_client, tmp_path)
    res = await client.post("/api/devices/extras", json={
        "device_name": "spuelmaschine", "read_entity_id": "input_number.x", "ai_suggestion": False,
    })
    assert res.status == 400


async def test_device_extra_post_rejects_invalid_entity(aiohttp_client, tmp_path):
    client, _ = await _discovered_client(aiohttp_client, tmp_path)
    res = await client.post("/api/devices/extras", json={
        "device_name": "heizstab", "read_entity_id": "keine_entity_id", "ai_suggestion": False,
    })
    assert res.status == 400


async def test_device_extra_post_rejects_suggestion_conflict(aiohttp_client, tmp_path):
    client, _ = await _discovered_client(aiohttp_client, tmp_path)
    # Gleiche object_id wie der Seed -> gleicher Vorschlags-Sensor -> Kollision (409).
    res = await client.post("/api/devices/extras", json={
        "device_name": "heizstab",
        "read_entity_id": "sensor.heizstab_max_temperatur",
        "ai_suggestion": True,
    })
    assert res.status == 409


async def test_hems_rediscover_endpoint_syncs_devices(aiohttp_client, tmp_path):
    # Manueller HEMS-Sync (D-046): erkennt die Geräte neu und meldet Quelle + Anzahl.
    options = tmp_path / "options.json"
    options.write_text("{}")
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    allowlist = EntityAllowlist(db, logger)
    app = create_app(
        config, db, ring, device_collector=device_collector, allowlist=allowlist,
        hems_client=_FakeHEMSClient(_HEIZSTAB_SCHEMA), version="test",
    )

    client = await aiohttp_client(app)
    data = await (await client.post("/api/hems/rediscover")).json()

    assert data["source"] == "hems"
    assert data["device_count"] == 1
    assert data["devices"] == ["heizstab"]
    # Der Sync baut die Allowlist neu auf – die HEMS-Geräteentitäten sind freigegeben.
    assert allowlist.is_allowed("input_boolean.ems_heizstab_technische_freigabe")


async def test_discovery_schedules_retry_when_hems_absent(aiohttp_client, tmp_path):
    # Boot-Reihenfolge (D-046): fehlt das HEMS beim Start, plant EP einen Auto-Retry ein,
    # statt dauerhaft ohne Geräte zu bleiben. Der Task wird beim Teardown sauber abgebrochen.
    options = tmp_path / "options.json"
    options.write_text("{}")
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    app = create_app(config, db, ring, device_collector=device_collector, version="test")

    await aiohttp_client(app)  # löst die Start-Discovery aus (kein HEMS -> source "none")

    assert device_collector.discovery_source == "none"
    task = app.get("_discovery_retry_task")
    assert task is not None and not task.done()


async def test_forecast_endpoint_without_collector_is_empty(aiohttp_client, app):
    client = await aiohttp_client(app)
    data = await (await client.get("/api/forecast")).json()
    assert data == {}


async def test_allowlist_endpoint_empty_without_allowlist(aiohttp_client, app):
    client = await aiohttp_client(app)
    data = await (await client.get("/api/allowlist")).json()
    assert data == {"count": 0, "by_source": {}, "entries": []}


async def test_allowlist_endpoint_and_diagnostics_count(aiohttp_client, tmp_path):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    allowlist = EntityAllowlist(db, logger)
    allowlist.register_all({"sensor.pv": "measurement"})
    app = create_app(config, db, ring, allowlist=allowlist, version="test")

    client = await aiohttp_client(app)
    data = await (await client.get("/api/allowlist")).json()
    assert data["count"] == 1
    assert data["entries"][0]["entity_id"] == "sensor.pv"

    diag = await (await client.get("/api/diagnostics")).json()
    assert diag["allowlist_count"] == 1


async def test_discovery_populates_and_persists_allowlist(aiohttp_client, tmp_path):
    # Beim Start erkennt EP Geräte und nimmt deren Lese-Entitäten in die Allowlist auf.
    options = tmp_path / "options.json"
    options.write_text("{}")
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    allowlist = EntityAllowlist(db, logger)
    app = create_app(
        config, db, ring, device_collector=device_collector, allowlist=allowlist,
        hems_client=_FakeHEMSClient(_HEIZSTAB_SCHEMA), version="test",
    )

    client = await aiohttp_client(app)  # löst die Geräte-Discovery (on_startup) aus
    data = await (await client.get("/api/allowlist")).json()

    ids = {e["entity_id"] for e in data["entries"]}
    assert "input_boolean.ems_heizstab_technische_freigabe" in ids
    # Register wurde nach der Discovery in der DB persistiert.
    persisted = db.execute("SELECT COUNT(*) AS n FROM allowlist").fetchone()["n"]
    assert persisted == data["count"]


async def test_objectives_endpoint_returns_defaults(aiohttp_client, app):
    client = await aiohttp_client(app)
    data = await (await client.get("/api/objectives")).json()
    weights = {o["key"]: o["weight"] for o in data["objectives"]}
    assert weights["versorgungssicherheit"] == 100
    assert weights["batterieschonung"] == 50


async def test_constraints_endpoint_without_collector_is_empty(aiohttp_client, app):
    client = await aiohttp_client(app)
    data = await (await client.get("/api/constraints")).json()
    assert data == {"devices": []}


async def test_constraints_endpoint_reflects_discovered_devices(aiohttp_client, tmp_path):
    options = tmp_path / "options.json"
    options.write_text("{}")
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    schema = [{
        "name": "batterie", "label": "Batterie",
        "items": [
            {"entity": "input_boolean.ems_batterie_technische_freigabe"},
            {"entity": "input_number.ems_batterie_min_technisch_w"},
            {"entity": "input_number.ems_batterie_max_technisch_w"},
        ],
    }]
    app = create_app(
        config, db, ring, device_collector=device_collector,
        hems_client=_FakeHEMSClient(schema), version="test",
    )

    client = await aiohttp_client(app)  # löst die Geräte-Discovery (on_startup) aus
    data = await (await client.get("/api/constraints")).json()

    battery = data["devices"][0]
    assert battery["name"] == "batterie"
    assert battery["is_battery"] is True
    assert battery["suggestion_keys"] == ["geschutzte_mindestleistung_w_vorschlag"]


async def test_constraints_endpoint_exposes_class_key_for_ui(aiohttp_client, tmp_path):
    # Regression: das UI (loadConstraints) entscheidet über `d.class` zwischen
    # Binär ("Feste Leistung") und Regelbar ("Min./Max. Leistung"). Der Endpunkt
    # muss die Geräteklasse als `class` liefern (nicht als Dataclass-Feld
    # `device_class`), sonst greift der Binär-Zweig nie und Binärgeräte zeigen
    # fälschlich Min./Max.-Leistung an.
    options = tmp_path / "options.json"
    options.write_text("{}")
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    schema = [{
        "name": "heizluefter_1", "label": "Heizlüfter 1",
        "items": [
            {"entity": "input_boolean.ems_heizluefter_1_technische_freigabe"},
            {"entity": "input_number.ems_heizluefter_1_leistung_w"},
        ],
    }]
    app = create_app(
        config, db, ring, device_collector=device_collector,
        hems_client=_FakeHEMSClient(schema), version="test",
    )

    client = await aiohttp_client(app)
    data = await (await client.get("/api/constraints")).json()

    device = data["devices"][0]
    assert device["class"] == "binary"
    assert "device_class" not in device


async def test_plan_schema_endpoint_is_versioned(aiohttp_client, app):
    client = await aiohttp_client(app)
    data = await (await client.get("/api/plan/schema")).json()
    assert data["schema_version"] == "1.0"
    assert "devices" in data["schema"]["properties"]


async def test_forecast_endpoint_returns_totals(aiohttp_client, tmp_path):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    forecast_collector = ForecastCollector(None, logger, unit="kWh")
    forecast_collector.set_orientations([PVOrientation("Ost", {"current_hour": "sensor.ost"})])
    app = create_app(config, db, ring, forecast_collector=forecast_collector, version="test")

    client = await aiohttp_client(app)
    data = await (await client.get("/api/forecast")).json()

    assert data["unit"] == "kWh"
    assert any(v["key"] == "current_hour" for v in data["values"])
    assert data["orientations"][0]["label"] == "Ost"
