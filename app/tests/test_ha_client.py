"""Tests für den HA-Connector ohne echte Netzwerkverbindung (Fake-Session)."""

import pytest

from energy_pilot.allowlist import SOURCE_MEASUREMENT, EntityAllowlist
from energy_pilot.database import init_db
from energy_pilot.ha_client import HAClient


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.urls = []
        self.posts = []

    def get(self, url, headers=None):
        self.urls.append(url)
        return _FakeResponse(self._payload)

    def post(self, url, headers=None, json=None):
        self.urls.append(url)
        self.posts.append({"url": url, "json": json})
        return _FakeResponse(self._payload)


def test_headers_and_base_url_normalization():
    client = HAClient(token="abc", base_url="http://supervisor/core/api/")
    assert client.headers["Authorization"] == "Bearer abc"
    assert client.base_url == "http://supervisor/core/api"


@pytest.mark.asyncio
async def test_test_connection_calls_api_root():
    session = _FakeSession({"message": "API running."})
    client = HAClient(token="t", session=session)

    result = await client.test_connection()

    assert result["message"] == "API running."
    assert session.urls[0].endswith("/api/")


@pytest.mark.asyncio
async def test_get_state_builds_entity_url():
    session = _FakeSession({"state": "1234"})
    client = HAClient(token="t", session=session)

    result = await client.get_state("sensor.pv_leistung")

    assert result["state"] == "1234"
    assert session.urls[0].endswith("/states/sensor.pv_leistung")


@pytest.mark.asyncio
async def test_set_state_posts_state_and_attributes():
    session = _FakeSession({"entity_id": "sensor.ep_heizstab_prio_vorschlag", "state": "10"})
    client = HAClient(token="t", session=session)

    result = await client.set_state(
        "sensor.ep_heizstab_prio_vorschlag", "10", {"unit_of_measurement": "W"}
    )

    assert result["state"] == "10"
    assert session.posts[0]["url"].endswith("/states/sensor.ep_heizstab_prio_vorschlag")
    assert session.posts[0]["json"] == {"state": "10", "attributes": {"unit_of_measurement": "W"}}


@pytest.mark.asyncio
async def test_set_state_omits_attributes_when_none():
    session = _FakeSession({"state": "on"})
    client = HAClient(token="t", session=session)

    await client.set_state("sensor.ep_heizstab_freigabe_vorschlag", "on")

    assert session.posts[0]["json"] == {"state": "on"}


@pytest.mark.asyncio
async def test_get_state_allowed_entity_passes_guard():
    allow = EntityAllowlist()
    allow.register_all({"sensor.pv_leistung": SOURCE_MEASUREMENT})
    session = _FakeSession({"state": "1"})
    client = HAClient(token="t", session=session, allowlist=allow)

    result = await client.get_state("sensor.pv_leistung")

    assert result["state"] == "1"


@pytest.mark.asyncio
async def test_get_state_soft_guard_does_not_block_unlisted_entity():
    # Nicht freigegebene Entität: Read läuft trotzdem (soft), Verstoß wird auditiert.
    conn = init_db(":memory:")
    allow = EntityAllowlist(conn)
    session = _FakeSession({"state": "1"})
    client = HAClient(token="t", session=session, allowlist=allow)

    result = await client.get_state("sensor.verboten")

    assert result["state"] == "1"
    violations = conn.execute(
        "SELECT COUNT(*) AS n FROM audit WHERE action = 'allowlist_violation'"
    ).fetchone()["n"]
    assert violations == 1
    conn.close()
