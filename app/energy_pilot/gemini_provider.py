"""Google-Gemini-Provider über die REST-API (D-007/D-025/D-041).

Direkter REST-Aufruf via aiohttp (Muster wie `hems_client.py`) – bewusst **ohne**
schweres SDK. Single-Shot: ein Prompt + `responseSchema` → ein strukturiertes
JSON-Objekt. Der API-Schlüssel steht ausschließlich in der Addon-Config, wird per
Header (nicht in der URL) gesendet und nie geloggt (Doc 04, info.md §13).
"""

from __future__ import annotations

import json

import aiohttp

from energy_pilot.ai_provider import (
    AIProvider,
    AsyncRateLimiter,
    ProviderError,
    ProviderResponse,
    RateLimitError,
)

# Öffentliche Gemini-REST-Basis; im Konstruktor überschreibbar (Tests/OpenAI-kompatibel).
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT_S = 30.0


class GeminiProvider(AIProvider):
    """Schlanker Async-Client für die Gemini `generateContent`-REST-API."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        rate_limit_per_min: int = 10,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._limiter = AsyncRateLimiter(rate_limit_per_min)
        self._session = session
        self._owns_session = session is None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Schließt die selbst angelegte Session (nicht eine injizierte)."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def generate(self, prompt: str, response_schema: dict) -> ProviderResponse:
        await self._limiter.acquire()
        session = await self._ensure_session()
        url = f"{self.base_url}/models/{self.model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }
        # Schlüssel als Header (nicht in der URL) → erscheint nicht in Zugriffs-/Proxy-Logs.
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        try:
            async with session.post(
                url, json=body, headers=headers, timeout=self._timeout
            ) as resp:
                if resp.status == 429:
                    raise RateLimitError("Gemini-Rate-Limit erreicht (HTTP 429)")
                if resp.status >= 400:
                    text = await resp.text()
                    raise ProviderError(f"Gemini-Fehler HTTP {resp.status}: {text[:200]}")
                payload = await resp.json()
        except TimeoutError as exc:
            # aiohttp meldet den total-Timeout als asyncio.TimeoutError (= TimeoutError) –
            # das ist KEIN ClientError. Ungefangen propagiert es mit leerer Meldung bis in
            # den Planner-Log (`str(TimeoutError())` == ""); deshalb hier klar benennen.
            total = self._timeout.total
            detail = f" nach {total:.0f}s" if total else ""
            raise ProviderError(f"Gemini-Zeitüberschreitung{detail}") from exc
        except aiohttp.ClientError as exc:
            raise ProviderError(f"Gemini-Verbindungsfehler: {exc}") from exc
        return self._parse(payload)

    def _parse(self, payload: dict) -> ProviderResponse:
        """Extrahiert das JSON-Objekt + Token-Zähler aus der Gemini-Antwort."""
        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini-Antwort ohne verwertbaren Inhalt") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Gemini lieferte kein gültiges JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("Gemini-JSON ist kein Objekt")
        usage = payload.get("usageMetadata") or {}
        return ProviderResponse(
            data=data,
            tokens_in=usage.get("promptTokenCount"),
            tokens_out=usage.get("candidatesTokenCount"),
            raw=payload,
        )

    async def test_connection(self) -> dict:
        """Leichter Verbindungstest (Mini-Prompt) für die UI – prüft Schlüssel/Erreichbarkeit."""
        schema = {
            "type": "OBJECT",
            "properties": {"ok": {"type": "BOOLEAN"}},
            "required": ["ok"],
        }
        resp = await self.generate('Antworte ausschließlich mit JSON {"ok": true}.', schema)
        return {
            "model": self.model,
            "tokens_in": resp.tokens_in,
            "tokens_out": resp.tokens_out,
        }
