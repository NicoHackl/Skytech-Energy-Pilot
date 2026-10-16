"""Tests für den Link im Sidebar-Fuß auf die HA-Konfigurationsseite (D-068)."""

import io

import pytest
from aiohttp import web

from energy_pilot import addon_link
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.logging_setup import setup_logging
from energy_pilot.web.server import create_app

INFO = {"slug": "03f1563e_skytech_energy_pilot_dev", "name": "Skytech Energy Pilot (Dev)"}


def test_link_nutzt_slug_mit_repository_praefix_und_namen():
    assert addon_link.link_from_info(INFO) == {
        "name": "Skytech Energy Pilot (Dev)",
        "config_path": "/config/app/03f1563e_skytech_energy_pilot_dev/config",
    }


@pytest.mark.parametrize("slug", ["", "../../evil", "Skytech"])
def test_ungueltiger_slug_wird_nicht_zum_pfad(slug):
    assert addon_link.link_from_info({"slug": slug, "name": "x"}) is None


async def _fake_supervisor(aiohttp_server, status=200, body=None):
    seen: dict = {}

    async def self_info(request: web.Request) -> web.Response:
        seen["auth"] = request.headers.get("Authorization")
        payload = body if body is not None else {"result": "ok", "data": INFO}
        return web.json_response(payload, status=status)

    app = web.Application()
    app.router.add_get("/addons/self/info", self_info)
    server = await aiohttp_server(app)
    return str(server.make_url("/addons/self/info")), seen


async def test_fetch_liest_den_supervisor_mit_token(aiohttp_server):
    url, seen = await _fake_supervisor(aiohttp_server)
    link = await addon_link.fetch("geheim", url=url)
    assert link is not None
    assert link["config_path"] == "/config/app/03f1563e_skytech_energy_pilot_dev/config"
    assert seen["auth"] == "Bearer geheim"


async def test_fetch_ohne_token_fragt_nicht():
    assert await addon_link.fetch(None, url="http://127.0.0.1:9/nie") is None


async def test_fetch_bei_verweigerung_ohne_link(aiohttp_server):
    url, _ = await _fake_supervisor(aiohttp_server, status=403, body={"result": "error"})
    assert await addon_link.fetch("geheim", url=url) is None


async def test_fetch_bei_nicht_erreichbarem_supervisor_ohne_link():
    assert await addon_link.fetch("geheim", url="http://127.0.0.1:9/addons/self/info") is None


async def test_endpunkt_merkt_nur_den_erfolg(aiohttp_client, tmp_path, monkeypatch):
    antworten = [None, dict(addon_link.link_from_info(INFO))]
    aufrufe = []

    async def fake_fetch(token, logger=None):
        aufrufe.append(token)
        return antworten[min(len(aufrufe) - 1, 1)]

    monkeypatch.setattr(addon_link, "fetch", fake_fetch)
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    app = create_app(config, init_db(str(tmp_path / "ep.db")), ring, version="test", logger=logger)
    client = await aiohttp_client(app)

    erste = await (await client.get("/api/addon")).json()
    assert erste == {"name": "Skytech Energy Pilot", "config_path": None}
    zweite = await (await client.get("/api/addon")).json()
    assert zweite["name"] == "Skytech Energy Pilot (Dev)"
    await client.get("/api/addon")
    assert len(aufrufe) == 2
