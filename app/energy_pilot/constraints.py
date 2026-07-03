"""Device-Constraint-Model: leitet die **harten Grenzen** je Gerät ab (D-011).

Harte Grenzen sind die technischen Limits/Freigaben, die die KI **nie** verändern
oder verletzen darf (info.md §7, [08-validierung-sicherheit.md]). Sie werden aus
den in M1 bereits gelesenen `ems_*`-Werten (siehe device_collector.py) abgeleitet.
Sonderfälle:

- **Batterie (D-016/D-037):** immer Priorität 1, immer freigegeben; einziger
  relevanter Grenzwert ist die maximale Ladeleistung (`max_power`).
- **Binärlasten / Heizlüfter (D-017/D-031):** feste Leistung (Default 1500 W),
  nur Freigabe/Priorität regelbar.

User-gepflegte **Zusatz-Entitäten** (D-047, generalisiert den früheren Heizstab-Sonderfall
D-035) werden mit ihrem aktuellen Lesewert als `extras` mitgeführt. Ihre KI-Vorschläge sind
advisorisch (nur HA-Sensor) und unterliegen keiner harten Grenze – der Freitext steuert die KI.
"""

from __future__ import annotations

from dataclasses import dataclass

from energy_pilot.devices import BINARY, Device, DeviceExtra

# Geräte-Präfix der Batterie (Sonderregeln: immer Prio 1, immer freigegeben, D-016/D-037).
BATTERY_PREFIX = "batterie"

# D-017: Heizlüfter sind feste 1500-W-Binärlasten; Fallback, falls `ems_*_leistung_w` fehlt.
DEFAULT_BINARY_POWER_W = 1500.0


@dataclass(frozen=True)
class ConstraintExtra:
    """Eine Zusatz-Entität eines Geräts samt aktuellem Lesewert + Typ/Grenzen (D-047/D-048)."""

    extra: DeviceExtra
    value: object | None  # aktueller Lesewert (Zahl/Bool/Text je Typ; None = nicht gelesen)
    kind: str = "auto"  # aufgelöster Datentyp: number | bool | datetime | text | select
    min: float | None = None  # input_number-Attribut `min` (Untergrenze für die KI, D-048)
    max: float | None = None  # input_number-Attribut `max` (Obergrenze für die KI, D-048)
    has_date: bool | None = None  # input_datetime-Attribut `has_date` (D-048)
    has_time: bool | None = None  # input_datetime-Attribut `has_time` (D-048)
    options: tuple[str, ...] | None = None  # input_select-Auswahlpool `options` (D-049)


@dataclass(frozen=True)
class DeviceConstraint:
    """Die harten Grenzen eines Geräts aus EP-Sicht (read-only abgeleitet)."""

    name: str
    label: str
    device_class: str  # controllable | binary
    output_unit: str  # watt | ampere
    is_battery: bool
    freigabe: bool | None  # ems_*_technische_freigabe (None = unbekannt)
    min_power: float | None  # controllable: ems_*_min_technisch_*
    max_power: float | None  # controllable: ems_*_max_technisch_* (Batterie: max. Ladeleistung)
    fixed_power: float | None  # binary: ems_*_leistung_w (Default 1500 W)
    forced_prio: int | None  # Batterie: 1 (D-016/D-037)
    forced_freigabe: bool | None  # Batterie: True (D-016)
    extras: tuple[ConstraintExtra, ...] = ()  # user-gepflegte Zusatz-Entitäten (D-047)
    ai_prompt: str = ""  # user-gepflegte KI-Beschreibung des Geräts (D-051), advisorisch


def _entry(readings: dict, name: str, key: str) -> object:
    """Holt einen gelesenen Gerätewert (toleriert die `{"value": ...}`-Form des Collectors)."""
    value = (readings.get(name) or {}).get(key)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _extra_record(readings: dict, name: str, key: str) -> tuple[object, dict]:
    """Liefert (Wert, Attribute) einer Zusatz-Entität aus den Readings (Collector-Form, D-048)."""
    rec = (readings.get(name) or {}).get(key)
    if isinstance(rec, dict):
        return rec.get("value"), (rec.get("attrs") or {})
    return rec, {}


def _as_opt_bool(value: object) -> bool | None:
    """Übernimmt ein HA-Attribut nur, wenn es wirklich ein Bool ist (z.B. has_date/has_time)."""
    return value if isinstance(value, bool) else None


def _as_options(value: object) -> tuple[str, ...] | None:
    """Wandelt das `options`-Attribut eines input_select in einen Wertepool (D-049)."""
    if isinstance(value, list | tuple):
        opts = tuple(str(v) for v in value)
        return opts or None
    return None


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
        freigabe = _as_bool(_entry(readings, device.name, "technische_freigabe"))

        min_power = max_power = fixed_power = None
        if device.device_class == BINARY:
            fixed_power = _as_float(_entry(readings, device.name, "leistung_w"))
            if fixed_power is None:
                fixed_power = DEFAULT_BINARY_POWER_W
        else:  # controllable (inkl. Batterie)
            min_power = _as_float(_entry(readings, device.name, "min_technisch"))
            max_power = _as_float(_entry(readings, device.name, "max_technisch"))

        # Zusatz-Entitäten (D-047/D-048): Lesewert + Typ + Attribut-Grenzen/Format mitführen.
        extras_list: list[ConstraintExtra] = []
        for ex in device.extras:
            raw_value, attrs = _extra_record(readings, device.name, ex.read_key)
            kind = ex.kind
            if kind == "auto":  # sensor u.ä.: nach aktuellem Wert auf number/text festlegen
                is_num = isinstance(raw_value, int | float) and not isinstance(raw_value, bool)
                kind = "number" if is_num else "text"
            value = _as_float(raw_value) if kind == "number" else raw_value
            extras_list.append(
                ConstraintExtra(
                    extra=ex,
                    value=value,
                    kind=kind,
                    min=_as_float(attrs.get("min")),
                    max=_as_float(attrs.get("max")),
                    has_date=_as_opt_bool(attrs.get("has_date")),
                    has_time=_as_opt_bool(attrs.get("has_time")),
                    options=_as_options(attrs.get("options")),
                )
            )
        extras = tuple(extras_list)

        result.append(
            DeviceConstraint(
                name=device.name,
                label=device.label,
                device_class=device.device_class,
                output_unit=device.output_unit,
                is_battery=is_battery,
                freigabe=freigabe,
                min_power=min_power,
                max_power=max_power,
                fixed_power=fixed_power,
                forced_prio=1 if is_battery else None,
                forced_freigabe=True if is_battery else None,
                extras=extras,
                ai_prompt=device.ai_prompt,
            )
        )
    return result
