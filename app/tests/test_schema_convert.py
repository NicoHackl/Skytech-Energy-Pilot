"""Tests für den Gemini→Standard-JSON-Schema-Konverter (D-056)."""

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import CONTROLLABLE, Device
from energy_pilot.plan_context import build_response_schema
from energy_pilot.schema_convert import to_json_schema

_GEMINI = {
    "type": "OBJECT",
    "properties": {
        "devices": {
            "type": "OBJECT",
            "properties": {
                "batterie": {
                    "type": "OBJECT",
                    "properties": {"name": {"type": "STRING"}, "p": {"type": "INTEGER"}},
                    "required": ["name", "p"],
                    "propertyOrdering": ["name", "p"],
                }
            },
            "required": ["batterie"],
            "propertyOrdering": ["batterie"],
        },
        "confidence": {"type": "INTEGER"},
        "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["devices", "confidence"],
    "propertyOrdering": ["devices", "confidence", "warnings"],
}


def test_types_lowercased_and_propertyordering_dropped():
    out = to_json_schema(_GEMINI)
    assert out["type"] == "object"
    assert out["properties"]["confidence"]["type"] == "integer"
    assert out["properties"]["warnings"]["type"] == "array"
    assert out["properties"]["warnings"]["items"]["type"] == "string"
    assert "propertyOrdering" not in out
    assert "propertyOrdering" not in out["properties"]["devices"]


def test_additional_properties_false_on_every_object():
    out = to_json_schema(_GEMINI)
    assert out["additionalProperties"] is False
    assert out["properties"]["devices"]["additionalProperties"] is False
    batt = out["properties"]["devices"]["properties"]["batterie"]
    assert batt["additionalProperties"] is False
    # Nicht-Objekte bekommen kein additionalProperties.
    assert "additionalProperties" not in out["properties"]["warnings"]


def test_all_required_forces_full_required_lists():
    loose = to_json_schema(_GEMINI)
    assert set(loose["required"]) == {"devices", "confidence"}  # warnings bleibt optional
    strict = to_json_schema(_GEMINI, all_required=True)
    assert set(strict["required"]) == {"devices", "confidence", "warnings"}


def test_enum_and_description_preserved():
    schema = {
        "type": "OBJECT",
        "properties": {
            "modus": {"type": "STRING", "enum": ["a", "b"], "description": "Wähle a oder b."}
        },
        "required": ["modus"],
    }
    out = to_json_schema(schema)
    assert out["properties"]["modus"]["enum"] == ["a", "b"]
    assert out["properties"]["modus"]["description"] == "Wähle a oder b."


def test_real_build_response_schema_converts_cleanly():
    devices = [Device("batterie", "Batterie", "batterie", CONTROLLABLE, "watt")]
    readings = {"batterie": {"technische_freigabe": {"value": True},
                             "min_technisch": {"value": 0.0}, "max_technisch": {"value": 5000.0}}}
    gemini_schema = build_response_schema(build_constraints(devices, readings))
    converted = to_json_schema(gemini_schema, all_required=True)
    # Keine Gemini-Reste, überall Kleinschreibung + additionalProperties.
    _assert_no_gemini_leftovers(converted)


def _assert_no_gemini_leftovers(node):
    if isinstance(node, dict):
        assert "propertyOrdering" not in node
        t = node.get("type")
        if isinstance(t, str):
            assert t == t.lower(), f"Typ nicht kleingeschrieben: {t}"
        if t == "object":
            assert node.get("additionalProperties") is False
        for value in node.values():
            _assert_no_gemini_leftovers(value)
    elif isinstance(node, list):
        for item in node:
            _assert_no_gemini_leftovers(item)
