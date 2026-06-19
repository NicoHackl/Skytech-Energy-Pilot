"""Tests für den User-Objective-Manager (weiche Zielgewichte, D-011)."""

from energy_pilot.objectives import DEFAULT_OBJECTIVES, objectives_from_config


def test_default_objectives_match_info_md_section7():
    weights = {o.key: o.weight for o in DEFAULT_OBJECTIVES}
    assert weights == {
        "versorgungssicherheit": 100,
        "eauto_ladeziel": 100,
        "warmwasserkomfort": 100,
        "netzbezug": 90,
        "stromkosten": 85,
        "eigenverbrauch": 80,
        "einspeisung": 70,
        "batterieschonung": 50,
    }


def test_missing_option_yields_defaults():
    result = objectives_from_config({})
    assert [o.weight for o in result] == [o.weight for o in DEFAULT_OBJECTIVES]


def test_config_overrides_selected_weights():
    overrides = {"objective_weights": {"netzbezug": 50, "batterieschonung": 0}}
    result = {o.key: o.weight for o in objectives_from_config(overrides)}
    assert result["netzbezug"] == 50
    assert result["batterieschonung"] == 0
    assert result["versorgungssicherheit"] == 100  # unverändert


def test_weights_are_clamped_and_invalid_fall_back():
    result = {
        o.key: o.weight
        for o in objectives_from_config(
            {"objective_weights": {"netzbezug": 250, "stromkosten": -5, "eigenverbrauch": "abc"}}
        )
    }
    assert result["netzbezug"] == 100  # auf 100 geklemmt
    assert result["stromkosten"] == 0  # auf 0 geklemmt
    assert result["eigenverbrauch"] == 80  # ungültig -> Default


def test_unknown_keys_ignored_and_non_dict_is_safe():
    result = objectives_from_config({"objective_weights": {"unbekannt": 10}})
    assert [o.weight for o in result] == [o.weight for o in DEFAULT_OBJECTIVES]
    safe = objectives_from_config({"objective_weights": "kein_dict"})
    assert [o.weight for o in safe] == [o.weight for o in DEFAULT_OBJECTIVES]
