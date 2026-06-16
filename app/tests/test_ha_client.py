"""Tests für den HA-Connector ohne echte Netzwerkverbindung (Fake-Session)."""

import pytest

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

    def get(self, url, headers=None):
        self.urls.append(url)
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
