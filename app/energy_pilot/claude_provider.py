"""Anthropic-Claude-Provider über die Messages-REST-API (D-056).

Direkter REST-Aufruf via aiohttp (Muster wie `gemini_provider.py`) – bewusst **ohne** schweres
SDK, konsistent mit der `AIProvider`-Abstraktion. Single-Shot: ein Prompt + JSON-Schema →
ein strukturiertes JSON-Objekt (`output_config.format`). Der API-Schlüssel steht ausschließlich
in der Addon-Config, wird per Header (`x-api-key`, nicht in der URL) gesendet und nie geloggt.

Determinismus: Claude-Modelle (Sonnet 5 / Opus 4.8 …) akzeptieren **kein** `temperature`/`seed`
mehr (400 bei Übergabe), daher werden diese Sampling-Parameter bewusst nicht gesetzt. Die harte
Grenze bleibt ohnehin der lokale Validator (Iron Rules 5/6).
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
from energy_pilot.http_errors import read_error_body
from energy_pilot.schema_convert import to_json_schema

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_TIMEOUT_S = 30.0
ANTHROPIC_VERSION = "2023-06-01"
# Oberes Ausgabe-Token-Limit je Aufruf (Claude verlangt `max_tokens`). Der Plan ist ein
# kompaktes JSON-Objekt (wenige Geräte, je ein paar Felder) – 8192 ist reichlich.
MAX_TOKENS = 8192


class ClaudeProvider(AIProvider):
    """Schlanker Async-Client für die Anthropic `messages`-REST-API."""

    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        rate_limit_per_min: int = 50,
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
        url = f"{self.base_url}/messages"
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
            # Strukturierte Ausgabe: das Gemini-Schema in Standard-JSON-Schema übersetzen.
            "output_config": {
                "format": {"type": "json_schema", "schema": to_json_schema(response_schema)}
            },
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            async with session.post(
                url, json=body, headers=headers, timeout=self._timeout
            ) as resp:
                if resp.status == 429:
                    detail = await read_error_body(resp)
                    suffix = f": {detail}" if detail else ""
                    raise RateLimitError(f"Claude-Rate-Limit erreicht (HTTP 429){suffix}")
                if resp.status >= 400:
                    detail = await read_error_body(resp)
                    suffix = f": {detail}" if detail else ""
                    raise ProviderError(f"Claude-Fehler HTTP {resp.status}{suffix}")
                payload = await resp.json()
        except TimeoutError as exc:
            # aiohttp meldet den total-Timeout als asyncio.TimeoutError (= TimeoutError, KEIN
            # ClientError). Ungefangen propagiert er mit leerer Meldung – deshalb klar benennen.
            total = self._timeout.total
            detail = f" nach {total:.0f}s" if total else ""
            raise ProviderError(f"Claude-Zeitüberschreitung{detail}") from exc
        except aiohttp.ClientError as exc:
            raise ProviderError(f"Claude-Verbindungsfehler: {exc}") from exc
        return self._parse(payload)

    def _parse(self, payload: dict) -> ProviderResponse:
        """Extrahiert das JSON-Objekt + Token-Zähler aus der Claude-Antwort.

        Bei `output_config.format` steht das JSON im ersten `text`-Content-Block.
        """
        blocks = payload.get("content")
        text = None
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    break
        if not isinstance(text, str):
            raise ProviderError("Claude-Antwort ohne verwertbaren Textinhalt")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Claude lieferte kein gültiges JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("Claude-JSON ist kein Objekt")
        usage = payload.get("usage") or {}
        return ProviderResponse(
            data=data,
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
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
