"""Kanonische Datenrollen des Energy Pilot.

Legt fest, welche Eingangsgrößen gemittelt werden (Leistungs-/Flussgrößen) und
welche als letzter Wert geführt werden (Zustände/SOC) – gemäß Decision D-001/D-003
(siehe docs/design-entscheidungen.md).

Ausnahme zu D-003 (Temperaturen als Letztwert): die beiden Temperatur-Rollen werden
**gemittelt** geführt (D-061). Nicht der Absolutwert ist die Information, sondern der
Verlauf: eine steigende Speichertemperatur ohne Heizstableistung heißt „die Solarthermie
lädt gerade" – genau das Signal, das die KI sonst nicht erkennen kann. `latest` bleibt
zusätzlich verfügbar, es geht also kein Momentanwert verloren.
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
#
# Die frühere Rolle `grid_power` („Netzleistung" am Übergabepunkt) ist entfernt: `grid_import` und
# `grid_export` tragen dieselbe Information, und zwar richtungsrein — ohne Vorzeichenkonvention,
# über die man sich vertun kann. Sie war reine Durchleitung an die KI; kein Codepfad rechnete
# mit ihr.
MEASUREMENT_ROLES: tuple[Role, ...] = (
    Role("pv_power", "PV-Leistung", averaged=True, unit="W"),
    Role("house_load", "Hausverbrauch", averaged=True, unit="W"),
    Role("grid_import", "Netzbezug", averaged=True, unit="W"),
    Role("grid_export", "Einspeisung", averaged=True, unit="W"),
    Role("battery_power", "Batterieleistung", averaged=True, unit="W"),
    Role("battery_soc", "Batterie-SOC", averaged=False, unit="%"),
    # Temperaturen gemittelt (D-061): der Verlauf trägt die Information, nicht der Letztwert.
    Role("hot_water_temp", "Warmwassertemperatur", averaged=True, unit="°C"),
    Role("outdoor_temp", "Außentemperatur", averaged=True, unit="°C"),
)

ROLES_BY_KEY: dict[str, Role] = {role.key: role for role in MEASUREMENT_ROLES}
