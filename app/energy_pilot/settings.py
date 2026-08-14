"""Persistente Key/Value-Einstellungen über die `config`-Tabelle (Migration 1).

Genutzt für vom User in der EP-Oberfläche gepflegte Werte, die einen Add-on-Neustart
und ein Add-on-Update überdauern müssen (die DB liegt im persistenten `/data`-Volume) –
z.B. den editierbaren Planungs-Prompt. Bewusst schlank: ein generischer KV-Speicher,
keine eigene Tabelle/Migration.
"""

from __future__ import annotations

import sqlite3

# Schlüssel des in der EP-Oberfläche editierbaren Planungs-Prompts.
PLANNING_PROMPT_KEY = "planning_prompt"
# Schlüssel des editierbaren Klassifizierungs-Prompts (D-055, vorgelagerter Ziel-Aufruf).
CLASSIFICATION_PROMPT_KEY = "classification_prompt"


def get_setting(db: sqlite3.Connection | None, key: str) -> str | None:
    """Liest einen Wert; None, wenn nicht gesetzt oder keine DB verfügbar."""
    if db is None:
        return None
    try:
        row = db.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (eiserne Regel 13)
        return None
    if row is None:
        return None
    return row["value"]


def set_setting(db: sqlite3.Connection | None, key: str, value: str) -> None:
    """Schreibt/aktualisiert einen Wert (UPSERT auf den Primärschlüssel `key`)."""
    if db is None:
        return
    db.execute(
        "INSERT INTO config (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (key, value),
    )
    db.commit()


def delete_setting(db: sqlite3.Connection | None, key: str) -> None:
    """Entfernt einen Wert (z.B. „auf Standard zurücksetzen")."""
    if db is None:
        return
    db.execute("DELETE FROM config WHERE key = ?", (key,))
    db.commit()
