"""Zuordnung von Datenrollen zu HA-Entitäten samt Fallback-Wert (Decision D-006).

Grenzwerte/Messgrößen werden über HA-Entitäten geliefert; findet sich keine
gültige Entität, greift der in der Oberfläche gepflegte Fallback-Wert.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from energy_pilot.conversion import safe_float
from energy_pilot.roles import MEASUREMENT_ROLES


@dataclass
class EntityMapping:
    """Verknüpfung einer Rolle mit einer HA-Entität und optionalem Fallback."""

    role: str
    entity_id: str | None = None
    fallback_value: float | None = None


def mapping_from_options(values: dict) -> dict[str, EntityMapping]:
    """Baut die Zuordnung aus den Addon-Optionen (entity_<rolle>/fallback_<rolle>).

    Decision-Änderung: Die Sensor-Zuordnung wird in der Addon-Konfiguration
    gepflegt (gleiche Seite wie das KI-Modell), nicht in der Addon-Oberfläche.
    """
    # Sensoren liegen in der Gruppe "sensoren"; flach als Fallback (Abwärtskompatibilität).
    nested = values.get("sensoren")
    source = nested if isinstance(nested, dict) else values

    mapping: dict[str, EntityMapping] = {}
    for role in MEASUREMENT_ROLES:
        entity_id = (source.get(f"entity_{role.key}") or "").strip() or None
        fallback = safe_float(source.get(f"fallback_{role.key}"))
        if entity_id is not None or fallback is not None:
            mapping[role.key] = EntityMapping(role.key, entity_id, fallback)
    return mapping


def load_mapping(conn: sqlite3.Connection) -> dict[str, EntityMapping]:
    """Lädt alle gespeicherten Zuordnungen aus der Datenbank."""
    rows = conn.execute("SELECT role, ha_entity_id, fallback_value FROM entity_map")
    return {
        row["role"]: EntityMapping(row["role"], row["ha_entity_id"], row["fallback_value"])
        for row in rows
    }


def save_mapping(conn: sqlite3.Connection, mapping: EntityMapping) -> None:
    """Speichert oder aktualisiert eine Zuordnung (Upsert über die Rolle)."""
    conn.execute(
        "INSERT INTO entity_map (role, ha_entity_id, fallback_value, updated_at) "
        "VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(role) DO UPDATE SET "
        "ha_entity_id=excluded.ha_entity_id, "
        "fallback_value=excluded.fallback_value, "
        "updated_at=excluded.updated_at",
        (mapping.role, mapping.entity_id, mapping.fallback_value),
    )
    conn.commit()
