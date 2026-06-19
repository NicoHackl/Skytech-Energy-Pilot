"""PV-Erzeugungsprognose: Modell und Config-Parsing.

Die PV-Prognose ist in V1 die einzige externe Datenquelle (Decision D-018). Der
User pflegt pro PV-Ausrichtung bis zu vier Sensoren in der Addon-Config; jeder
der vier Werte liegt direkt im State eines eigenen Sensors (D-026). EP summiert
die Werte je Typ über alle Ausrichtungen (siehe forecast_collector).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PVValue:
    """Ein Prognose-Wert-Typ mit Anzeige-Label."""

    key: str
    label: str


# Feste Reihenfolge der vier Prognosewerte (D-018/D-026).
PV_VALUES: tuple[PVValue, ...] = (
    PVValue("current_hour", "Aktuelle Stunde"),
    PVValue("next_hour", "Nächste Stunde"),
    PVValue("remaining_today", "Verbleibend heute"),
    PVValue("tomorrow", "Morgen"),
)


@dataclass(frozen=True)
class PVOrientation:
    """Eine PV-Ausrichtung mit den (gesetzten) Sensor-Entitäten je Wert-Typ."""

    label: str
    entities: dict[str, str]  # value_key -> entity_id


def orientations_from_config(values: dict) -> list[PVOrientation]:
    """Baut die Ausrichtungen aus der Addon-Option `pv_forecast`.

    Einträge ohne jede Entität werden übersprungen; ein fehlendes Label wird
    durch `Ausrichtung N` ersetzt.
    """
    raw = values.get("pv_forecast") or []
    orientations: list[PVOrientation] = []
    for index, cfg in enumerate(raw, start=1):
        if not isinstance(cfg, dict):
            continue
        entities = {
            value.key: entity
            for value in PV_VALUES
            if (entity := (cfg.get(value.key) or "").strip())
        }
        if not entities:
            continue
        label = (cfg.get("label") or "").strip() or f"Ausrichtung {index}"
        orientations.append(PVOrientation(label, entities))
    return orientations
