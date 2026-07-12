"""Tests für den OpenAI-Provider (Fake-Session, keine echte Verbindung), D-056."""

import json

import pytest

from energy_pilot.ai_provider import ProviderError, RateLimitError
from energy_pilot.openai_provider import OpenAIProvider


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
    """Liefert je `post()` die nächste vorbereitete Antwort (für den Retry-Test)."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]


def _ok_payload(data):
    return {
        "choices": [{"message": {"content": json.dumps(data)}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
    }


async def test_generate_parses_json_and_tokens():
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"confidence": 60, "devices": []})))
    provider = OpenAIProvider("secret-key", model="gpt-x", session=session)

    resp = await provider.generate("hallo", {"type": "OBJECT", "properties": {}})

    assert resp.data["confidence"] == 60
    assert resp.tokens_in == 5
    assert resp.tokens_out == 7
    call = session.calls[0]
    assert call["url"].endswith("/chat/completions")
    # Schlüssel im Authorization-Header, nicht in der URL.
    assert call["headers"]["Authorization"] == "Bearer secret-key"
    assert "secret-key" not in call["url"]
    # Strict-Structured-Output mit vollständigem required (all_required).
    js = call["json"]["response_format"]["json_schema"]
    assert js["strict"] is True


async def test_generate_sends_temperature_and_seed():
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = OpenAIProvider("k", temperature=0.0, seed=42, session=session)
    await provider.generate("hi", {"type": "OBJECT"})
    body = session.calls[0]["json"]
    assert body["temperature"] == 0.0
    assert body["seed"] == 42


async def test_retries_without_sampling_on_unsupported_temperature():
    # Reasoning-Modelle (gpt-5) lehnen feste temperature ab → einmalig ohne wiederholen.
    err_body = json.dumps({"error": {"message": "Unsupported value: 'temperature' ..."}})
    session = _FakeSession(
        _FakeResponse(status=400, text=err_body),
        _FakeResponse(payload=_ok_payload({"devices": []})),
    )
    provider = OpenAIProvider("k", temperature=0.0, seed=42, session=session)

    resp = await provider.generate("hi", {"type": "OBJECT"})

    assert resp.data == {"devices": []}
    assert len(session.calls) == 2
    # Erster Aufruf mit, zweiter ohne Sampling-Parameter.
    assert "temperature" in session.calls[0]["json"]
    assert "temperature" not in session.calls[1]["json"]
    assert "seed" not in session.calls[1]["json"]


async def test_non_sampling_400_is_not_retried():
    err_body = json.dumps({"error": {"message": "invalid api key"}})
    session = _FakeSession(_FakeResponse(status=400, text=err_body))
    provider = OpenAIProvider("k", temperature=0.0, seed=42, session=session)
    with pytest.raises(ProviderError):
        await provider.generate("hi", {"type": "OBJECT"})
    assert len(session.calls) == 1  # kein Retry


async def test_generate_raises_rate_limit_on_429():
    provider = OpenAIProvider("k", session=_FakeSession(_FakeResponse(status=429, text="quota")))
    with pytest.raises(RateLimitError):
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
    provider = OpenAIProvider("k", timeout_s=30, session=_TimeoutSession())
    with pytest.raises(ProviderError) as excinfo:
        await provider.generate("hi", {})
    assert "Zeitüberschreitung" in str(excinfo.value)
    assert str(excinfo.value).strip()
