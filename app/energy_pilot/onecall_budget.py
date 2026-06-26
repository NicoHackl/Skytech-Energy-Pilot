"""Tages-Call-Budget für die kostenpflichtige One Call API 4.0 (O2, D-045).

Jede One-Call-Anfrage (eine Timeline-Seite **oder** ein Alert-Abruf) ist ein eigener bezahlter
Call. Dieses Modul zählt die an einem Tag bereits verbrauchten Calls und ist die Grundlage des
**verpflichtenden** Schutzes gegen das Überschreiten des konfigurierten Tageslimits (Default 1000
= OWM-Freikontingent „One Call by Call"). Der Zähler wird über den generischen KV-Speicher
(`settings.py` / `config`-Tabelle im persistenten `/data`-Volume) geführt – so kann ein
Add-on-Neustart das Budget **nicht** umgehen (sonst würde ein Restart-Loop beliebig viele Calls
auslösen).

Der Tag wird in **UTC** gerechnet (deckt sich mit OWMs Quota-Reset um Mitternacht UTC); beim
Datumswechsel beginnt der Zähler automatisch wieder bei 0. Ohne DB (`db=None`) degradiert das
Modul still: `calls_today` = 0, `consume` ist ein No-op (Iron Rule 8 – blockiert nie).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from energy_pilot.settings import get_setting, set_setting

# KV-Schlüssel des Budget-Zählers (Wert = JSON {"day": "YYYY-MM-DD", "count": N}).
ONECALL_BUDGET_KEY = "onecall_call_budget"


def _today_utc() -> str:
    """Aktuelles Datum in UTC als `YYYY-MM-DD` (OWM-Quota-Reset um Mitternacht UTC)."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _load(db: sqlite3.Connection | None) -> tuple[str, int]:
    """Liest (Tag, Zähler) aus dem KV-Speicher; (\"\", 0), falls nicht gesetzt/ungültig."""
    raw = get_setting(db, ONECALL_BUDGET_KEY)
    if not raw:
        return "", 0
    try:
        data = json.loads(raw)
        return str(data.get("day") or ""), int(data.get("count") or 0)
    except (ValueError, TypeError):  # defekter Wert → wie ungesetzt behandeln
        return "", 0


def calls_today(db: sqlite3.Connection | None, *, now_day: str | None = None) -> int:
    """Heute (UTC) bereits verbrauchte bezahlte Calls; 0 bei neuem Tag oder ohne DB."""
    day = now_day or _today_utc()
    stored_day, count = _load(db)
    return count if stored_day == day else 0


def remaining(
    db: sqlite3.Connection | None, budget: int, *, now_day: str | None = None
) -> int:
    """Heute noch verfügbare Calls (nie negativ)."""
    return max(0, budget - calls_today(db, now_day=now_day))


def consume(db: sqlite3.Connection | None, n: int, *, now_day: str | None = None) -> None:
    """Bucht `n` verbrauchte Calls auf den heutigen Zähler (mit Tageswechsel-Reset)."""
    if db is None or n <= 0:
        return
    day = now_day or _today_utc()
    stored_day, count = _load(db)
    base = count if stored_day == day else 0
    set_setting(db, ONECALL_BUDGET_KEY, json.dumps({"day": day, "count": base + n}))
