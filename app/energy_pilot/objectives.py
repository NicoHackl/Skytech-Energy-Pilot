"""User-Objective-Manager: weiche Zielgewichte (Decision D-011).

Die weichen Ziele (siehe doc/configuration.md) sind gegeneinander abwägbare Gewichte
(0–100 %). Sie sind in der Addon-Config unter `objective_weights` pflegbar und werden
initial mit den unten stehenden Defaultwerten vorbelegt (D-011). Harte Grenzen liegen dagegen im
Constraint-Model (constraints.py) und sind **nie** durch die KI änderbar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Objective:
    """Ein gewichtbares weiches Ziel (Gewicht in Prozent, 0–100)."""

    key: str
    label: str
    weight: int


# Reihenfolge + Default-Gewichte (D-011, siehe doc/configuration.md).
DEFAULT_OBJECTIVES: tuple[Objective, ...] = (
    Objective("versorgungssicherheit", "Versorgungssicherheit", 100),
    Objective("eauto_ladeziel", "E-Auto-Ladeziel", 100),
    Objective("warmwasserkomfort", "Warmwasserkomfort", 100),
    Objective("netzbezug", "Netzbezug minimieren", 90),
    Objective("stromkosten", "Stromkosten minimieren", 85),
    Objective("eigenverbrauch", "Eigenverbrauch maximieren", 80),
    Objective("einspeisung", "Einspeisung reduzieren", 70),
    Objective("batterieschonung", "Batterieschonung", 50),
)


def _clamp_weight(value: object, default: int) -> int:
    """Klemmt ein Gewicht auf 0–100; ungültige Werte fallen auf den Default zurück."""
    try:
        weight = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0, min(100, weight))


def objectives_from_config(values: dict) -> list[Objective]:
    """Liefert die aktiven Ziele: Defaults aus §7, überschrieben durch `objective_weights`.

    Unbekannte Keys in der Config werden ignoriert; fehlende Keys behalten den
    Default. Werte außerhalb 0–100 werden geklemmt.
    """
    overrides = values.get("objective_weights") or {}
    if not isinstance(overrides, dict):
        overrides = {}
    result: list[Objective] = []
    for obj in DEFAULT_OBJECTIVES:
        if obj.key in overrides:
            weight = _clamp_weight(overrides[obj.key], obj.weight)
        else:
            weight = obj.weight
        result.append(Objective(obj.key, obj.label, weight))
    return result
