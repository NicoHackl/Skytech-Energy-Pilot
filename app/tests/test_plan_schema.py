"""Tests für das Plan-JSON-Schema, den Schreibvertrag und die Serialisierung."""

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device, DeviceExtra
from energy_pilot.plan_schema import (
    SCHEMA_VERSION,
    CandidatePlan,
    DeviceSuggestion,
    plan_to_dict,
    schema_errors,
    suggestion_keys,
)


def _con(name, cls=CONTROLLABLE, unit="watt", extras=()):
    return build_constraints([Device(name, name.title(), name, cls, unit, extras=extras)], {})[0]


def test_battery_suggestion_keys_only_protected_min():
    assert suggestion_keys(_con("batterie")) == ["geschutzte_mindestleistung_w_vorschlag"]


def test_binary_suggestion_keys():
    keys = suggestion_keys(_con("heizluefter_1", cls=BINARY))
    assert keys == ["prio_vorschlag", "freigabe_vorschlag"]


def test_active_extra_adds_dynamic_suggestion_key():
    # Aktivierte Zusatz-Entität (D-047) fügt ihr `extra_<obj>_vorschlag`-Feld dem Vertrag hinzu.
    extra = DeviceExtra(
        read_entity_id="input_number.ep_heizstab_max_temperatur", ai_suggestion=True
    )
    keys = suggestion_keys(_con("heizstab", extras=(extra,)))
    assert "extra_heizstab_max_temperatur_vorschlag" in keys
    assert "geschutzte_mindestleistung_w_vorschlag" in keys


def test_inactive_extra_not_in_suggestion_keys():
    # Ohne KI-Vorschlag (Checkbox aus) taucht das Feld NICHT im Schreibvertrag auf.
    extra = DeviceExtra(read_entity_id="input_number.min_soc_auto", ai_suggestion=False)
    keys = suggestion_keys(_con("heizstab", extras=(extra,)))
    assert not any(k.startswith("extra_") for k in keys)


def test_ampere_controllable_uses_a_suffix():
    keys = suggestion_keys(_con("wallbox", unit="ampere"))
    assert "geschutzte_mindestleistung_a_vorschlag" in keys
    assert "geschutzte_mindestleistung_w_vorschlag" not in keys


def _valid_plan_dict():
    plan = CandidatePlan(
        plan_id="p1",
        valid_from="2026-06-19T12:00:00+00:00",
        valid_until="2026-06-19T13:00:00+00:00",
        devices=[
            DeviceSuggestion(
                name="heizstab",
                prio_vorschlag=2,
                freigabe_vorschlag=True,
                geschutzte_mindestleistung_w_vorschlag=500.0,
                extras={"extra_heizstab_max_temperatur_vorschlag": 60.0},
            )
        ],
        provider="gemini",
        model="gemini-3.5-flash",
        confidence=85,
        reasoning="weil PV-Überschuss erwartet",
    )
    return plan_to_dict(plan)


def test_plan_to_dict_omits_none_and_sets_version():
    plan = CandidatePlan(
        "p", "a", "b",
        [DeviceSuggestion("batterie", geschutzte_mindestleistung_w_vorschlag=3000.0)],
    )
    payload = plan_to_dict(plan)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["devices"][0] == {
        "name": "batterie",
        "geschutzte_mindestleistung_w_vorschlag": 3000.0,
    }


def test_valid_plan_passes_schema():
    assert schema_errors(_valid_plan_dict()) == []


def test_missing_required_field_fails_schema():
    plan = _valid_plan_dict()
    del plan["plan_id"]
    assert schema_errors(plan)


def test_unknown_device_field_rejected_by_schema():
    plan = _valid_plan_dict()
    plan["devices"][0]["unbekannt"] = 1
    assert schema_errors(plan)


def test_wrong_schema_version_fails():
    plan = _valid_plan_dict()
    plan["schema_version"] = "9.9"
    assert schema_errors(plan)


def test_plan_to_dict_flattens_extras():
    plan = CandidatePlan(
        "p", "a", "b",
        [DeviceSuggestion("heizstab", extras={"extra_min_soc_auto_vorschlag": 42.0})],
    )
    assert plan_to_dict(plan)["devices"][0] == {
        "name": "heizstab",
        "extra_min_soc_auto_vorschlag": 42.0,
    }


def test_dynamic_extra_field_accepted_by_schema():
    plan = _valid_plan_dict()  # enthält bereits ein `extra_*_vorschlag`-Feld
    assert any("extra_" in k for k in plan["devices"][0])
    assert schema_errors(plan) == []
