"""OpenAI-(GPT-)Provider über die Chat-Completions-REST-API (D-056).

Direkter REST-Aufruf via aiohttp (Muster wie `gemini_provider.py`) – bewusst **ohne** schweres
SDK, konsistent mit der `AIProvider`-Abstraktion. Single-Shot: ein Prompt + JSON-Schema →
ein strukturiertes JSON-Objekt (`response_format` mit `json_schema`, Strict-Mode). Der
API-Schlüssel steht ausschließlich in der Addon-Config, wird per `Authorization`-Header (nicht
in der URL) gesendet und nie geloggt.

Determinismus: `temperature`/`seed` werden – wenn konfiguriert – mitgeschickt (wie bei Gemini).
Reasoning-Modelle (z.B. gpt-5) akzeptieren u.U. keine feste Temperatur/Seed und antworten mit
HTTP 400; in dem Fall wird der Aufruf **einmalig ohne** diese Sampling-Felder wiederholt.
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

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_S = 30.0
# Textbausteine, an denen ein Sampling-Parameter-Fehler (temperature/seed) erkannt wird –
# dann wird ohne diese Felder erneut versucht (Reasoning-Modelle wie gpt-5).
_SAMPLING_HINTS = ("temperature", "seed", "unsupported")


class OpenAIProvider(AIProvider):
    """Schlanker Async-Client für die OpenAI `chat/completions`-REST-API."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5",
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        rate_limit_per_min: int = 60,
        temperature: float | None = 0.0,
        seed: int | None = None,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.seed = seed
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

    def _build_body(self, prompt: str, response_schema: dict, *, sampling: bool) -> dict:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "energy_pilot_plan",
                    "strict": True,
                    # OpenAI-Strict verlangt additionalProperties:false + vollständige required.
                    "schema": to_json_schema(response_schema, all_required=True),
                },
            },
        }
        if sampling:
            if self.temperature is not None:
                body["temperature"] = self.temperature
            if self.seed is not None:
                body["seed"] = self.seed
        return body

    async def generate(self, prompt: str, response_schema: dict) -> ProviderResponse:
        await self._limiter.acquire()
        session = await self._ensure_session()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        sampling = self.temperature is not None or self.seed is not None
        payload = await self._post(session, url, headers, prompt, response_schema, sampling)
        return self._parse(payload)

    async def _post(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict,
        prompt: str,
        response_schema: dict,
        sampling: bool,
    ) -> dict:
        """Sendet den Aufruf; bei einem Sampling-bedingten 400 einmalig ohne temperature/seed."""
        body = self._build_body(prompt, response_schema, sampling=sampling)
        try:
            async with session.post(
                url, json=body, headers=headers, timeout=self._timeout
            ) as resp:
                if resp.status == 429:
                    detail = await read_error_body(resp)
                    suffix = f": {detail}" if detail else ""
                    raise RateLimitError(f"OpenAI-Rate-Limit erreicht (HTTP 429){suffix}")
                if resp.status >= 400:
                    detail = await read_error_body(resp)
                    # Reasoning-Modelle (gpt-5) lehnen feste temperature/seed ab → ohne wiederholen.
                    if sampling and _is_sampling_error(detail):
                        return await self._post(
                            session, url, headers, prompt, response_schema, sampling=False
                        )
                    suffix = f": {detail}" if detail else ""
                    raise ProviderError(f"OpenAI-Fehler HTTP {resp.status}{suffix}")
                return await resp.json()
        except TimeoutError as exc:
            total = self._timeout.total
            detail = f" nach {total:.0f}s" if total else ""
            raise ProviderError(f"OpenAI-Zeitüberschreitung{detail}") from exc
        except aiohttp.ClientError as exc:
            raise ProviderError(f"OpenAI-Verbindungsfehler: {exc}") from exc

    def _parse(self, payload: dict) -> ProviderResponse:
        """Extrahiert das JSON-Objekt + Token-Zähler aus der OpenAI-Antwort."""
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI-Antwort ohne verwertbaren Inhalt") from exc
        if not isinstance(text, str):
            raise ProviderError("OpenAI-Antwort ohne Textinhalt")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"OpenAI lieferte kein gültiges JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("OpenAI-JSON ist kein Objekt")
        usage = payload.get("usage") or {}
        return ProviderResponse(
            data=data,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
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


def _is_sampling_error(detail: str) -> bool:
    """True, wenn der Fehlertext auf eine abgelehnte temperature/seed hindeutet."""
    low = (detail or "").lower()
    return any(hint in low for hint in _SAMPLING_HINTS)
