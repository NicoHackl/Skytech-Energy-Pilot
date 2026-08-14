"""Persistenz der user-gepflegten KI-Beschreibung je Gerät (D-051).

Zusätzlich zum globalen Planungs-Prompt (settings.PLANNING_PROMPT_KEY) kann der User im
Geräte-Tab je Gerät einen Freitext hinterlegen, der der KI die **Funktion/Besonderheiten**
dieses konkreten Geräts erklärt (z.B. „versorgt die Fußbodenheizung, träge, darf nachts
laufen"). Der Text ist rein **advisorisch**: er geht als Kontext-Feld `funktion` in den
Planungs-Prompt ein (siehe plan_context._condense_constraint), nie an das HEMS.

Die Konfiguration überdauert Add-on-Neustart/-Update (persistentes `/data`-Volume, Tabelle
`device_prompts`, Migration 7). Ein leerer Text löscht den Eintrag (kein Prompt = Standard).
"""

from __future__ import annotations

import sqlite3


def load_device_prompts(db: sqlite3.Connection | None) -> dict[str, str]:
    """Lädt alle Geräte-Prompts als `device_name -> prompt` (leere/fehlende ausgelassen)."""
    if db is None:
        return {}
    try:
        rows = db.execute(
            "SELECT device_name, prompt FROM device_prompts"
        ).fetchall()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (eiserne Regel 13)
        return {}
    result: dict[str, str] = {}
    for row in rows:
        prompt = (row["prompt"] or "").strip()
        if prompt:
            result[row["device_name"]] = prompt
    return result


def get_device_prompt(db: sqlite3.Connection | None, device_name: str) -> str:
    """Liest den Prompt eines Geräts; leerer String, wenn keiner gesetzt ist."""
    if db is None:
        return ""
    try:
        row = db.execute(
            "SELECT prompt FROM device_prompts WHERE device_name = ?", (device_name,)
        ).fetchone()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (eiserne Regel 13)
        return ""
    return (row["prompt"] or "").strip() if row else ""


def set_device_prompt(
    db: sqlite3.Connection | None, device_name: str, prompt: str
) -> bool:
    """Speichert (UPSERT) oder löscht (leerer Text) den Prompt eines Geräts.

    Liefert True, wenn danach ein eigener Prompt gesetzt ist, sonst False (Standard).
    """
    if db is None:
        return False
    prompt = (prompt or "").strip()
    if not prompt:
        db.execute("DELETE FROM device_prompts WHERE device_name = ?", (device_name,))
        db.commit()
        return False
    db.execute(
        "INSERT INTO device_prompts (device_name, prompt, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(device_name) DO UPDATE SET "
        "prompt = excluded.prompt, updated_at = datetime('now')",
        (device_name, prompt),
    )
    db.commit()
    return True
