"""Persistenz der user-gepflegten Betriebsregeln als Freitext (D-060).

Der User formuliert je Gerät — und einmal hausweit — in eigenen Worten, **unter welchen
Bedingungen ein Gerät laufen soll und unter welchen nicht** (z.B. „Steht die Warmwasser-
temperatur über 70 °C oder werden die nächsten zwei Tage über 25 °C warm, bleibt der Heizstab
gesperrt: die Solarthermie deckt das Warmwasser und der Speicher darf nicht überhitzen.").

Abgrenzung zur Geräte-Beschreibung (D-051, `device_prompts`): dort steht, **was** ein Gerät ist
und wie es sich verhält; hier steht, **was der User will**. Getrennte Felder, weil sie im Prompt
unterschiedlich adressiert werden: die Beschreibung ist Hintergrundwissen, die Regeln sind die
Vorgabe, gegen die die KI ihre Entscheidung je Gerät begründen muss.

Bewusst Freitext und **nicht** typisiert (Entscheidung des Users, D-060): die Regeln gehen als
eigener, im Prompt referenzierter Block in den KI-Kontext und werden nicht nachträglich gegen die
Modellantwort erzwungen. Die Gegenkontrolle ist die erzwungene Selbsterklärung je Gerät
(`begruendung`/`angewandte_regeln` im Antwortschema), nicht ein Override.

Die Konfiguration überdauert Add-on-Neustart/-Update (persistentes `/data`-Volume, Tabelle
`device_regeln`, Migration 12). Ein leerer Text löscht den Eintrag.
"""

from __future__ import annotations

import sqlite3

from energy_pilot.settings import GLOBAL_RULES_KEY, get_setting, set_setting


def load_device_regeln(db: sqlite3.Connection | None) -> dict[str, str]:
    """Lädt alle Geräteregeln als `device_name -> regeln` (leere/fehlende ausgelassen)."""
    if db is None:
        return {}
    try:
        rows = db.execute("SELECT device_name, regeln FROM device_regeln").fetchall()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (eiserne Regel 13)
        return {}
    result: dict[str, str] = {}
    for row in rows:
        regeln = (row["regeln"] or "").strip()
        if regeln:
            result[row["device_name"]] = regeln
    return result


def get_device_regeln(db: sqlite3.Connection | None, device_name: str) -> str:
    """Liest die Regeln eines Geräts; leerer String, wenn keine gesetzt sind."""
    if db is None:
        return ""
    try:
        row = db.execute(
            "SELECT regeln FROM device_regeln WHERE device_name = ?", (device_name,)
        ).fetchone()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (eiserne Regel 13)
        return ""
    return (row["regeln"] or "").strip() if row else ""


def set_device_regeln(
    db: sqlite3.Connection | None, device_name: str, regeln: str
) -> bool:
    """Speichert (UPSERT) oder löscht (leerer Text) die Regeln eines Geräts.

    Liefert True, wenn danach eigene Regeln gesetzt sind, sonst False.
    """
    if db is None:
        return False
    regeln = (regeln or "").strip()
    if not regeln:
        db.execute("DELETE FROM device_regeln WHERE device_name = ?", (device_name,))
        db.commit()
        return False
    db.execute(
        "INSERT INTO device_regeln (device_name, regeln, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(device_name) DO UPDATE SET "
        "regeln = excluded.regeln, updated_at = datetime('now')",
        (device_name, regeln),
    )
    db.commit()
    return True


def get_global_regeln(db: sqlite3.Connection | None) -> str:
    """Liest die hausweiten Regeln (KV-Store, kein eigenes Schema nötig)."""
    return (get_setting(db, GLOBAL_RULES_KEY) or "").strip()


def set_global_regeln(db: sqlite3.Connection | None, regeln: str) -> str:
    """Speichert die hausweiten Regeln und liefert den gespeicherten Text zurück."""
    text = (regeln or "").strip()
    set_setting(db, GLOBAL_RULES_KEY, text)
    return text
