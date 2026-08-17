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


async def test_generate_sends_temperature_and_seed():
    # D-050: Determinismus-Parameter landen in der generationConfig (stabile Ausgabefelder).
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = GeminiProvider("k", temperature=0.0, seed=42, session=session)

    await provider.generate("hi", {"type": "OBJECT"})

    gen = session.calls[0]["json"]["generationConfig"]
    assert gen["temperature"] == 0.0
    assert gen["seed"] == 42
    assert gen["responseMimeType"] == "application/json"


async def test_generate_omits_determinism_when_unset():
    # temperature=None/seed=None => Felder weglassen (Provider-Default greift).
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = GeminiProvider("k", temperature=None, seed=None, session=session)

    await provider.generate("hi", {"type": "OBJECT"})

    gen = session.calls[0]["json"]["generationConfig"]
    assert "temperature" not in gen
    assert "seed" not in gen


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


async def test_generate_sends_instruction_as_system_channel():
    """D-062: Instruktion und Daten in getrennten Kanälen, nicht in einer User-Nachricht."""
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = GeminiProvider("k", session=session)

    await provider.generate("Daten:\n{}", {"type": "OBJECT"}, system="ROLLE UND REGELN")

    body = session.calls[0]["json"]
    assert body["systemInstruction"] == {"parts": [{"text": "ROLLE UND REGELN"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Daten:\n{}"}]}]


async def test_generate_omits_system_channel_when_empty():
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = GeminiProvider("k", session=session)

    await provider.generate("nur Daten", {"type": "OBJECT"}, system="   ")

    assert "systemInstruction" not in session.calls[0]["json"]


async def test_generate_sends_thinking_budget_when_configured():
    """D-063: Denkbudget explizit setzen – Thinking ist bei Flash-Modellen eine Varianzquelle."""
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = GeminiProvider("k", thinking_budget=0, session=session)

    await provider.generate("hi", {"type": "OBJECT"})

    assert session.calls[0]["json"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


async def test_generate_omits_thinking_budget_when_unset():
    session = _FakeSession(_FakeResponse(payload=_ok_payload({"devices": []})))
    provider = GeminiProvider("k", thinking_budget=None, session=session)

    await provider.generate("hi", {"type": "OBJECT"})

    assert "thinkingConfig" not in session.calls[0]["json"]["generationConfig"]
