"""User-definierte Ziele + deren Gewichtung (D-055).

Ersetzt die frühere statische Addon-Config `objective_weights` (D-011): der User pflegt im
Tab "Grenzen und Ziele" eigene Ziele (`Ziel`: id/Name/Beschreibung/zugehörige Geräte, OHNE
Gewicht) in der DB-Tabelle `ziele` (Migration 10). Ein vorgelagerter Klassifizierungs-LLM-Aufruf
(siehe `planner.py`, `plan_context.build_classification_context`) leitet daraus je Planungslauf
die Gewichtung ab; `objectives_from_classification` baut daraus die `Objective`-Liste, die
`plan_context.build_context` unverändert wie zuvor konsumiert.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Objective:
    """Ein gewichtetes weiches Ziel (Gewicht in Prozent, 0–100) für den Plan-Kontext."""

    key: str
    label: str
    weight: int


@dataclass(frozen=True)
class Ziel:
    """Ein user-definiertes Ziel (D-055): keine Gewichtung, die leitet die KI selbst ab."""

    id: int
    name: str
    beschreibung: str
    devices: tuple[str, ...]


def _clamp_weight(value: object, default: int) -> int:
    """Klemmt ein Gewicht auf 0–100; ungültige Werte fallen auf den Default zurück."""
    try:
        weight = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0, min(100, weight))


def _row_to_ziel(row: sqlite3.Row) -> Ziel:
    try:
        devices = json.loads(row["devices_json"] or "[]")
    except (TypeError, ValueError):
        devices = []
    if not isinstance(devices, list):
        devices = []
    return Ziel(
        id=row["id"],
        name=row["name"] or "",
        beschreibung=row["beschreibung"] or "",
        devices=tuple(str(d) for d in devices),
    )


def load_ziele(db: sqlite3.Connection | None) -> list[Ziel]:
    """Lädt alle user-definierten Ziele (stabile Reihenfolge, leer ohne DB/Fehler)."""
    if db is None:
        return []
    try:
        rows = db.execute(
            "SELECT id, name, beschreibung, devices_json FROM ziele ORDER BY sort_order, id"
        ).fetchall()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (Iron Rule 8)
        return []
    return [_row_to_ziel(row) for row in rows]


def upsert_ziel(
    db: sqlite3.Connection,
    *,
    ziel_id: int | None,
    name: str,
    beschreibung: str = "",
    devices: list[str] | None = None,
) -> Ziel:
    """Legt ein Ziel an (`ziel_id=None`) oder aktualisiert es (Ziele-Tab, D-055)."""
    devices = list(devices or [])
    devices_json = json.dumps(devices, ensure_ascii=False)
    if ziel_id is None:
        cur = db.execute(
            "INSERT INTO ziele (name, beschreibung, devices_json, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (name, beschreibung, devices_json),
        )
        ziel_id = cur.lastrowid
    else:
        db.execute(
            "UPDATE ziele SET name = ?, beschreibung = ?, devices_json = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (name, beschreibung, devices_json, ziel_id),
        )
    db.commit()
    return Ziel(id=ziel_id, name=name, beschreibung=beschreibung, devices=tuple(devices))


def delete_ziel(db: sqlite3.Connection, ziel_id: int) -> None:
    """Entfernt ein Ziel."""
    db.execute("DELETE FROM ziele WHERE id = ?", (ziel_id,))
    db.commit()


def objectives_from_classification(ziele: list[Ziel], gewichtung: dict) -> list[Objective]:
    """Baut die Plan-Kontext-`Objective`-Liste aus der Klassifizierungs-Antwort.

    Fehlt ein Ziel in `gewichtung` oder ist der Wert ungültig, greift Default-Gewicht 50
    (neutral) – Robustheit gegen einzelne Modell-Lücken (D-050-Vorbild). Ein komplett
    gescheiterter Klassifizierungs-Aufruf (Exception) lässt dagegen den ganzen Planungslauf
    scheitern (siehe `planner.py`), das hier ist nur die Absicherung bei einer *erfolgreichen*
    aber lückenhaften Antwort.
    """
    if not isinstance(gewichtung, dict):
        gewichtung = {}
    return [
        Objective(
            key=str(z.id),
            label=z.name,
            weight=_clamp_weight(gewichtung.get(str(z.id)), 50),
        )
        for z in ziele
    ]
