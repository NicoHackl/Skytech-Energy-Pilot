"""Kontext-, Prompt- und Antwort-Schema-Aufbau für die KI-Planung (Doc 04/07).

Hier wird der **Datenminimum**-Kontext für die KI zusammengestellt (Iron Rule 7):
nur verdichtete, freigegebene Werte (Zustand, PV-Prognose, harte Grenzen, Ziele) –
kein Roh-Dump der HA-Datenbank. Der Prompt erklärt der KI ihre Rolle als
Orchestrator und die je Gerät **erlaubten** Vorschlagsfelder; das Antwort-Schema
zwingt strukturiertes JSON. Die fachliche Grenzprüfung macht danach `validator.py`.
"""

from __future__ import annotations

import json

from energy_pilot.constraints import DeviceConstraint
from energy_pilot.devices import BINARY
from energy_pilot.objectives import Objective
from energy_pilot.plan_schema import suggestion_keys


def _condense_state(state: dict) -> list[dict]:
    """Verdichtet den State-Snapshot je Rolle auf das Nötigste (Werte + Mittel)."""
    out: list[dict] = []
    for role, info in state.items():
        entry: dict[str, object] = {
            "role": role,
            "label": info.get("label"),
            "unit": info.get("unit"),
        }
        if "value" in info:  # Zustandsgrößen: nur Letztwert (SOC, Temperatur …)
            entry["value"] = info.get("value")
        else:  # Messgrößen: Letztwert + 1/15/60-min-Mittel (nur vorhandene)
            entry["latest"] = info.get("latest")
            for key in ("mean_1m", "mean_15m", "mean_60m"):
                if info.get(key) is not None:
                    entry[key] = info[key]
        out.append(entry)
    return out


def _condense_forecast(forecast: dict) -> dict:
    """Reduziert die PV-Prognose auf die summierten Werte (keine Einzel-Ausrichtungen)."""
    if not forecast:
        return {}
    return {
        "unit": forecast.get("unit"),
        "values": [
            {"key": v.get("key"), "label": v.get("label"), "total": v.get("total")}
            for v in forecast.get("values", [])
        ],
    }


def _condense_constraint(constraint: DeviceConstraint) -> dict:
    """Beschreibt ein Gerät für die KI: harte Grenzen + erlaubte Vorschlagsfelder."""
    entry: dict[str, object] = {
        "name": constraint.name,
        "label": constraint.label,
        "class": constraint.device_class,
        "output_unit": constraint.output_unit,
        "technische_freigabe": constraint.freigabe,
        "allowed_fields": suggestion_keys(constraint),
    }
    if constraint.is_battery:
        entry["max_ladeleistung_w"] = constraint.max_power
        entry["hinweis"] = "immer Prio 1, immer freigegeben (D-016)"
    elif constraint.device_class == BINARY:
        entry["feste_leistung_w"] = constraint.fixed_power
    else:
        entry["min_leistung"] = constraint.min_power
        entry["max_leistung"] = constraint.max_power
        if constraint.is_heizstab:
            entry["max_wassertemperatur"] = constraint.max_water_temp
    return entry


def build_context(
    state: dict,
    forecast: dict,
    constraints: list[DeviceConstraint],
    objectives: list[Objective],
    *,
    valid_from: str,
    valid_until: str,
) -> dict:
    """Stellt den verdichteten KI-Kontext zusammen (Datenminimum, Iron Rule 7)."""
    return {
        "valid_from": valid_from,
        "valid_until": valid_until,
        "state": _condense_state(state),
        "forecast": _condense_forecast(forecast),
        "devices": [_condense_constraint(c) for c in constraints],
        "objectives": [
            {"key": o.key, "label": o.label, "weight": o.weight} for o in objectives
        ],
    }


def build_prompt(context: dict) -> str:
    """Baut den deutschen Planungs-Prompt aus dem verdichteten Kontext."""
    data = json.dumps(context, ensure_ascii=False, indent=2)
    return (
        "Du bist der Energie-Orchestrator des Home-Assistant-Addons „Skytech Energy Pilot“.\n"
        "Erzeuge aus den folgenden Daten einen vorausschauenden Energieplan als "
        "Vorschlagswerte. Du bist KEIN Regler und steuerst keine Geräte direkt.\n\n"
        "Harte Regeln:\n"
        "- Halte die harten Grenzen jedes Geräts strikt ein; überschreite sie nie.\n"
        "- Gib pro Gerät NUR die Felder aus, die in dessen `allowed_fields` stehen.\n"
        "- Eine technisch gesperrte Last (technische_freigabe=false) darfst du nicht "
        "freigeben.\n"
        "- Prioritäten von Geräten darfst du nur in 10er Schritten von 10 - 100 setzten."
        "10 ist dabei die höchste, und 100 die niedrigste Priorität."
        "Dabei muss es mit Prio 10 beginnen und immer um 10 aufsteigen z.b. 10, 20 ,30\n"
        "- Die Batterie hat immer Priorität 1 und ist immer freigegeben; schlage für sie "
        "nur die geschützte Mindest-Ladeleistung vor.\n"
        "- Erfinde keine Geräte; verwende exakt die `name`-Werte aus `devices`.\n"
        "- Gewichte die weichen Ziele gemäß `objectives` (0–100 %).\n\n"
        "Gib zusätzlich `confidence` (0–100), eine kurze deutsche `reasoning`-Begründung "
        "und optionale `warnings` aus. Antworte ausschließlich als JSON gemäß dem "
        "vorgegebenen Schema.\n\n"
        f"Daten:\n{data}\n"
    )


def build_response_schema(constraints: list[DeviceConstraint]) -> dict:
    """Gemini-kompatibles Antwort-Schema (OpenAPI-Subset, Typ-Enums in Großschreibung).

    Bewusst NICHT `PLAN_JSON_SCHEMA` (nutzt `const`/`$schema`/`additionalProperties`,
    die Gemini nicht unterstützt). Die Geräte-Properties sind die **Vereinigung** aller
    möglichen Vorschlagsfelder; die Vertragstreue je Gerät erzwingt der Validator.
    """
    device_properties = {
        "name": {"type": "STRING"},
        "prio_vorschlag": {"type": "INTEGER"},
        "freigabe_vorschlag": {"type": "BOOLEAN"},
        "geschutzte_mindestleistung_w_vorschlag": {"type": "NUMBER"},
        "geschutzte_mindestleistung_a_vorschlag": {"type": "NUMBER"},
        "max_temperatur_vorschlag": {"type": "NUMBER"},
    }
    return {
        "type": "OBJECT",
        "properties": {
            "devices": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": device_properties,
                    "required": ["name"],
                },
            },
            "confidence": {"type": "INTEGER"},
            "reasoning": {"type": "STRING"},
            "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["devices", "confidence", "reasoning"],
    }
