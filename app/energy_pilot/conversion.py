"""Sichere Wertkonvertierung von Home-Assistant-Zuständen."""

from __future__ import annotations

# Zustandstexte, die "kein gültiger Messwert" bedeuten.
INVALID_STATES = frozenset({"", "unavailable", "unknown", "none", "nan"})


def safe_float(value: object) -> float | None:
    """Wandelt einen HA-Zustand in eine Zahl um; liefert None bei ungültigen Werten."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool ist ein int-Subtyp – hier bewusst nicht als Zahl interpretieren
        return None
    if isinstance(value, (int | float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in INVALID_STATES:
        return None
    try:
        return float(text)
    except ValueError:
        return None
