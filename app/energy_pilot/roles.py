"""Kanonische Datenrollen des Energy Pilot.

Legt fest, welche Eingangsgrößen gemittelt werden (Leistungs-/Flussgrößen) und
welche als letzter Wert geführt werden (Zustände/SOC/Temperaturen) – gemäß
Decision D-001/D-003 (siehe doc/decisions-log.md).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    """Beschreibt eine Eingangsgröße und ihr Aggregationsverhalten."""

    key: str
    label: str
    averaged: bool
    unit: str = ""


# Mess-/Flussgrößen werden über 1/15/60 min gemittelt.
# Zustandsgrößen (averaged=False) führen den letzten gültigen Wert.
MEASUREMENT_ROLES: tuple[Role, ...] = (
    Role("pv_power", "PV-Leistung", averaged=True, unit="W"),
    Role("house_load", "Hausverbrauch", averaged=True, unit="W"),
    Role("grid_power", "Netzleistung", averaged=True, unit="W"),
    Role("grid_import", "Netzbezug", averaged=True, unit="W"),
    Role("grid_export", "Einspeisung", averaged=True, unit="W"),
    Role("battery_power", "Batterieleistung", averaged=True, unit="W"),
    Role("battery_soc", "Batterie-SOC", averaged=False, unit="%"),
)

ROLES_BY_KEY: dict[str, Role] = {role.key: role for role in MEASUREMENT_ROLES}
