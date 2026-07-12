"""Konvertiert die Gemini-Format-Antwortschemas in Standard-JSON-Schema (D-056).

`plan_context.build_response_schema` / `build_classification_response_schema` liefern die
Antwort-Schemas im **Gemini-Dialekt** (Großschreib-Typen `OBJECT`/`STRING`/…,
`propertyOrdering`). Claude (`output_config.format`) und OpenAI (`response_format` mit
`json_schema`) erwarten dagegen **Standard-JSON-Schema** (Kleinschreib-Typen,
`additionalProperties: false` je Objekt). Diese reine Funktion bildet den Gemini-Dialekt
verlustfrei darauf ab – der Vertrag (Felder, `required`, `enum`, `description`) bleibt gleich,
nur die Notation wechselt. Die Gemini-Schemas führen bewusst keine numerischen `min`/`max`-
Keywords (Grenzen stehen im `description`-Text), daher entsteht nichts für Claude/OpenAI
Unzulässiges.
"""

from __future__ import annotations

# Gemini-Typname (Großschreibung) -> JSON-Schema-Typname (Kleinschreibung).
_TYPE_MAP: dict[str, str] = {
    "OBJECT": "object",
    "STRING": "string",
    "INTEGER": "integer",
    "NUMBER": "number",
    "BOOLEAN": "boolean",
    "ARRAY": "array",
}


def to_json_schema(schema: dict, *, all_required: bool = False) -> dict:
    """Wandelt ein Gemini-Format-Schema rekursiv in Standard-JSON-Schema.

    - Typnamen werden kleingeschrieben; `propertyOrdering` (Gemini-spezifisch) entfällt.
    - Jedes Objekt bekommt `additionalProperties: false` (Pflicht für Claude/OpenAI-Strict).
    - `properties`/`items` werden rekursiv konvertiert; `required`/`enum`/`description` bleiben.
    - `all_required=True` (OpenAI Strict-Mode) erzwingt je Objekt `required` = alle Property-
      Keys. Der Plan-Schema-Vertrag ist per D-050 ohnehin fast vollständig „required" – real
      betrifft das nur das sonst optionale Top-Level-`warnings`.
    """
    if not isinstance(schema, dict):
        return schema

    result: dict[str, object] = {}
    for key, value in schema.items():
        if key == "propertyOrdering":
            continue  # Gemini-spezifisch, in Standard-JSON-Schema unzulässig
        if key == "type" and isinstance(value, str):
            result[key] = _TYPE_MAP.get(value, value.lower())
        elif key == "properties" and isinstance(value, dict):
            result[key] = {
                prop: to_json_schema(sub, all_required=all_required)
                for prop, sub in value.items()
            }
        elif key == "items":
            result[key] = to_json_schema(value, all_required=all_required)
        else:
            result[key] = value

    # Objekte: additionalProperties abschalten und (optional) alle Felder verpflichtend machen.
    if result.get("type") == "object":
        result["additionalProperties"] = False
        props = result.get("properties")
        if all_required and isinstance(props, dict):
            result["required"] = list(props.keys())
    return result
