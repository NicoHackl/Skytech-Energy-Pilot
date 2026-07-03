"""Kontext-, Prompt- und Antwort-Schema-Aufbau für die KI-Planung (Doc 04/07).

Hier wird der **Datenminimum**-Kontext für die KI zusammengestellt (Iron Rule 7):
nur verdichtete, freigegebene Werte (Zustand, PV-Prognose, harte Grenzen, Ziele) –
kein Roh-Dump der HA-Datenbank. Der Prompt erklärt der KI ihre Rolle als
Orchestrator und die je Gerät **erlaubten** Vorschlagsfelder; das Antwort-Schema
zwingt strukturiertes JSON. Die fachliche Grenzprüfung macht danach `validator.py`.
"""

from __future__ import annotations

import json
import math

from energy_pilot.constraints import DeviceConstraint
from energy_pilot.devices import BINARY
from energy_pilot.objectives import Objective
from energy_pilot.plan_schema import suggestion_keys

# Zusatz-Entität-Typ (D-048) -> Gemini-Antwort-Schema-Typ (OpenAPI-Subset, Großschreibung).
_KIND_TO_GEMINI: dict[str, str] = {
    "number": "NUMBER",
    "bool": "BOOLEAN",
    "datetime": "STRING",
    "text": "STRING",
}


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


# OWM liefert die Prognose in 3-Stunden-Schritten; daraus folgt die Schrittzahl je Horizont.
_FORECAST_STEP_H = 3
# Schrittweite je One-Call-Timeline (Minuten) – für die Kürzung auf den Planungshorizont.
_ONECALL_STEP_MIN = {"15min": 15, "1h": 60, "1day": 24 * 60}


def _condense_onecall(weather: dict, *, horizon_h: int) -> dict:
    """Verdichtet die in `weather.llm_timeline` gewählte One-Call-Timeline für den KI-Kontext.

    Es geht **genau eine** Timeline ans LLM (Token-Budget): 15min/1h werden auf
    `forecast_horizon_h` gekürzt, `1day` komplett übernommen. Behalten werden nur
    energierelevante Felder (Temperatur, Bewölkung, Regenwahrscheinlichkeit; bei `1day`
    zusätzlich Min/Max). Leer, wenn die gewählte Timeline keine Schritte hat.
    """
    timeline = weather.get("llm_timeline") or "1h"
    tl = (weather.get("timelines") or {}).get(timeline) or {}
    slots = tl.get("slots") or []
    if not slots:
        return {}
    if timeline == "1day":
        chosen = slots
    else:
        step_min = _ONECALL_STEP_MIN.get(timeline, 60)
        max_steps = max(1, math.ceil(horizon_h * 60 / step_min))
        chosen = slots[:max_steps]
    out_slots: list[dict] = []
    for s in chosen:
        item = {
            "time": s.get("time"),
            "temp": s.get("temp"),
            "clouds": s.get("clouds"),
            "pop": s.get("pop"),
        }
        if timeline == "1day":
            item["temp_min"] = s.get("temp_min")
            item["temp_max"] = s.get("temp_max")
        out_slots.append(item)
    return {
        "source": "onecall",
        "timeline": timeline,
        "units": weather.get("units"),
        "slots": out_slots,
    }


def _condense_weather(weather: dict, *, horizon_h: int, detail: str) -> dict:
    """Verdichtet die OWM-Wetterprognose für den KI-Kontext (quellen-/detailabhängig).

    Bei `source="onecall"` geht die konfigurierte Timeline (`llm_timeline`) ein (siehe
    `_condense_onecall`). Sonst (forecast3h): `compact` (Default) = Temperatur/Bewölkung/
    Regenwahrscheinlichkeit je 3-Stunden-Schritt bis zum Planungshorizont (Datenminimum,
    Iron Rule 7); `full` = komplette 5-Tage-Prognose mit allen Feldern. Leer ohne Prognose.
    """
    if not weather:
        return {}
    if weather.get("source") == "onecall":
        return _condense_onecall(weather, horizon_h=horizon_h)
    forecast = weather.get("forecast")
    if not forecast:
        return {}
    slots = forecast.get("slots") or []

    if detail == "full":
        out_slots = [
            {
                "time": s.get("time"),
                "temp": s.get("temp"),
                "feels_like": s.get("feels_like"),
                "clouds": s.get("clouds"),
                "pop": s.get("pop"),
                "wind_speed": s.get("wind_speed"),
                "humidity": s.get("humidity"),
                "rain_3h": s.get("rain_3h"),
                "snow_3h": s.get("snow_3h"),
                "condition": s.get("condition"),
            }
            for s in slots
        ]
    else:  # compact
        max_steps = max(1, math.ceil(horizon_h / _FORECAST_STEP_H))
        out_slots = [
            {
                "time": s.get("time"),
                "temp": s.get("temp"),
                "clouds": s.get("clouds"),
                "pop": s.get("pop"),
            }
            for s in slots[:max_steps]
        ]

    return {
        "city": forecast.get("city"),
        "detail": detail,
        "units": weather.get("units"),
        "slots": out_slots,
    }


def _datetime_format(has_date: bool | None, has_time: bool | None) -> str:
    """Erwartetes String-Format eines input_datetime-Vorschlags aus has_date/has_time (D-048)."""
    if has_date and has_time:
        return "YYYY-MM-DD HH:MM:SS (Datum und Uhrzeit)"
    if has_time and not has_date:
        return "HH:MM:SS (nur Uhrzeit)"
    if has_date and not has_time:
        return "YYYY-MM-DD (nur Datum)"
    return "YYYY-MM-DD HH:MM:SS"


def _condense_extra(ce) -> dict:
    """Verdichtet eine Zusatz-Entität für den KI-Kontext (Wert + Typ + Grenzen/Format, D-048)."""
    ex = ce.extra
    item: dict[str, object] = {
        "entity": ex.read_entity_id,
        "label": ex.display_label,
        "typ": ce.kind,
        "wert": ce.value,
        "einheit": ex.unit or None,
        "hinweis": ex.ai_hint or None,
        "suggest": ex.ai_suggestion,
        "vorschlagsfeld": ex.plan_field if ex.ai_suggestion else None,
    }
    # input_number: min/max als Ober-/Untergrenze für die KI (D-048).
    if ce.kind == "number" and (ce.min is not None or ce.max is not None):
        item["untergrenze"] = ce.min
        item["obergrenze"] = ce.max
    # input_datetime: erwartetes String-Format aus has_date/has_time (D-048).
    if ce.kind == "datetime":
        item["format"] = _datetime_format(ce.has_date, ce.has_time)
    # input_select: der Auswahlpool ist die erlaubte Wertemenge für den Vorschlag (D-049).
    if ce.kind == "select" and ce.options:
        item["optionen"] = list(ce.options)
    return item


def _condense_constraint(constraint: DeviceConstraint) -> dict:
    """Beschreibt ein Gerät für die KI: harte Grenzen + erlaubte Vorschlagsfelder + Zusatzwerte."""
    entry: dict[str, object] = {
        "name": constraint.name,
        "label": constraint.label,
        "class": constraint.device_class,
        "output_unit": constraint.output_unit,
        "technische_freigabe": constraint.freigabe,
        "allowed_fields": suggestion_keys(constraint),
    }
    # User-gepflegte Freitext-Beschreibung dieses Geräts (D-051): erklärt der KI dessen
    # Funktion/Besonderheiten. Nur wenn gesetzt, um den Kontext schlank zu halten (Iron Rule 7).
    if constraint.ai_prompt:
        entry["funktion"] = constraint.ai_prompt
    if constraint.is_battery:
        entry["max_ladeleistung_w"] = constraint.max_power
        entry["hinweis"] = "immer Prio 1, immer freigegeben (D-016)"
    elif constraint.device_class == BINARY:
        entry["feste_leistung_w"] = constraint.fixed_power
    else:
        entry["min_leistung"] = constraint.min_power
        entry["max_leistung"] = constraint.max_power

    # User-gepflegte Zusatz-Entitäten (D-047/D-048): Wert + Typ + Grenzen/Format + Freitext.
    # `suggest`/`vorschlagsfeld` sagen der KI, ob/unter welchem Feld sie einen Wert liefert.
    if constraint.extras:
        entry["zusatzwerte"] = [_condense_extra(ce) for ce in constraint.extras]
    return entry


def build_context(
    state: dict,
    forecast: dict,
    constraints: list[DeviceConstraint],
    objectives: list[Objective],
    *,
    valid_from: str,
    valid_until: str,
    weather: dict | None = None,
    horizon_h: int = 24,
    weather_detail: str = "compact",
) -> dict:
    """Stellt den verdichteten KI-Kontext zusammen (Datenminimum, Iron Rule 7)."""
    return {
        "valid_from": valid_from,
        "valid_until": valid_until,
        "state": _condense_state(state),
        "forecast": _condense_forecast(forecast),
        "weather": _condense_weather(weather or {}, horizon_h=horizon_h, detail=weather_detail),
        "devices": [_condense_constraint(c) for c in constraints],
        "objectives": [
            {"key": o.key, "label": o.label, "weight": o.weight} for o in objectives
        ],
    }


# Standard-Instruktion für die Planung. Über die EP-Oberfläche editierbar (in der
# `config`-Tabelle persistiert); der `Daten:`-Block wird IMMER von `build_prompt`
# angehängt, das Antwort-Schema bleibt code-kontrolliert und der Validator erzwingt die
# harten Grenzen unabhängig vom Prompt (Iron Rules 5/6).
DEFAULT_PLANNING_PROMPT = (
    "Du bist der Energie-Orchestrator des Home-Assistant-Addons „Skytech Energy Pilot“.\n"
    "Erzeuge aus den folgenden Daten einen vorausschauenden Energieplan als "
    "Vorschlagswerte. Du bist KEIN Regler und steuerst keine Geräte direkt.\n\n"
    "Harte Regeln:\n"
    "- Halte die harten Grenzen jedes Geräts strikt ein; überschreite sie nie.\n"
    "- Gib pro Gerät NUR die Felder aus, die in dessen `allowed_fields` stehen.\n"
    "- Eine technisch gesperrte Last (technische_freigabe=false) darfst du nicht "
    "freigeben.\n"
    "- Vergib den Geräten (NICHT der Batterie) eine eindeutige Rangfolge als "
    "`prio_vorschlag`: beginne bei 10 (höchste Priorität) und steigere in "
    "10er-Schritten – 10, 20, 30 … Keine Werte doppelt, keine Lücken, höchstens 100.\n"
    "- Die Batterie ist konzeptionell stets vorrangig und immer freigegeben; sie "
    "bekommt KEINE Priorität – schlage für sie nur die geschützte "
    "Mindest-Ladeleistung vor.\n"
    "- Erfinde keine Geräte; verwende exakt die `name`-Werte aus `devices`.\n"
    "- Gewichte die weichen Ziele gemäß `objectives` (0–100 %).\n"
    "- Beziehe die Wetterprognose (`weather`) in die Planung ein: hohe Bewölkung "
    "(`clouds`) und Regenwahrscheinlichkeit (`pop`) senken die erwartete PV-Erzeugung, "
    "niedrige Temperaturen erhöhen tendenziell den Heizbedarf.\n"
    "- Beachte `zusatzwerte` je Gerät: der aktuelle Wert und der `hinweis` erklären dir "
    "dessen Bedeutung. Hat ein Zusatzwert `suggest=true`, liefere deinen Vorschlag exakt "
    "unter dem Feldnamen aus `vorschlagsfeld` (nur diese Felder sind in `allowed_fields`).\n"
    "- Hat ein Gerät das Feld `funktion`, ist das eine vom User verfasste Beschreibung seiner "
    "Funktion/Besonderheiten; berücksichtige sie bei der Planung dieses Geräts.\n\n"
    "Gib zusätzlich `confidence` (0–100), eine kurze deutsche `reasoning`-Begründung "
    "und optionale `warnings` aus. Antworte ausschließlich als JSON gemäß dem "
    "vorgegebenen Schema."
)


def build_prompt(context: dict, template: str | None = None) -> str:
    """Baut den Planungs-Prompt: (editierbare) Instruktion + angehängter Datenblock.

    `template` ist die optional vom User in der EP-Oberfläche gepflegte Instruktion;
    fehlt sie, gilt `DEFAULT_PLANNING_PROMPT`. Der `Daten:`-Block wird unabhängig vom
    Template immer angehängt, damit der Kontext nie versehentlich fehlt.
    """
    instruction = (template or "").strip() or DEFAULT_PLANNING_PROMPT
    data = json.dumps(context, ensure_ascii=False, indent=2)
    return f"{instruction}\n\nDaten:\n{data}\n"


def _extra_field_schema(ce) -> dict:
    """Antwort-Schema-Property eines Zusatz-Vorschlagsfelds (Typ/Enum/Beschreibung, D-047 ff.)."""
    prop: dict[str, object] = {"type": _KIND_TO_GEMINI.get(ce.kind, "STRING")}
    desc: list[str] = []
    if ce.extra.ai_hint:
        desc.append(ce.extra.ai_hint)
    if ce.kind == "number" and (ce.min is not None or ce.max is not None):
        lo = "-unendlich" if ce.min is None else ce.min
        hi = "unendlich" if ce.max is None else ce.max
        desc.append(f"Wertebereich {lo} bis {hi}.")
    elif ce.kind == "datetime":
        desc.append(f"Format {_datetime_format(ce.has_date, ce.has_time)}.")
    elif ce.kind == "select" and ce.options:
        # Auswahlpool als Enum erzwingen (D-049): die KI MUSS genau eine Option wählen.
        prop["enum"] = list(ce.options)
        desc.append("Wähle genau einen dieser Werte: " + ", ".join(ce.options) + ".")
    if desc:
        prop["description"] = " ".join(str(p) for p in desc)
    return prop


def _fixed_field_schema(key: str) -> dict:
    """Antwort-Schema-Property eines festen Vorschlagsfelds (Prio/Freigabe/Mindestleistung)."""
    if key == "prio_vorschlag":
        return {
            "type": "INTEGER",
            "description": "10er-Rangfolge ab 10 (höchste Prio); nicht für die Batterie.",
        }
    if key == "freigabe_vorschlag":
        return {"type": "BOOLEAN"}
    return {"type": "NUMBER"}  # geschutzte_mindestleistung_{w,a}_vorschlag


def _device_response_schema(constraint: DeviceConstraint) -> dict:
    """Antwort-Schema genau eines Geräts: nur die erlaubten Felder, ALLE als Pflicht.

    Kernfix gegen schwankende Ausgabefelder (D-050): `required` = exakt der Schreibvertrag
    dieses Geräts (`suggestion_keys`), sodass das Modell KEIN gefordertes Feld weglassen darf
    (auch nicht die früher „vergessene" Max-Wassertemperatur). `propertyOrdering` stabilisiert
    zusätzlich die Ausgabe (Gemini-Empfehlung für reproduzierbare strukturierte Antworten).
    """
    keys = suggestion_keys(constraint)
    extra_by_field = {
        ce.extra.plan_field: ce for ce in constraint.extras if ce.extra.ai_suggestion
    }
    properties: dict[str, object] = {"name": {"type": "STRING"}}
    for key in keys:
        properties[key] = (
            _extra_field_schema(extra_by_field[key])
            if key in extra_by_field
            else _fixed_field_schema(key)
        )
    return {
        "type": "OBJECT",
        "properties": properties,
        "required": ["name", *keys],
        "propertyOrdering": ["name", *keys],
    }


def build_response_schema(constraints: list[DeviceConstraint]) -> dict:
    """Gemini-Antwort-Schema mit per-Gerät **erzwungenen** Pflichtfeldern (Kernfix D-050).

    Bewusst NICHT `PLAN_JSON_SCHEMA` (nutzt `const`/`$schema`/`additionalProperties`, die
    Gemini nicht unterstützt). `devices` ist ein OBJECT (ein Property je Gerätename) statt eines
    Arrays: nur so lässt sich pro Gerät ein eigenes `required` erzwingen – ein gemeinsames
    Array-`items` könnte die je nach Geräteklasse unterschiedlichen Pflichtfelder (Batterie ohne
    Prio, gerätespezifische Zusatzfelder) nicht abbilden. So MUSS das Modell für jedes Gerät alle
    geforderten Vorschlagsfelder liefern; der Validator füllt etwaige Restlücken zusätzlich auf.
    """
    device_properties = {c.name: _device_response_schema(c) for c in constraints}
    device_order = [c.name for c in constraints]
    return {
        "type": "OBJECT",
        "properties": {
            "devices": {
                "type": "OBJECT",
                "properties": device_properties,
                # Alle Geräte Pflicht (behebt „mal nur manche Geräte"): das Modell muss jeden
                # bekannten Gerätenamen als Schlüssel liefern.
                "required": device_order,
                "propertyOrdering": device_order,
            },
            "confidence": {"type": "INTEGER"},
            "reasoning": {"type": "STRING"},
            "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["devices", "confidence", "reasoning"],
        "propertyOrdering": ["devices", "confidence", "reasoning", "warnings"],
    }


def build_repair_prompt(base_prompt: str, missing: dict[str, list[str]]) -> str:
    """Hängt an den Basis-Prompt eine gezielte Nachforderung fehlender Pflichtfelder an (D-050).

    Ein einmaliger, bewusst schlanker Zusatz: Er benennt exakt die je Gerät fehlenden Felder und
    fordert den KOMPLETTEN Plan erneut an. Rein promptseitig – Schema und Validator bleiben die
    harten Garanten; scheitert der Aufruf, greift die deterministische Füllung im Validator.
    """
    lines = [f"- {name}: {', '.join(fields)}" for name, fields in missing.items()]
    note = (
        "\n\nWICHTIG: Deine vorige Antwort war unvollständig. Liefere den KOMPLETTEN Plan erneut "
        "als JSON gemäß Schema und fülle für JEDES Gerät ALLE geforderten Vorschlagsfelder – "
        "insbesondere diese bisher fehlenden Pflichtfelder:\n" + "\n".join(lines)
    )
    return base_prompt + note
