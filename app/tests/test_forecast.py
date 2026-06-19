"""Tests für das PV-Prognose-Modell und das Config-Parsing."""

from energy_pilot.forecast import PV_VALUES, orientations_from_config


def test_pv_values_order_and_keys():
    keys = [v.key for v in PV_VALUES]
    assert keys == ["current_hour", "next_hour", "remaining_today", "tomorrow"]


def test_orientations_parsed_with_labels():
    values = {
        "pv_forecast": [
            {
                "label": "Ost",
                "current_hour": "sensor.pv_ost_jetzt",
                "next_hour": "sensor.pv_ost_1h",
                "remaining_today": "sensor.pv_ost_rest",
                "tomorrow": "sensor.pv_ost_morgen",
            },
            {"current_hour": "sensor.pv_west_jetzt"},  # Teil-Konfig, Default-Label
        ]
    }
    orientations = orientations_from_config(values)
    assert [o.label for o in orientations] == ["Ost", "Ausrichtung 2"]
    assert orientations[0].entities["tomorrow"] == "sensor.pv_ost_morgen"
    assert set(orientations[1].entities) == {"current_hour"}


def test_empty_and_invalid_entries_skipped():
    values = {
        "pv_forecast": [
            {"label": "Leer"},  # keine Entität -> übersprungen
            "kein_dict",  # ungültig -> übersprungen
            {"current_hour": "  "},  # nur Whitespace -> übersprungen
        ]
    }
    assert orientations_from_config(values) == []


def test_missing_option_yields_empty():
    assert orientations_from_config({}) == []
