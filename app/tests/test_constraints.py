"""Tests für das Device-Constraint-Model (harte Grenzen, D-011/D-016/D-035/D-037)."""

from energy_pilot.constraints import DEFAULT_BINARY_POWER_W, build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device


def _dev(name, cls=CONTROLLABLE, unit="watt", prefix=None):
    return Device(
        name=name,
        label=name.title(),
        entity_prefix=prefix or name,
        device_class=cls,
        output_unit=unit,
    )


def test_controllable_reads_min_max_and_freigabe():
    readings = {
        "heizstab": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 500.0},
            "max_technisch": {"value": 3000.0},
            "ep_max_temperatur": {"value": 65.0},
        }
    }
    constraint = build_constraints([_dev("heizstab")], readings)[0]
    assert constraint.freigabe is True
    assert constraint.min_power == 500.0
    assert constraint.max_power == 3000.0
    assert constraint.is_heizstab is True
    assert constraint.max_water_temp == 65.0
    assert constraint.fixed_power is None


def test_battery_is_always_prio1_and_freigegeben():
    readings = {
        "batterie": {"technische_freigabe": {"value": False}, "max_technisch": {"value": 5000.0}}
    }
    constraint = build_constraints([_dev("batterie")], readings)[0]
    assert constraint.is_battery is True
    assert constraint.forced_prio == 1
    assert constraint.forced_freigabe is True
    assert constraint.max_power == 5000.0  # einziger relevanter Grenzwert (D-016)


def test_binary_uses_leistung_w_else_default():
    devices = [_dev("heizluefter_1", cls=BINARY)]
    constraint = build_constraints(devices, {"heizluefter_1": {"leistung_w": {"value": 1500.0}}})[0]
    assert constraint.fixed_power == 1500.0
    assert constraint.min_power is None
    fallback = build_constraints(devices, {})[0]
    assert fallback.fixed_power == DEFAULT_BINARY_POWER_W


def test_ampere_unit_preserved():
    readings = {"wallbox": {"min_technisch": {"value": 6.0}, "max_technisch": {"value": 16.0}}}
    constraint = build_constraints([_dev("wallbox", unit="ampere")], readings)[0]
    assert constraint.output_unit == "ampere"
    assert constraint.max_power == 16.0


def test_missing_values_yield_none():
    constraint = build_constraints([_dev("heizstab")], {})[0]
    assert constraint.freigabe is None
    assert constraint.min_power is None
    assert constraint.max_water_temp is None


def test_accepts_unwrapped_readings():
    # Toleriert sowohl die {"value": x}-Form des Collectors als auch blanke Werte.
    constraint = build_constraints([_dev("heizstab")], {"heizstab": {"max_technisch": 3000.0}})[0]
    assert constraint.max_power == 3000.0
