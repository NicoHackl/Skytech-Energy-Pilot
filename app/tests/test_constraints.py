"""Tests für das Device-Constraint-Model (harte Grenzen, D-011/D-016/D-037/D-047)."""

from energy_pilot.constraints import DEFAULT_BINARY_POWER_W, build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device, DeviceExtra


def _dev(name, cls=CONTROLLABLE, unit="watt", prefix=None, extras=()):
    return Device(
        name=name,
        label=name.title(),
        entity_prefix=prefix or name,
        device_class=cls,
        output_unit=unit,
        extras=extras,
    )


def test_controllable_reads_min_max_and_freigabe():
    readings = {
        "heizstab": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 500.0},
            "max_technisch": {"value": 3000.0},
        }
    }
    constraint = build_constraints([_dev("heizstab")], readings)[0]
    assert constraint.freigabe is True
    assert constraint.min_power == 500.0
    assert constraint.max_power == 3000.0
    assert constraint.fixed_power is None


def test_extras_carry_current_read_value():
    # Zusatz-Entitäten (D-047) werden mit ihrem aktuellen Lesewert am Constraint mitgeführt.
    extra = DeviceExtra(
        read_entity_id="input_number.ep_heizstab_max_temperatur",
        ai_suggestion=True, unit="°C",
    )
    readings = {"heizstab": {"extra_heizstab_max_temperatur": {"value": 65.0}}}
    constraint = build_constraints([_dev("heizstab", extras=(extra,))], readings)[0]
    assert len(constraint.extras) == 1
    assert constraint.extras[0].extra.read_entity_id == "input_number.ep_heizstab_max_temperatur"
    assert constraint.extras[0].value == 65.0
    assert constraint.extras[0].kind == "number"


def test_extra_input_number_min_max_from_attributes():
    # input_number: min/max-Attribute werden als Grenzen mitgeführt (D-048).
    ex = DeviceExtra(read_entity_id="input_number.min_soc", ai_suggestion=True)
    readings = {"wallbox": {"extra_min_soc": {"value": 20.0, "attrs": {"min": 0, "max": 100}}}}
    ce = build_constraints([_dev("wallbox", extras=(ex,))], readings)[0].extras[0]
    assert ce.kind == "number"
    assert ce.min == 0.0 and ce.max == 100.0


def test_extra_input_datetime_has_date_time_from_attributes():
    ex = DeviceExtra(read_entity_id="input_datetime.abfahrt", ai_suggestion=True)
    readings = {
        "wallbox": {
            "extra_abfahrt": {
                "value": "2026-07-02 08:00:00",
                "attrs": {"has_date": True, "has_time": False},
            }
        }
    }
    ce = build_constraints([_dev("wallbox", extras=(ex,))], readings)[0].extras[0]
    assert ce.kind == "datetime"
    assert ce.value == "2026-07-02 08:00:00"
    assert ce.has_date is True and ce.has_time is False


def test_extra_input_select_carries_options_pool():
    # input_select (D-049): `options`-Attribut wird als Wertepool am Constraint mitgeführt.
    ex = DeviceExtra(read_entity_id="input_select.lademodus", ai_suggestion=True)
    readings = {
        "wallbox": {
            "extra_lademodus": {
                "value": "PV-Überschuss",
                "attrs": {"options": ["Aus", "PV-Überschuss", "Schnell"]},
            }
        }
    }
    ce = build_constraints([_dev("wallbox", extras=(ex,))], readings)[0].extras[0]
    assert ce.kind == "select"
    assert ce.value == "PV-Überschuss"
    assert ce.options == ("Aus", "PV-Überschuss", "Schnell")


def test_extra_sensor_auto_resolves_number_or_text():
    ex_num = DeviceExtra(read_entity_id="sensor.auto_soc")
    ex_txt = DeviceExtra(read_entity_id="sensor.status")
    readings = {
        "wallbox": {
            "extra_auto_soc": {"value": 42.0},
            "extra_status": {"value": "laden"},
        }
    }
    cons = build_constraints([_dev("wallbox", extras=(ex_num, ex_txt))], readings)[0]
    by_field = {ce.extra.plan_field: ce for ce in cons.extras}
    assert by_field["extra_auto_soc_vorschlag"].kind == "number"
    assert by_field["extra_status_vorschlag"].kind == "text"


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
    assert constraint.extras == ()


def test_accepts_unwrapped_readings():
    # Toleriert sowohl die {"value": x}-Form des Collectors als auch blanke Werte.
    constraint = build_constraints([_dev("heizstab")], {"heizstab": {"max_technisch": 3000.0}})[0]
    assert constraint.max_power == 3000.0
