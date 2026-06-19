"""Tests für den aiohttp-Webserver und die JSON-API."""

import io
import json

import pytest

from energy_pilot.aggregation import RollingAggregator
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


async def test_devices_endpoint_reflects_config_discovery(aiohttp_client, tmp_path):
    # Geräte werden beim Start aus der Config erkannt (HEMS nicht gesetzt -> Fallback).
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"devices": [{"name": "heizstab", "class": "controllable"}]}))
    config = AddonConfig.load(options_path=str(options), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    device_collector = DeviceCollector(None, logger)
    app = create_app(config, db, ring, device_collector=device_collector, version="test")

    client = await aiohttp_client(app)
    data = await (await client.get("/api/devices")).json()

    assert data["source"] == "config"
    assert data["devices"][0]["name"] == "heizstab"
    keys = {f["key"] for f in data["devices"][0]["fields"]}
    assert {"technische_freigabe", "min_technisch", "max_technisch", "ep_max_temperatur"} <= keys


async def test_forecast_endpoint_without_collector_is_empty(aiohttp_client, app):
    client = await aiohttp_client(app)
    data = await (await client.get("/api/forecast")).json()
    assert data == {}


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
