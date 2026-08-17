"""Persistenz der Wärmespeicher-Kennwerte je Gerät (D-066).

Drei Zahlen, die nur der Anlagenbetreiber kennt und die EP nicht erraten darf:

- **Volumen** in Liter — macht aus einer Temperaturdifferenz eine Energiemenge.
- **Komfortminimum** in °C — was jederzeit gewährleistet sein muss.
- **Zielwert** in °C (optional) — worauf geladen werden soll, wenn geladen wird.

Abgrenzung, die den Unterschied zum verworfenen Regelwerk ausmacht (D-060): das sind
**Anlagendaten und eine Anforderung**, keine Entscheidungsregeln. „Nie unter 45 °C" sagt nicht,
wann der Heizstab läuft — es sagt, was nicht passieren darf. Wann geladen wird, folgt aus der
Bilanz und bleibt die Entscheidung der KI.

Fehlt ein Wert, entfallen die abgeleiteten kWh-Merkmale und der KI-Kontext sagt das ausdrücklich
(`features.py`) — nie ein stiller Nullwert, der wie eine Messung aussieht.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SpeicherDaten:
    """Kennwerte eines Wärmespeichers; `None` heißt „nicht gepflegt", nie 0."""

    volumen_liter: float | None = None
    komfort_min_c: float | None = None
    ziel_c: float | None = None

    @property
    def gepflegt(self) -> bool:
        """True, wenn mindestens ein Wert gesetzt ist (sonst gibt es nichts zu übergeben)."""
        return any(
            value is not None
            for value in (self.volumen_liter, self.komfort_min_c, self.ziel_c)
        )

    @property
    def rechenbar(self) -> bool:
        """True, wenn eine kWh-Rechnung möglich ist: Volumen **und** Komfortminimum."""
        return self.volumen_liter is not None and self.komfort_min_c is not None

    @property
    def fehlende_felder(self) -> tuple[str, ...]:
        """Welche Werte für die kWh-Rechnung fehlen (für die Meldung an die KI)."""
        fehlt: list[str] = []
        if self.volumen_liter is None:
            fehlt.append("volumen_liter")
        if self.komfort_min_c is None:
            fehlt.append("komfort_min_c")
        return tuple(fehlt)


def _as_opt_float(value: object) -> float | None:
    """Zahl oder None; ein leerer String bedeutet „nicht gepflegt", nicht 0."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def load_speicher(db: sqlite3.Connection | None) -> dict[str, SpeicherDaten]:
    """Lädt die Kennwerte aller Geräte als `device_name -> SpeicherDaten`."""
    if db is None:
        return {}
    try:
        rows = db.execute(
            "SELECT device_name, volumen_liter, komfort_min_c, ziel_c FROM device_speicher"
        ).fetchall()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (eiserne Regel 13)
        return {}
    out: dict[str, SpeicherDaten] = {}
    for row in rows:
        daten = SpeicherDaten(
            volumen_liter=_as_opt_float(row["volumen_liter"]),
            komfort_min_c=_as_opt_float(row["komfort_min_c"]),
            ziel_c=_as_opt_float(row["ziel_c"]),
        )
        if daten.gepflegt:
            out[row["device_name"]] = daten
    return out


def get_speicher(db: sqlite3.Connection | None, device_name: str) -> SpeicherDaten:
    """Kennwerte eines Geräts; leere `SpeicherDaten`, wenn nichts gepflegt ist."""
    return load_speicher(db).get(device_name, SpeicherDaten())


def set_speicher(
    db: sqlite3.Connection | None,
    device_name: str,
    *,
    volumen_liter: float | None,
    komfort_min_c: float | None,
    ziel_c: float | None = None,
) -> SpeicherDaten:
    """Speichert (UPSERT) die Kennwerte; sind alle leer, wird der Eintrag entfernt.

    Liefert die gespeicherten Werte zurück, damit der Aufrufer nicht erneut lesen muss.
    """
    daten = SpeicherDaten(
        volumen_liter=_as_opt_float(volumen_liter),
        komfort_min_c=_as_opt_float(komfort_min_c),
        ziel_c=_as_opt_float(ziel_c),
    )
    if db is None:
        return daten
    if not daten.gepflegt:
        db.execute("DELETE FROM device_speicher WHERE device_name = ?", (device_name,))
        db.commit()
        return daten
    db.execute(
        "INSERT INTO device_speicher (device_name, volumen_liter, komfort_min_c, ziel_c, "
        "updated_at) VALUES (?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(device_name) DO UPDATE SET volumen_liter = excluded.volumen_liter, "
        "komfort_min_c = excluded.komfort_min_c, ziel_c = excluded.ziel_c, "
        "updated_at = datetime('now')",
        (device_name, daten.volumen_liter, daten.komfort_min_c, daten.ziel_c),
    )
    db.commit()
    return daten
