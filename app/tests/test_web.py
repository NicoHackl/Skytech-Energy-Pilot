"""Tests für den aiohttp-Webserver und die JSON-API."""

import io

import pytest

from energy_pilot.aggregation import RollingAggregator
from energy_pilot.collector import StateCollector
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
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


async def test_entities_get_returns_roles(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/entities")
    assert resp.status == 200
    payload = await resp.json()
    roles = {row["role"] for row in payload}
    assert "pv_power" in roles


async def test_entities_post_saves_mapping(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/entities",
        json={"role": "pv_power", "entity_id": "sensor.pv", "fallback_value": "0"},
    )
    assert resp.status == 200

    # Zuordnung ist anschließend über GET sichtbar
    payload = await (await client.get("/api/entities")).json()
    pv = next(row for row in payload if row["role"] == "pv_power")
    assert pv["entity_id"] == "sensor.pv"
    assert pv["fallback_value"] == 0.0


async def test_entities_post_rejects_unknown_role(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/api/entities", json={"role": "does_not_exist"})
    assert resp.status == 400
