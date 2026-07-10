"""Tests für die gemeinsame HTTP-Fehlerbehandlung (Original-Servermeldung mitnehmen)."""

import pytest

from energy_pilot.http_errors import (
    MAX_BODY_CHARS,
    HTTPStatusError,
    message_from_json,
    raise_for_status,
    read_error_body,
)


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeResponse:
    def __init__(self, *, status=200, text="", reason="OK", path="/api/x"):
        self.status = status
        self._text = text
        self.reason = reason
        self.url = _FakeURL(path)

    async def text(self):
        return self._text


def test_message_from_json_flat_message():
    assert message_from_json({"message": "Entity not found."}) == "Entity not found."


def test_message_from_json_nested_error_message():
    # Gemini/Google-Shape: {"error": {"message": …}}
    assert message_from_json({"error": {"message": "API key invalid"}}) == "API key invalid"


def test_message_from_json_error_as_string():
    assert message_from_json({"error": "quota exceeded"}) == "quota exceeded"


def test_message_from_json_returns_none_without_usable_field():
    assert message_from_json({"cod": 500}) is None
    assert message_from_json("kein dict") is None


async def test_read_error_body_prefers_structured_message():
    resp = _FakeResponse(text='{"cod": 401, "message": "Invalid API key."}')
    assert await read_error_body(resp) == "Invalid API key."


async def test_read_error_body_falls_back_to_raw_text():
    resp = _FakeResponse(text="plain text error")
    assert await read_error_body(resp) == "plain text error"


async def test_read_error_body_truncates_long_bodies():
    resp = _FakeResponse(text="x" * (MAX_BODY_CHARS + 50))
    body = await read_error_body(resp)
    assert len(body) == MAX_BODY_CHARS + 1  # gekürzt + Ellipsis
    assert body.endswith("…")


async def test_read_error_body_empty_stays_empty():
    assert await read_error_body(_FakeResponse(text="")) == ""


async def test_raise_for_status_noop_below_400():
    await raise_for_status(_FakeResponse(status=200), service="HA")  # wirft nicht


async def test_raise_for_status_includes_service_status_path_and_message():
    resp = _FakeResponse(
        status=404, reason="Not Found", path="/api/status",
        text='{"message": "Regelzyklus fehlt"}',
    )
    with pytest.raises(HTTPStatusError) as exc:
        await raise_for_status(resp, service="HEMS")

    err = exc.value
    assert err.service == "HEMS"
    assert err.status == 404
    assert err.reason == "Not Found"
    assert err.path == "/api/status"
    assert err.server_message == "Regelzyklus fehlt"
    text = str(err)
    assert text == "HEMS: HTTP 404 Not Found (/api/status) – Regelzyklus fehlt"


async def test_raise_for_status_without_body_is_still_clear():
    resp = _FakeResponse(status=500, reason="Internal Server Error", path="/api/x", text="")
    with pytest.raises(HTTPStatusError) as exc:
        await raise_for_status(resp, service="Home Assistant")
    assert str(exc.value) == "Home Assistant: HTTP 500 Internal Server Error (/api/x)"
