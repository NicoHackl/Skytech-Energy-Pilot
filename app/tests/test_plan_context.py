"""Tests für den KI-Kontext-, Prompt- und Antwort-Schema-Aufbau (Datenminimum)."""

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device
from energy_pilot.objectives import objectives_from_config
from energy_pilot.plan_context import build_context, build_prompt, build_response_schema


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
        "heizluefter_1": {"technische_freigabe": {"value": True}, "leistung_w": {"value": 1500.0}},
    }
    return build_constraints(devices, readings)


def test_build_response_schema_is_gemini_compatible():
    schema = build_response_schema(_constraints())
    assert schema["type"] == "OBJECT"
    assert "devices" in schema["properties"]
    assert "confidence" in schema["properties"]
    # Kein JSON-Schema-Dialekt, den Gemini ablehnt:
    assert "$schema" not in schema
    assert "additionalProperties" not in schema
    assert schema["properties"]["devices"]["items"]["properties"]["name"]["type"] == "STRING"


def test_build_context_is_data_minimum():
    state = {
        "pv_power": {
            "label": "PV", "unit": "W", "averaged": True, "source": "live",
            "latest": 1000.0, "mean_1m": 900.0, "mean_15m": None, "mean_60m": None,
        },
        "battery_soc": {
            "label": "SOC", "unit": "%", "averaged": False, "source": "live", "value": 55.0,
        },
    }
    forecast = {
        "unit": "kWh",
        "values": [{"key": "current_hour", "label": "Akt", "unit": "kWh", "total": 2.0}],
        "orientations": [{"label": "S", "values": {}}],
    }
    ctx = build_context(
        state, forecast, _constraints(), objectives_from_config({}),
        valid_from="A", valid_until="B",
    )

    assert ctx["valid_from"] == "A"
    assert ctx["valid_until"] == "B"
    # Prognose verdichtet: nur Summen, keine Einzel-Ausrichtungen (Datenminimum).
    assert "orientations" not in ctx["forecast"]
    # Batterie darf nur die geschützte Mindestleistung vorschlagen (D-037).
    battery = next(d for d in ctx["devices"] if d["name"] == "batterie")
    assert battery["allowed_fields"] == ["geschutzte_mindestleistung_w_vorschlag"]
    # Mittelwerte: None-Felder werden weggelassen, vorhandene bleiben.
    pv = next(s for s in ctx["state"] if s["role"] == "pv_power")
    assert pv["mean_1m"] == 900.0
    assert "mean_15m" not in pv
    soc = next(s for s in ctx["state"] if s["role"] == "battery_soc")
    assert soc["value"] == 55.0


def test_build_prompt_contains_rules_and_data():
    ctx = build_context(
        {}, {}, _constraints(), objectives_from_config({}), valid_from="A", valid_until="B"
    )
    prompt = build_prompt(ctx)
    assert isinstance(prompt, str)
    assert "Orchestrator" in prompt
    assert "heizstab" in prompt  # die verdichteten Gerätedaten stehen im Prompt
