"""Tests für den Gemini-Provider (Fake-Session, keine echte Verbindung) + Rate-Limiter."""

import json

import pytest

from energy_pilot.ai_provider import AsyncRateLimiter, ProviderError, RateLimitError
from energy_pilot.gemini_provider import GeminiProvider


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
    return {
        "candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8},
    }


async def test_generate_parses_json_and_tokens():
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"confidence": 60, "devices": []})))
    provider = GeminiProvider("secret-key", model="gemini-x", session=session)

    resp = await provider.generate("hallo", {"type": "OBJECT"})

    assert resp.data["confidence"] == 60
    assert resp.tokens_in == 12
    assert resp.tokens_out == 8
    call = session.calls[0]
    assert call["url"].endswith("/models/gemini-x:generateContent")
    # Schlüssel geht per Header, nicht in der URL (taucht nicht in Zugriffs-Logs auf).
    assert call["headers"]["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in call["url"]


class _TimeoutResponse:
    async def __aenter__(self):
        raise TimeoutError  # aiohttp meldet den total-Timeout als asyncio.TimeoutError

    async def __aexit__(self, *exc):
        return False


class _TimeoutSession:
    def post(self, url, json=None, headers=None, timeout=None):
        return _TimeoutResponse()


async def test_generate_wraps_timeout_as_provider_error():
    # Regression: der total-Timeout (asyncio.TimeoutError) ist KEIN aiohttp.ClientError
    # und darf nicht mit leerer Meldung durchschlagen (sonst "error": "" im Planner-Log).
    provider = GeminiProvider("k", timeout_s=30, session=_TimeoutSession())
    with pytest.raises(ProviderError) as excinfo:
        await provider.generate("hi", {})
    assert "Zeitüberschreitung" in str(excinfo.value)
    assert str(excinfo.value).strip()  # nie leer


async def test_generate_raises_rate_limit_on_429():
    provider = GeminiProvider("k", session=_FakeSession(_FakeResponse(status=429, text="quota")))
    with pytest.raises(RateLimitError):
        await provider.generate("hi", {})


async def test_generate_raises_provider_error_on_http_error():
    provider = GeminiProvider("k", session=_FakeSession(_FakeResponse(status=500, text="boom")))
    with pytest.raises(ProviderError):
        await provider.generate("hi", {})


async def test_generate_raises_on_invalid_json():
    payload = {"candidates": [{"content": {"parts": [{"text": "kein json"}]}}]}
    provider = GeminiProvider("k", session=_FakeSession(_FakeResponse(payload=payload)))
    with pytest.raises(ProviderError):
        await provider.generate("hi", {})


async def test_generate_raises_on_empty_candidates():
    provider = GeminiProvider("k", session=_FakeSession(_FakeResponse(payload={"candidates": []})))
    with pytest.raises(ProviderError):
        await provider.generate("hi", {})


async def test_rate_limiter_no_wait_under_limit():
    limiter = AsyncRateLimiter(5, window_s=60.0)
    for _ in range(5):
        assert await limiter.acquire() == 0.0


async def test_rate_limiter_waits_when_over_limit():
    limiter = AsyncRateLimiter(1, window_s=0.05)
    assert await limiter.acquire() == 0.0
    assert await limiter.acquire() > 0.0
