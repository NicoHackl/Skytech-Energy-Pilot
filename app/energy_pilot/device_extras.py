"""Persistenz der user-gepflegten Zusatz-Entitäten je Gerät (D-047).

Zusätzlich zu den vom HEMS gezogenen `ems_*`-Werten kann der User im Geräte-Tab je Gerät
weitere Entitäten hinterlegen (z.B. `input_number.min_soc_auto`), die EP liest und – wenn
so konfiguriert – von der KI zu einem Vorschlagswert (`sensor.ep_<obj>_vorschlag`) machen
lässt. Diese Konfiguration überdauert Add-on-Neustart/-Update (persistentes `/data`-Volume,
Tabelle `device_extras`, Migration 6). Die Werte selbst sind advisorisch: sie werden nur als
HA-Sensor bereitgestellt, nie an das HEMS übergeben (das HEMS kennt sie nicht).

Der frühere Heizstab-Hardcode (D-035, `input_number.ep_heizstab_max_temperatur` →
`sensor.ep_heizstab_max_temperatur_vorschlag`) wird beim ersten Erkennen eines Heizstab-Geräts
einmalig als (editierbare) Default-Zusatzentität angelegt (`seed_defaults`), damit bestehende
Installationen unverändert weiterlaufen.
"""

from __future__ import annotations

import re
import sqlite3

from energy_pilot.devices import Device, DeviceExtra
from energy_pilot.settings import get_setting, set_setting

# Geräte-Präfix des Heizstabs für das Default-Seeding (früher constraints.HEIZSTAB_PREFIX, D-035).
_HEIZSTAB_PREFIX = "heizstab"
# Einmal-Marker im KV-Store: verhindert erneutes Seeding, nachdem der User den Default gelöscht hat.
_HEIZSTAB_SEED_MARKER = "device_extras_heizstab_seeded"

# Default-Zusatzentität, die den früheren Heizstab-Hardcode (D-035) ablöst.
_HEIZSTAB_DEFAULT = {
    "read_entity_id": "input_number.ep_heizstab_max_temperatur",
    "ai_suggestion": True,
    "ai_hint": (
        "Maximal zulässige Warmwassertemperatur (°C) des Heizstabs. Der aktuelle Wert ist die "
        "vom User gesetzte Obergrenze. Schlage eine sinnvolle Zieltemperatur ≤ diesem Grenzwert "
        "vor, die Warmwasserbedarf und PV-Überschuss abwägt; überschreite den Grenzwert nie."
    ),
    "label": "Max. Wassertemperatur",
    "unit": "°C",
}

# Grobe Struktur einer HA-Entity-ID: <domain>.<object_id> (Kleinbuchstaben/Ziffern/Unterstrich).
_ENTITY_ID_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


def is_valid_entity_id(entity_id: str) -> bool:
    """Prüft grob das HA-Entity-ID-Format `<domain>.<object_id>`."""
    return bool(_ENTITY_ID_RE.match((entity_id or "").strip()))


def _row_to_extra(row: sqlite3.Row) -> DeviceExtra:
    return DeviceExtra(
        read_entity_id=row["read_entity_id"],
        ai_suggestion=bool(row["ai_suggestion"]),
        ai_hint=row["ai_hint"] or "",
        label=row["label"] or "",
        unit=row["unit"] or "",
        write_original=bool(row["write_original"]),
    )


def load_extras(db: sqlite3.Connection | None) -> dict[str, tuple[DeviceExtra, ...]]:
    """Lädt alle Zusatz-Entitäten, gruppiert nach `device_name` (stabile Reihenfolge)."""
    if db is None:
        return {}
    try:
        rows = db.execute(
            "SELECT device_name, read_entity_id, ai_suggestion, ai_hint, label, unit, "
            "write_original FROM device_extras ORDER BY device_name, sort_order, id"
        ).fetchall()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie (Iron Rule 8)
        return {}
    grouped: dict[str, list[DeviceExtra]] = {}
    for row in rows:
        grouped.setdefault(row["device_name"], []).append(_row_to_extra(row))
    return {name: tuple(items) for name, items in grouped.items()}


def apply_extras(
    devices: list[Device],
    extras_map: dict[str, tuple[DeviceExtra, ...]],
    prompts: dict[str, str] | None = None,
) -> list[Device]:
    """Hängt die geladenen Zusatz-Entitäten und Geräte-Prompts an die Geräte an.

    Die Zuordnung erfolgt über den stabilen `device.name` (D-029). Geräte ohne Konfiguration
    behalten eine leere `extras`-Tuple bzw. einen leeren `ai_prompt`. `prompts` ist die
    user-gepflegte KI-Beschreibung je Gerät (D-051, siehe device_prompts). Liefert neue
    `Device`-Instanzen (frozen dataclass).
    """
    prompts = prompts or {}
    result: list[Device] = []
    for device in devices:
        extras = extras_map.get(device.name, ())
        result.append(
            Device(
                name=device.name,
                label=device.label,
                entity_prefix=device.entity_prefix,
                device_class=device.device_class,
                output_unit=device.output_unit,
                extras=extras,
                ai_prompt=prompts.get(device.name, ""),
            )
        )
    return result


def upsert_extra(
    db: sqlite3.Connection | None,
    *,
    device_name: str,
    read_entity_id: str,
    ai_suggestion: bool,
    ai_hint: str = "",
    label: str = "",
    unit: str = "",
    write_original: bool = False,
) -> None:
    """Legt eine Zusatz-Entität an oder aktualisiert sie (UPSERT auf device_name+entity).

    `write_original` (D-052) ist nur bei `ai_suggestion=True` wirksam (siehe
    `DeviceExtra.should_write_original`) – hier trotzdem roh übernommen, damit ein späteres
    Aktivieren von `ai_suggestion` den zuvor gewählten Original-Schreibweg nicht verliert.
    """
    if db is None:
        return
    db.execute(
        "INSERT INTO device_extras "
        "(device_name, read_entity_id, ai_suggestion, ai_hint, label, unit, write_original, "
        "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(device_name, read_entity_id) DO UPDATE SET "
        "ai_suggestion = excluded.ai_suggestion, ai_hint = excluded.ai_hint, "
        "label = excluded.label, unit = excluded.unit, "
        "write_original = excluded.write_original, updated_at = datetime('now')",
        (
            device_name,
            read_entity_id.strip(),
            1 if ai_suggestion else 0,
            ai_hint,
            label,
            unit,
            1 if write_original else 0,
        ),
    )
    db.commit()


def delete_extra(
    db: sqlite3.Connection | None, *, device_name: str, read_entity_id: str
) -> None:
    """Entfernt eine Zusatz-Entität eines Geräts."""
    if db is None:
        return
    db.execute(
        "DELETE FROM device_extras WHERE device_name = ? AND read_entity_id = ?",
        (device_name, read_entity_id.strip()),
    )
    db.commit()


def suggestion_conflict(
    extras_map: dict[str, tuple[DeviceExtra, ...]],
    *,
    device_name: str,
    read_entity_id: str,
) -> str | None:
    """Prüft, ob der Vorschlags-Sensor der neuen Entität mit einer anderen kollidiert.

    Zwei Zusatz-Entitäten mit aktivem KI-Vorschlag dürfen nicht denselben
    `sensor.ep_<obj>_vorschlag` erzeugen (sonst überschreiben sie sich in HA). Liefert die
    kollidierende Quell-Entität (eines anderen Eintrags) oder None.
    """
    candidate = DeviceExtra(read_entity_id=read_entity_id, ai_suggestion=True)
    target = candidate.suggestion_entity_id
    for name, extras in extras_map.items():
        for extra in extras:
            if not extra.ai_suggestion:
                continue
            if name == device_name and extra.read_entity_id == read_entity_id.strip():
                continue  # der Eintrag selbst (Update) kollidiert nicht mit sich
            if extra.suggestion_entity_id == target:
                return extra.read_entity_id
    return None


def seed_defaults(db: sqlite3.Connection | None, devices: list[Device]) -> bool:
    """Legt einmalig die Heizstab-Default-Zusatzentität an (ersetzt Hardcode D-035).

    Nur beim ersten Erkennen eines Heizstab-Geräts und solange der Marker nicht gesetzt ist.
    Der User kann den Default danach frei ändern oder löschen (er wird nicht neu angelegt).
    Liefert True, wenn geseedet wurde.
    """
    if db is None or get_setting(db, _HEIZSTAB_SEED_MARKER):
        return False
    heizstab = next((d for d in devices if d.entity_prefix == _HEIZSTAB_PREFIX), None)
    if heizstab is None:
        return False
    upsert_extra(
        db,
        device_name=heizstab.name,
        read_entity_id=_HEIZSTAB_DEFAULT["read_entity_id"],
        ai_suggestion=_HEIZSTAB_DEFAULT["ai_suggestion"],
        ai_hint=_HEIZSTAB_DEFAULT["ai_hint"],
        label=_HEIZSTAB_DEFAULT["label"],
        unit=_HEIZSTAB_DEFAULT["unit"],
    )
    set_setting(db, _HEIZSTAB_SEED_MARKER, "1")
    return True
