"""Plan-JSON-Schema + Datenstrukturen des Kandidatenplans (D-008/D-030/D-034).

Definiert die **strukturelle** Form eines Energieplans (versioniert über
`schema_version`, da das Schema später gemeinsam mit HEMS gepflegt wird, offener
Punkt in [08-validierung-sicherheit.md]). Hier liegt nur die Struktur-/Typprüfung
(JSON-Schema). Die **fachliche** Grenzprüfung gegen die harten Grenzen
(constraints.py) macht der Validator (validator.py).

V1-Schreibvertrag je Gerät (D-030/D-034/D-037/D-047):
- regelbar/binär: `prio_vorschlag`, `freigabe_vorschlag`
- regelbar zusätzlich: `geschutzte_mindestleistung_{w|a}_vorschlag`
- **Batterie:** nur `geschutzte_mindestleistung_w_vorschlag` (D-037)
- **Zusatz-Entitäten (D-047):** je aktivierter Zusatz-Entität ein dynamisches Feld
  `extra_<obj>_vorschlag` (löst den früheren Heizstab-Hardcode `max_temperatur_vorschlag`
  D-035 ab). Diese Felder sind advisorisch (nur HA-Sensor), unterliegen keiner harten Grenze.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import jsonschema

from energy_pilot.constraints import DeviceConstraint
from energy_pilot.devices import BINARY

# Versionierung des Plan-Schemas (mit HEMS gemeinsam zu pflegen).
SCHEMA_VERSION = "1.0"

# Feste Vorschlagsfelder eines Geräts (Reihenfolge = Serialisierungsreihenfolge). Zusatz-
# Entitäten (D-047) kommen als dynamische `extra_<obj>_vorschlag`-Felder hinzu (siehe unten).
SUGGESTION_FIELDS: tuple[str, ...] = (
    "prio_vorschlag",
    "freigabe_vorschlag",
    "geschutzte_mindestleistung_w_vorschlag",
    "geschutzte_mindestleistung_a_vorschlag",
)

# Muster der dynamischen Zusatz-Vorschlagsfelder (D-047), z.B. `extra_min_soc_auto_vorschlag`.
EXTRA_FIELD_RE = re.compile(r"^extra_[a-z0-9_]+_vorschlag$")


def is_extra_field(key: str) -> bool:
    """True, wenn `key` ein dynamisches Zusatz-Vorschlagsfeld ist (D-047)."""
    return bool(EXTRA_FIELD_RE.match(key))


@dataclass
class DeviceSuggestion:
    """Vorschlagswerte für genau ein Gerät (nicht gesetzte Felder bleiben None).

    `extras` hält die dynamischen Zusatz-Vorschläge (D-047) als `{extra_<obj>_vorschlag: wert}`.
    """

    name: str
    prio_vorschlag: int | None = None
    freigabe_vorschlag: bool | None = None
    geschutzte_mindestleistung_w_vorschlag: float | None = None
    geschutzte_mindestleistung_a_vorschlag: float | None = None
    extras: dict[str, float] = field(default_factory=dict)


@dataclass
class CandidatePlan:
    """Ein vollständiger Kandidatenplan (interne Repräsentation der Engine)."""

    plan_id: str
    valid_from: str
    valid_until: str
    devices: list[DeviceSuggestion]
    provider: str = ""
    model: str = ""
    confidence: int | None = None
    reasoning: str = ""
    warnings: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


def extra_suggestion_keys(constraint: DeviceConstraint) -> list[str]:
    """Dynamische Zusatz-Vorschlagsfelder eines Geräts (D-047): nur aktivierte Zusatz-Entitäten."""
    return [ce.extra.plan_field for ce in constraint.extras if ce.extra.ai_suggestion]


def suggestion_keys(constraint: DeviceConstraint) -> list[str]:
    """Liefert die je Gerät **erlaubten** Vorschlagsfelder (Schreibvertrag, D-030 ff./D-047).

    Fixe Felder nach Geräteklasse plus die dynamischen `extra_<obj>_vorschlag`-Felder der
    aktivierten Zusatz-Entitäten (D-047).
    """
    if constraint.is_battery:
        keys = ["geschutzte_mindestleistung_w_vorschlag"]  # D-037
    elif constraint.device_class == BINARY:
        keys = ["prio_vorschlag", "freigabe_vorschlag"]
    else:
        suffix = "a" if constraint.output_unit == "ampere" else "w"
        keys = [
            "prio_vorschlag",
            "freigabe_vorschlag",
            f"geschutzte_mindestleistung_{suffix}_vorschlag",
        ]
    return keys + extra_suggestion_keys(constraint)


def plan_to_dict(plan: CandidatePlan) -> dict:
    """Serialisiert einen Plan in die kanonische JSON-Form (None-Felder entfallen)."""
    devices: list[dict] = []
    for suggestion in plan.devices:
        entry: dict[str, object] = {"name": suggestion.name}
        for key in SUGGESTION_FIELDS:
            value = getattr(suggestion, key)
            if value is not None:
                entry[key] = value
        # Dynamische Zusatz-Vorschläge (D-047) flach in den Geräteeintrag übernehmen.
        for key, value in suggestion.extras.items():
            if value is not None:
                entry[key] = value
        devices.append(entry)
    return {
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "valid_from": plan.valid_from,
        "valid_until": plan.valid_until,
        "provider": plan.provider,
        "model": plan.model,
        "confidence": plan.confidence,
        "reasoning": plan.reasoning,
        "warnings": list(plan.warnings),
        "devices": devices,
    }


# Strukturelles JSON-Schema (Draft 2020-12). Nur Form/Typen — fachliche Grenzen prüft der Validator.
PLAN_JSON_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema_version", "plan_id", "valid_from", "valid_until", "devices"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "plan_id": {"type": "string", "minLength": 1},
        "valid_from": {"type": "string", "minLength": 1},
        "valid_until": {"type": "string", "minLength": 1},
        "provider": {"type": "string"},
        "model": {"type": "string"},
        "confidence": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
        "reasoning": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "devices": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "additionalProperties": False,
                # Zusatz-Vorschläge (D-047/D-048): beliebig viele `extra_<obj>_vorschlag`.
                # Typ je nach Domäne der Quell-Entität (Zahl/Bool/Text/Datum-als-String); den
                # konkreten Schreibvertrag je Gerät erzwingt der Validator (suggestion_keys).
                "patternProperties": {
                    r"^extra_[a-z0-9_]+_vorschlag$": {"type": ["number", "boolean", "string"]},
                },
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    # Prio hier bewusst nur strukturell (integer): die eindeutige
                    # 10er-Rangfolge erzwingt der Validator per Normalisierung. Eine
                    # strenge Schemagrenze würde nicht-konforme Werte schon in Stufe 1
                    # ablehnen, statt sie (gewünscht) zu normalisieren.
                    "prio_vorschlag": {"type": "integer"},
                    "freigabe_vorschlag": {"type": "boolean"},
                    "geschutzte_mindestleistung_w_vorschlag": {"type": "number", "minimum": 0},
                    "geschutzte_mindestleistung_a_vorschlag": {"type": "number", "minimum": 0},
                },
            },
        },
    },
}


def schema_errors(plan_dict: dict) -> list[str]:
    """Prüft einen Plan-Dict gegen `PLAN_JSON_SCHEMA`; liefert Fehlermeldungen (leer = ok)."""
    validator = jsonschema.Draft202012Validator(PLAN_JSON_SCHEMA)
    messages: list[str] = []
    for error in sorted(validator.iter_errors(plan_dict), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in error.path) or "<root>"
        messages.append(f"{path}: {error.message}")
    return messages
