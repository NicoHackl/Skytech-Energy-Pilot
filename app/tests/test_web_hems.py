"""Tests für die HEMS-Status-Endpunkte (/api/hems/status, /api/hems/test)."""

import io

from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.logging_setup import setup_logging
from energy_pilot.web.server import create_app


class _FakeStatusCollector:
    configured = True
    online = True
    last_fetch_ts = 100.0
    last_error = None
    last_feedback = {"overall": "beobachtet_konform", "devices": []}

    def snapshot(self):
        return {"configured": True, "online": True, "pool_w": 1000.0, "devices": []}

    async def test_fetch(self):
        return {"ok": True, "cycle_count": 5, "feedback": self.last_feedback}


def _app(tmp_path, collector=None):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    _, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    return create_app(config, db, ring, hems_status_collector=collector, version="test")


async def test_hems_status_without_collector(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.get("/api/hems/status")
    assert resp.status == 200
    data = await resp.json()
    assert data["configured"] is False
    assert data["feedback"] is None


async def test_hems_status_with_collector(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path, _FakeStatusCollector()))
    resp = await client.get("/api/hems/status")
    data = await resp.json()
    assert data["online"] is True
    assert data["pool_w"] == 1000.0
    assert data["feedback"]["overall"] == "beobachtet_konform"


async def test_hems_test_without_collector_is_503(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.get("/api/hems/test")
    assert resp.status == 503
    data = await resp.json()
    assert data["connected"] is False


async def test_hems_test_with_collector(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path, _FakeStatusCollector()))
    resp = await client.get("/api/hems/test")
    assert resp.status == 200
    data = await resp.json()
    assert data["connected"] is True
    assert data["result"]["cycle_count"] == 5
