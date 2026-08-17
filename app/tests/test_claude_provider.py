"""Tests für den Claude-Provider (Fake-Session, keine echte Verbindung), D-056."""

import pytest

from energy_pilot.ai_provider import ProviderError, RateLimitError
from energy_pilot.claude_provider import ClaudeProvider


class _FakeResponse:
    def __init__(self, *, status=200, payload=None, text=""):
        self.status = status
        self._payload = payload
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._response


def _ok_payload(data):
    import json as _json
    return {
        "content": [{"type": "text", "text": _json.dumps(data)}],
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


async def test_generate_parses_json_and_tokens():
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"confidence": 60, "devices": []})))
    provider = ClaudeProvider("secret-key", model="claude-x", session=session)

    resp = await provider.generate("hallo", {"type": "OBJECT", "properties": {}})

    assert resp.data["confidence"] == 60
    assert resp.tokens_in == 12
    assert resp.tokens_out == 8
    call = session.calls[0]
    assert call["url"].endswith("/messages")
    # Schlüssel per Header, nicht in der URL.
    assert call["headers"]["x-api-key"] == "secret-key"
    assert call["headers"]["anthropic-version"]
    assert "secret-key" not in call["url"]
    # Strukturierte Ausgabe: Standard-JSON-Schema unter output_config.format.
    fmt = call["json"]["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert call["json"]["max_tokens"] > 0
    # Claude sendet KEINE Sampling-Parameter (400 auf modernen Modellen).
    assert "temperature" not in call["json"]
    assert "seed" not in call["json"]


async def test_generate_picks_first_text_block():
    payload = {
        "content": [
            {"type": "thinking", "thinking": "…"},
            {"type": "text", "text": "{\"ok\": true}"},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    provider = ClaudeProvider("k", session=_FakeSession(_FakeResponse(payload=payload)))
    resp = await provider.generate("hi", {"type": "OBJECT"})
    assert resp.data == {"ok": True}


async def test_generate_raises_rate_limit_on_429():
    provider = ClaudeProvider("k", session=_FakeSession(_FakeResponse(status=429, text="quota")))
    with pytest.raises(RateLimitError):
        await provider.generate("hi", {})


async def test_generate_raises_provider_error_on_http_error():
    provider = ClaudeProvider("k", session=_FakeSession(_FakeResponse(status=500, text="boom")))
    with pytest.raises(ProviderError):
        await provider.generate("hi", {})


class _TimeoutResponse:
    async def __aenter__(self):
        raise TimeoutError

    async def __aexit__(self, *exc):
        return False


class _TimeoutSession:
    def post(self, url, json=None, headers=None, timeout=None):
        return _TimeoutResponse()


async def test_generate_wraps_timeout_as_provider_error():
    provider = ClaudeProvider("k", timeout_s=30, session=_TimeoutSession())
    with pytest.raises(ProviderError) as excinfo:
        await provider.generate("hi", {})
    assert "Zeitüberschreitung" in str(excinfo.value)
    assert str(excinfo.value).strip()


async def test_generate_sends_instruction_as_system_field():
    """D-062: Instruktion im `system`-Feld der Messages-API, Daten als User-Nachricht."""
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = ClaudeProvider("k", session=session)

    await provider.generate("Daten:\n{}", {"type": "OBJECT"}, system="ROLLE UND REGELN")

    body = session.calls[0]["json"]
    assert body["system"] == "ROLLE UND REGELN"
    assert body["messages"] == [{"role": "user", "content": "Daten:\n{}"}]


async def test_generate_omits_system_field_when_empty():
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = ClaudeProvider("k", session=session)
    await provider.generate("nur Daten", {"type": "OBJECT"}, system="")
    assert "system" not in session.calls[0]["json"]
