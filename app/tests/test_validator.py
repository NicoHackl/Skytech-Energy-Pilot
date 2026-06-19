"""Tests für das lokale Plan-Sicherheits-Gate (Validator, Stufen 1–3)."""

from datetime import UTC, datetime

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device
from energy_pilot.validator import validate

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def _constraints():
    devices = [
        Device("batterie", "Batterie", "batterie", CONTROLLABLE, "watt"),
        Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt"),
        Device("heizluefter_1", "Heizlüfter 1", "heizluefter_1", BINARY, "watt"),
    ]
    readings = {
        "batterie": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 0.0},
            "max_technisch": {"value": 5000.0},
        },
        "heizstab": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 500.0},
            "max_technisch": {"value": 3000.0},
            "ep_max_temperatur": {"value": 60.0},
        },
        "heizluefter_1": {"technische_freigabe": {"value": False}, "leistung_w": {"value": 1500.0}},
    }
    return build_constraints(devices, readings)


def _plan(devices, **overrides):
    base = {
        "schema_version": "1.0",
        "plan_id": "p1",
        "valid_from": "2026-06-19T12:00:00+00:00",
        "valid_until": "2026-06-19T13:00:00+00:00",
        "provider": "gemini",
        "model": "gemini-3.5-flash",
        "confidence": 80,
        "reasoning": "",
        "warnings": [],
        "devices": devices,
    }
    base.update(overrides)
    return base


def test_happy_path_ok_without_clamps():
    plan = _plan(
        [
            {
                "name": "heizstab",
                "prio_vorschlag": 2,
                "freigabe_vorschlag": True,
                "geschutzte_mindestleistung_w_vorschlag": 800.0,
                "max_temperatur_vorschlag": 55.0,
            },
            {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
        ]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    assert result.clamped == []
    assert result.errors == []


def test_protected_min_power_is_clamped_not_rejected():
    plan = _plan(
        [{"name": "heizstab", "prio_vorschlag": 1, "freigabe_vorschlag": True,
          "geschutzte_mindestleistung_w_vorschlag": 9000.0}]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok  # geklemmt, nicht abgelehnt
    assert result.normalized_plan["devices"][0]["geschutzte_mindestleistung_w_vorschlag"] == 3000.0
    assert result.clamped


def test_heizstab_temperature_is_clamped():
    plan = _plan(
        [{"name": "heizstab", "prio_vorschlag": 1, "freigabe_vorschlag": True,
          "geschutzte_mindestleistung_w_vorschlag": 600.0, "max_temperatur_vorschlag": 99.0}]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    assert result.normalized_plan["devices"][0]["max_temperatur_vorschlag"] == 60.0


def test_freigabe_override_of_technical_block_rejected():
    plan = _plan([{"name": "heizluefter_1", "prio_vorschlag": 3, "freigabe_vorschlag": True}])
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("technische" in e.lower() for e in result.errors)


def test_write_contract_violation_rejected():
    # Batterie darf keine Priorität vorschlagen (D-037).
    device = {
        "name": "batterie",
        "prio_vorschlag": 1,
        "geschutzte_mindestleistung_w_vorschlag": 1000.0,
    }
    result = validate(_plan([device]), _constraints(), now=NOW)
    assert not result.ok
    assert any("Schreibvertrag" in e for e in result.errors)


def test_unknown_device_rejected():
    plan = _plan([{"name": "spuelmaschine", "prio_vorschlag": 1, "freigabe_vorschlag": True}])
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("unbekannt" in e.lower() for e in result.errors)


def test_expired_plan_rejected():
    plan = _plan(
        [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}],
        valid_from="2026-06-19T08:00:00+00:00",
        valid_until="2026-06-19T09:00:00+00:00",
    )
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("abgelaufen" in e for e in result.errors)


def test_invalid_time_order_rejected():
    plan = _plan(
        [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}],
        valid_from="2026-06-19T14:00:00+00:00",
        valid_until="2026-06-19T15:00:00+00:00",
    )
    # valid_until liegt in der Zukunft (nicht abgelaufen), aber start < end ist verletzt:
    plan["valid_until"] = "2026-06-19T13:30:00+00:00"
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("valid_from muss vor valid_until" in e for e in result.errors)


def test_schema_failure_returns_no_normalized_plan():
    plan = _plan([{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}])
    del plan["devices"]
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert result.normalized_plan is None


def test_naive_timestamps_treated_as_utc():
    plan = _plan(
        [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}],
        valid_from="2026-06-19T12:00:00",
        valid_until="2026-06-19T13:00:00",
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
