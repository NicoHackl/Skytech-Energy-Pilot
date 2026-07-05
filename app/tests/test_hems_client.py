"""Tests für den HEMS-Connector (Fake-Session, keine echte Verbindung)."""

import pytest

from energy_pilot.hems_client import HEMSClient
from energy_pilot.http_errors import HTTPStatusError


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeResponse:
    def __init__(self, payload, status=200, text="", reason="OK", path="/api/status"):
        self._payload = payload
        self.status = status
        self._text = text
        self.reason = reason
        self.url = _FakeURL(path)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class _FakeSession:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self._status = status
        self._text = text
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return _FakeResponse(self._payload, self._status, self._text, path=url)


def test_base_url_is_normalized():
    client = HEMSClient(base_url="http://local_skytech_hems:8099/")
    assert client.base_url == "http://local_skytech_hems:8099"


@pytest.mark.asyncio
async def test_device_schema_calls_endpoint():
    schema = [{"label": "Heizstab", "items": []}]
    session = _FakeSession(schema)
    client = HEMSClient("http://hems:8099", session=session)

    result = await client.device_schema()

    assert result == schema
    assert session.urls[0].endswith("/api/device_controls_schema")


@pytest.mark.asyncio
async def test_device_schema_raises_on_error_status():
    session = _FakeSession({}, status=502, text="Bad Gateway")
    client = HEMSClient("http://hems:8099", session=session)

    with pytest.raises(HTTPStatusError) as exc:
        await client.device_schema()

    assert exc.value.status == 502
    assert "HEMS" in str(exc.value)
    assert "502" in str(exc.value)


@pytest.mark.asyncio
async def test_status_calls_endpoint():
    payload = {"status": {"pool_w": 1000.0, "devices": []}, "cycle_count": 7}
    session = _FakeSession(payload)
    client = HEMSClient("http://hems:8099", session=session)

    result = await client.status()

    assert result == payload
    assert session.urls[0].endswith("/api/status")


@pytest.mark.asyncio
async def test_controls_calls_endpoint():
    payload = {"input_number.ems_heizstab_min_technisch_w": {"state": "500"}}
    session = _FakeSession(payload)
    client = HEMSClient("http://hems:8099", session=session)

    result = await client.controls()

    assert result == payload
    assert session.urls[0].endswith("/api/controls")


@pytest.mark.asyncio
async def test_status_raises_on_error_status_with_server_message():
    # 5XX mit JSON-Body: die HEMS-Meldung + der Endpunkt-Pfad landen in der Fehlermeldung.
    session = _FakeSession({}, status=500, text='{"message": "Regelzyklus abgestürzt"}')
    client = HEMSClient("http://hems:8099", session=session)

    with pytest.raises(HTTPStatusError) as exc:
        await client.status()

    assert exc.value.server_message == "Regelzyklus abgestürzt"
    assert exc.value.path.endswith("/api/status")
    assert "Regelzyklus abgestürzt" in str(exc.value)
