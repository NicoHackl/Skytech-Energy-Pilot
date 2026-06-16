"""Tests für den aiohttp-Webserver und die JSON-API."""

import io

import pytest

from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.logging_setup import log, setup_logging
from energy_pilot.web.server import create_app


@pytest.fixture
def app(tmp_path):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    log(logger, "info", "test-eintrag")
    db = init_db(str(tmp_path / "ep.db"))
    return create_app(config, db, ring, ha_client=None, version="test")


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
