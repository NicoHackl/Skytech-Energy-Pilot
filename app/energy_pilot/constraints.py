"""Device-Constraint-Model: leitet die **harten Grenzen** je Gerät ab (D-011).

Harte Grenzen sind die technischen Limits/Freigaben, die die KI **nie** verändern
oder verletzen darf (info.md §7, [08-validierung-sicherheit.md]). Sie werden aus
den in M1 bereits gelesenen `ems_*`-Werten (siehe device_collector.py) plus dem
Heizstab-Grenzwert-Helfer (D-035) abgeleitet. Sonderfälle:

- **Batterie (D-016/D-037):** immer Priorität 1, immer freigegeben; einziger
  relevanter Grenzwert ist die maximale Ladeleistung (`max_power`).
- **Heizstab (D-035):** zusätzlich die maximale Wassertemperatur als Grenze.
- **Binärlasten / Heizlüfter (D-017/D-031):** feste Leistung (Default 1500 W),
  nur Freigabe/Priorität regelbar.
"""

from __future__ import annotations

from dataclasses import dataclass

from energy_pilot.devices import BINARY, Device

# Geräte-Präfixe mit Sonderregeln (konsistent zur Heizstab-Sonderbehandlung in devices.py).
BATTERY_PREFIX = "batterie"
HEIZSTAB_PREFIX = "heizstab"

# D-017: Heizlüfter sind feste 1500-W-Binärlasten; Fallback, falls `ems_*_leistung_w` fehlt.
DEFAULT_BINARY_POWER_W = 1500.0


@dataclass(frozen=True)
class DeviceConstraint:
    """Die harten Grenzen eines Geräts aus EP-Sicht (read-only abgeleitet)."""

    name: str
    label: str
    device_class: str  # controllable | binary
    output_unit: str  # watt | ampere
    is_battery: bool
    is_heizstab: bool
    freigabe: bool | None  # ems_*_technische_freigabe (None = unbekannt)
    min_power: float | None  # controllable: ems_*_min_technisch_*
    max_power: float | None  # controllable: ems_*_max_technisch_* (Batterie: max. Ladeleistung)
    fixed_power: float | None  # binary: ems_*_leistung_w (Default 1500 W)
    max_water_temp: float | None  # nur Heizstab: input_number.ep_heizstab_max_temperatur (D-035)
    forced_prio: int | None  # Batterie: 1 (D-016/D-037)
    forced_freigabe: bool | None  # Batterie: True (D-016)


def _entry(readings: dict, name: str, key: str) -> object:
    """Holt einen gelesenen Gerätewert (toleriert die `{"value": ...}`-Form des Collectors)."""
    value = (readings.get(name) or {}).get(key)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def build_constraints(devices: list[Device], readings: dict) -> list[DeviceConstraint]:
    """Leitet die harten Grenzen aller Geräte aus den gelesenen `ems_*`-Werten ab.

    `readings` ist der Snapshot des DeviceCollectors (`device.name -> field.key ->
    {"value": ..., "source": ...}`); fehlende Werte ergeben `None`.
    """
    result: list[DeviceConstraint] = []
    for device in devices:
        is_battery = device.entity_prefix == BATTERY_PREFIX
        is_heizstab = device.entity_prefix == HEIZSTAB_PREFIX
        freigabe = _as_bool(_entry(readings, device.name, "technische_freigabe"))

        min_power = max_power = fixed_power = max_water_temp = None
        if device.device_class == BINARY:
            fixed_power = _as_float(_entry(readings, device.name, "leistung_w"))
            if fixed_power is None:
                fixed_power = DEFAULT_BINARY_POWER_W
        else:  # controllable (inkl. Batterie)
            min_power = _as_float(_entry(readings, device.name, "min_technisch"))
            max_power = _as_float(_entry(readings, device.name, "max_technisch"))
            if is_heizstab:
                max_water_temp = _as_float(_entry(readings, device.name, "ep_max_temperatur"))

        result.append(
            DeviceConstraint(
                name=device.name,
                label=device.label,
                device_class=device.device_class,
                output_unit=device.output_unit,
                is_battery=is_battery,
                is_heizstab=is_heizstab,
                freigabe=freigabe,
                min_power=min_power,
                max_power=max_power,
                fixed_power=fixed_power,
                max_water_temp=max_water_temp,
                forced_prio=1 if is_battery else None,
                forced_freigabe=True if is_battery else None,
            )
        )
    return result
