"""Gleitende Mittelwerte über feste Zeitfenster (1/15/60 min, Decision D-003).

Der Energy Pilot erhält Live-Werte und verdichtet sie selbst. Über die
Mittelwerte erfolgt bewusst keine Ereigniskopplung.
"""

from __future__ import annotations

from collections import deque

# Fenster in Sekunden: 1, 15 und 60 Minuten.
WINDOWS_S: tuple[int, ...] = (60, 900, 3600)


class RollingAggregator:
    """Hält je Schlüssel die Rohwerte des größten Fensters und bildet Mittel."""

    def __init__(self, windows: tuple[int, ...] = WINDOWS_S) -> None:
        self.windows = tuple(sorted(windows))
        self._max_window = max(self.windows)
        self._samples: dict[str, deque[tuple[float, float]]] = {}

    def add(self, key: str, value: float, ts: float) -> None:
        """Fügt einen Messwert hinzu und entfernt zu alte Werte."""
        samples = self._samples.setdefault(key, deque())
        samples.append((ts, value))
        self._prune(key, ts)

    def _prune(self, key: str, now: float) -> None:
        samples = self._samples[key]
        cutoff = now - self._max_window
        while samples and samples[0][0] < cutoff:
            samples.popleft()

    def latest(self, key: str) -> float | None:
        """Letzter gespeicherter Wert (für nicht gemittelte Zustandsgrößen)."""
        samples = self._samples.get(key)
        return samples[-1][1] if samples else None

    def mean(self, key: str, window_s: int, now: float) -> float | None:
        """Mittelwert über das angegebene Zeitfenster bis 'now'."""
        samples = self._samples.get(key)
        if not samples:
            return None
        cutoff = now - window_s
        values = [value for ts, value in samples if ts >= cutoff]
        if not values:
            return None
        return sum(values) / len(values)

    def means(self, key: str, now: float) -> dict[int, float | None]:
        """Mittelwerte über alle konfigurierten Fenster."""
        return {window: self.mean(key, window, now) for window in self.windows}
