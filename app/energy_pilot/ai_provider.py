"""Abstrakte KI-Provider-Schnittstelle + Hilfen (Rate-Limit, Fehlerklassen).

Die KI ist **Orchestrator**, nicht Regler (siehe docs/sicherheit-datenschutz.md).
Provider sind über diese abstrakte Basis austauschbar (D-007/D-041/D-056): Eingabe =
Prompt + Antwort-Schema, Ausgabe = **strukturiertes JSON**. Freitext wird nie als
Steuerbefehl verwendet (eiserne Regel 10). Die konkreten Provider liegen in
`gemini_provider.py`, `claude_provider.py` und `openai_provider.py`.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    """Kontrollierter Fehler eines KI-Providers (führt nie zum Absturz, eiserne Regel 13)."""


class RateLimitError(ProviderError):
    """Anbieter-Rate-Limit erreicht (z.B. HTTP 429)."""


@dataclass
class ProviderResponse:
    """Ergebnis eines KI-Aufrufs: geparstes JSON + Token-/Rohdaten."""

    data: dict
    tokens_in: int | None = None
    tokens_out: int | None = None
    raw: dict = field(default_factory=dict)


class AsyncRateLimiter:
    """Drossel: max. `max_per_min` Aufrufe je rollierendem 60-s-Fenster.

    Bei Erreichen des Limits **wartet** der Aufruf, statt einen Fehler zu werfen
    (docs/planungs-engine.md: „Wartedrossel statt Fehlerflut"). `acquire()` liefert die gewartete
    Zeit in Sekunden zurück (0.0, wenn kein Warten nötig war).
    """

    def __init__(self, max_per_min: int, *, window_s: float = 60.0) -> None:
        self.max_per_min = max(1, int(max_per_min))
        self.window_s = window_s
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        async with self._lock:
            waited = 0.0
            now = time.monotonic()
            self._prune(now)
            if len(self._calls) >= self.max_per_min:
                sleep_for = self.window_s - (now - self._calls[0])
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                    waited = sleep_for
                    now = time.monotonic()
                    self._prune(now)
            self._calls.append(now)
            return waited

    def _prune(self, now: float) -> None:
        while self._calls and now - self._calls[0] >= self.window_s:
            self._calls.popleft()


class AIProvider(ABC):
    """Austauschbare Schnittstelle zu einem KI-Dienst (D-007/D-041)."""

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def generate(self, prompt: str, response_schema: dict) -> ProviderResponse:
        """Fordert strukturiertes JSON (gemäß `response_schema`) zum Prompt an."""

    async def close(self) -> None:
        """Schließt offene Ressourcen (Default: nichts zu tun)."""
        return None
