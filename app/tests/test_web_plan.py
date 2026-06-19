"""Tests für die Plan-Endpunkte (/api/plan/run, /api/plan, /api/ai/test)."""

import io

from energy_pilot.ai_provider import AIProvider, ProviderResponse
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.devices import CONTROLLABLE, Device
from energy_pilot.logging_setup import setup_logging
from energy_pilot.planner import Planner
from energy_pilot.web.server import create_app


class _FakeProvider(AIProvider):
    name = "fake"
    model = "fake-1"

    def __init__(self, data):
        self._data = data

    async def generate(self, prompt, response_schema):
        return ProviderResponse(data=self._data, tokens_in=5, tokens_out=7)

    async def close(self):
        return None

    async def test_connection(self):
        return {"model": self.model}


class _Devices:
    devices = [Device("batterie", "Batterie", "batterie", CONTROLLABLE, "watt")]
    last_values = {
        "batterie": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 0.0},
            "max_technisch": {"value": 5000.0},
        }
    }


def _app_with_planner(tmp_path, provider):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    planner = Planner(provider, config, db, device_collector=_Devices(), logger=logger)
    return create_app(config, db, ring, planner=planner, version="test")


async def test_plan_run_and_get(aiohttp_client, tmp_path):
    data = {
        "devices": [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 2000.0}],
        "confidence": 70,
        "reasoning": "ok",
        "warnings": [],
    }
    client = await aiohttp_client(_app_with_planner(tmp_path, _FakeProvider(data)))

    run = await (await client.post("/api/plan/run")).json()
    assert run["ok"] is True
    assert run["plan"]["devices"][0]["name"] == "batterie"
    assert run["ai_call"]["tokens_in"] == 5
    assert "context" in run  # Transparenz: gesendete Daten

    latest = await (await client.get("/api/plan")).json()
    assert latest["ok"] is True
    assert latest["plan"]["confidence"] == 70


async def test_ai_test_connected(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app_with_planner(tmp_path, _FakeProvider({"devices": []})))
    data = await (await client.get("/api/ai/test")).json()
    assert data["connected"] is True
    assert data["result"]["model"] == "fake-1"


async def test_plan_endpoints_without_planner(aiohttp_client, tmp_path):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    client = await aiohttp_client(create_app(config, db, ring, version="test"))  # kein Planner

    assert (await client.post("/api/plan/run")).status == 503
    assert (await client.get("/api/ai/test")).status == 503
    assert await (await client.get("/api/plan")).json() == {"plan": None}
