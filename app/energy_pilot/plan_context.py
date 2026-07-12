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
from datetime import UTC, datetime, timedelta, timezone

from energy_pilot.constraints import DeviceConstraint
from energy_pilot.devices import BINARY
from energy_pilot.objectives import Objective
from energy_pilot.plan_schema import suggestion_keys
from energy_pilot.weather import ONECALL_TIMELINES

# Zusatz-Entität-Typ (D-048) -> Gemini-Antwort-Schema-Typ (OpenAPI-Subset, Großschreibung).
_KIND_TO_GEMINI: dict[str, str] = {
    "number": "NUMBER",
    "bool": "BOOLEAN",
    "datetime": "STRING",
    "text": "STRING",
}


# --- A3: Eingangs-Quantisierung / Snapping ---------------------------------------------------
# Default-Snap-Schritte je Größe; via Addon-Config (quantize-Dict) überschreibbar. Ziel: kleine
# Sensor-Schwankungen verändern den Prompt nicht mehr → gleicher Input → gleiche KI-Antwort
# (nutzt ai_temperature=0/ai_seed=42 endlich aus).
SNAP_POWER_W = 50
SNAP_SOC_PERCENT = 1
SNAP_AMP_A = 0.1
SNAP_FORECAST_KWH = 0.1
_DEFAULT_QUANTIZE: dict[str, float] = {
    "power_w": SNAP_POWER_W,
    "soc_percent": SNAP_SOC_PERCENT,
    "amp_a": SNAP_AMP_A,
    "forecast_kwh": SNAP_FORECAST_KWH,
}

# --- B2: Trend-Features ---------------------------------------------------------------------
# Trend aus kurz- vs. langfristigem Mittel. Relative Schwelle plus absoluter Boden (W) gegen
# Rauschen nahe Null; darunter gilt der Verlauf als „stabil".
TREND_REL = 0.05
TREND_ABS_W = 25.0


def _is_number(value: object) -> bool:
    """True für echte Zahlen (bool zählt NICHT als Zahl)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _snap(value: object, step: float) -> object:
    """Rundet eine Zahl auf das nächste Vielfache von `step`; nicht-Zahlen bleiben unverändert."""
    if not _is_number(value) or not step:
        return value
    return round(round(value / step) * step, 3)


def _snap_by_unit(value: object, unit: str | None, q: dict) -> object:
    """Rundet einheitengerecht: W/%/A auf grobe Stufen, sonst auf 2 Nachkommastellen."""
    if not _is_number(value):
        return value
    if unit == "W":
        return _snap(value, q.get("power_w", SNAP_POWER_W))
    if unit == "%":
        return _snap(value, q.get("soc_percent", SNAP_SOC_PERCENT))
    if unit == "A":
        return _snap(value, q.get("amp_a", SNAP_AMP_A))
    return round(float(value), 2)


def _trend(short: object, long: object) -> str | None:
    """Verlauf aus kurz- (mean_1m) vs. langfristigem (mean_60m) Mittel; None, wenn eines fehlt."""
    if not _is_number(short) or not _is_number(long):
        return None
    delta = float(short) - float(long)
    threshold = max(TREND_ABS_W, TREND_REL * abs(float(long)))
    if abs(delta) < threshold:
        return "stabil"
    return "steigend" if delta > 0 else "fallend"


def _round_minute(ts: object) -> object:
    """Rundet einen ISO-Zeitstempel auf Minutenauflösung (A3); nicht-ISO-Strings unverändert.

    Reruns innerhalb derselben Minute ergeben so denselben Prompt. Der in der DB gespeicherte
    Plan behält die exakten Zeiten (der Planner setzt sie getrennt von diesem Kontext).
    """
    if not isinstance(ts, str):
        return ts
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    return dt.replace(second=0, microsecond=0).isoformat()


def _condense_state(state: dict, quantize: dict | None = None) -> list[dict]:
    """Verdichtet den State-Snapshot je Rolle: quantisierte Werte + Mittel + Trend (A3/B2)."""
    q = quantize or _DEFAULT_QUANTIZE
    out: list[dict] = []
    for role, info in state.items():
        unit = info.get("unit")
        entry: dict[str, object] = {
            "role": role,
            "label": info.get("label"),
            "unit": unit,
        }
        if "value" in info:  # Zustandsgrößen: nur (gerundeter) Letztwert (SOC, Temperatur …)
            entry["value"] = _snap_by_unit(info.get("value"), unit, q)
        else:  # Messgrößen: Letztwert + 1/15/60-min-Mittel (nur vorhandene), plus Trend
            entry["latest"] = _snap_by_unit(info.get("latest"), unit, q)
            for key in ("mean_1m", "mean_15m", "mean_60m"):
                if info.get(key) is not None:
                    entry[key] = _snap_by_unit(info[key], unit, q)
            # Trend aus den ROHEN Mitteln ableiten (vor dem Snapping), sonst verschwindet er.
            trend = _trend(info.get("mean_1m"), info.get("mean_60m"))
            if trend is not None:
                entry["trend"] = trend
        out.append(entry)
    return out


def _condense_forecast(forecast: dict, quantize: dict | None = None) -> dict:
    """Reduziert die PV-Prognose auf die summierten (gerundeten) Werte (keine Ausrichtungen)."""
    if not forecast:
        return {}
    q = quantize or _DEFAULT_QUANTIZE
    step = q.get("forecast_kwh", SNAP_FORECAST_KWH)
    return {
        "unit": forecast.get("unit"),
        "values": [
            {"key": v.get("key"), "label": v.get("label"), "total": _snap(v.get("total"), step)}
            for v in forecast.get("values", [])
        ],
    }


# OWM liefert die forecast3h-Prognose in 3-Stunden-Schritten; daraus folgt die Schrittzahl
# je Horizont für den kompakten LLM-Auszug.
_FORECAST_STEP_H = 3

# --- One-Call-Auszug für die KI (upcoming_changes.md) ---------------------------------------
# Stündliche Prognose ans LLM: nur der heutige Tag ab „jetzt", frühestens ab 6 Uhr, bis 21 Uhr
# Ortszeit (nach 21 Uhr bleibt die Stundenreihe leer).
HOURLY_WINDOW_START_HOUR = 6
HOURLY_WINDOW_END_HOUR = 21
# Tagesprognose ans LLM: die nächsten 5 Tage ab morgen (heute deckt bereits die Stundenreihe ab).
DAILY_FORECAST_DAYS = 5
# Auflösungen, die sich als stündliches Tagesfenster eignen (1day ist die Tagesebene).
_INTRADAY_TIMELINES = ("15min", "1h")
# Sprechende Labels der Vorhersagemodelle für den KI-Kontext.
_ONECALL_MODEL_LABEL = {"15min": "15-Minuten", "1h": "stündlich", "1day": "täglich"}


def _offset_seconds(value: object) -> int:
    """OWM-`timezone_offset` (Sekunden ggü. UTC) defensiv als int; fehlend/ungültig → 0 (=UTC)."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _local_dt(dt_unix: int, offset_s: int) -> datetime:
    """Ortszeit eines Unix-UTC-Zeitstempels anhand des OWM-`timezone_offset` der Wetter-Zone."""
    return datetime.fromtimestamp(dt_unix, tz=timezone(timedelta(seconds=offset_s)))


def _slot_dt(slot: dict) -> int | None:
    """Liest den Unix-UTC-Zeitstempel (`dt`) eines Slots defensiv; ungültig → None."""
    dt = slot.get("dt")
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        return None
    return int(dt)


def _hourly_window_slots(slots: list, *, offset_s: int, now: datetime) -> list[dict]:
    """Stündliche Slots auf [max(jetzt, 6 Uhr) .. 21 Uhr] des heutigen Tages (Ortszeit) begrenzen.

    Fenstergrenzen als echte Ortszeit-Zeitpunkte: Start = max(jetzt, heute 6 Uhr), Ende = heute
    21 Uhr. Liegt „jetzt" nach 21 Uhr, bleibt die Reihe leer; Folgetage liegen hinter dem Ende
    und gehören in die Tagesprognose (upcoming_changes.md).
    """
    tz = timezone(timedelta(seconds=offset_s))
    now_local = now.astimezone(tz)
    day_start = now_local.replace(
        hour=HOURLY_WINDOW_START_HOUR, minute=0, second=0, microsecond=0
    )
    window_start = max(now_local, day_start)
    window_end = now_local.replace(hour=HOURLY_WINDOW_END_HOUR, minute=0, second=0, microsecond=0)
    out: list[dict] = []
    for s in slots:
        dt = _slot_dt(s)
        if dt is None:
            continue
        local = _local_dt(dt, offset_s)
        if window_start <= local <= window_end:
            out.append({
                "time": local.strftime("%Y-%m-%d %H:%M"),
                "temp": s.get("temp"),
                "clouds": s.get("clouds"),
                "pop": s.get("pop"),
            })
    return out


def _daily_next_days_slots(slots: list, *, offset_s: int, now: datetime) -> list[dict]:
    """Tages-Slots auf die nächsten `DAILY_FORECAST_DAYS` Tage ab morgen (Ortszeit) begrenzen.

    Der heutige Tag wird übersprungen (er steckt bereits in der Stundenreihe); es werden
    höchstens 5 Folgetage übernommen (energierelevante Felder inkl. Tages-Min/Max).
    """
    tz = timezone(timedelta(seconds=offset_s))
    today = now.astimezone(tz).date()
    out: list[dict] = []
    for s in slots:
        dt = _slot_dt(s)
        if dt is None:
            continue
        local = _local_dt(dt, offset_s)
        if local.date() <= today:
            continue
        out.append({
            "time": local.strftime("%Y-%m-%d"),
            "temp": s.get("temp"),
            "temp_min": s.get("temp_min"),
            "temp_max": s.get("temp_max"),
            "clouds": s.get("clouds"),
            "pop": s.get("pop"),
        })
        if len(out) >= DAILY_FORECAST_DAYS:
            break
    return out


def _condense_onecall(weather: dict, *, now: datetime) -> dict:
    """Verdichtet ALLE aktiven One-Call-Vorhersagemodelle für die KI (Kombination frei wählbar).

    Jedes in der Addon-Config aktivierte Modell (15min/1h/1day) fließt eigenständig in den Kontext
    unter `weather.models[<res>]` (D-054) — der User wählt per Schalter eine beliebige Kombination.
    Die intraday-Modelle (15min/1h) werden auf das heutige Fenster von „jetzt" (frühestens 6 Uhr)
    bis 21 Uhr Ortszeit begrenzt, das Tagesmodell (1day) auf die nächsten 5 Tage ab morgen.
    Behalten werden nur energierelevante Felder (Temperatur, Bewölkung, Regenwahrscheinlichkeit;
    daily zusätzlich Min/Max). Leer, wenn kein aktives Modell Daten hat.
    """
    timelines = weather.get("timelines") or {}
    models: dict[str, object] = {}
    for res in ONECALL_TIMELINES:  # feste Reihenfolge fein → grob
        tl = timelines.get(res) or {}
        raw = tl.get("slots") or []
        if not tl.get("enabled") or not raw:  # nur aktive UND abgerufene Modelle
            continue
        offset_s = _offset_seconds(tl.get("timezone_offset_s"))
        if res in _INTRADAY_TIMELINES:
            slots = _hourly_window_slots(raw, offset_s=offset_s, now=now)
            zeitraum = "heute ab jetzt (frühestens 6 Uhr) bis 21 Uhr Ortszeit; nach 21 Uhr leer"
        else:
            slots = _daily_next_days_slots(raw, offset_s=offset_s, now=now)
            zeitraum = f"nächste {DAILY_FORECAST_DAYS} Tage ab morgen"
        models[res] = {
            "aufloesung": _ONECALL_MODEL_LABEL.get(res, res),
            "zeitraum": zeitraum,
            "slots": slots,
        }
    if not models:
        return {}
    return {"source": "onecall", "units": weather.get("units"), "models": models}


def _condense_weather(
    weather: dict, *, horizon_h: int, detail: str, now: datetime | None = None
) -> dict:
    """Verdichtet die OWM-Wetterprognose für den KI-Kontext (quellen-/detailabhängig).

    Bei `source="onecall"` geht **jedes aktivierte Vorhersagemodell** ein (`weather.models`, siehe
    `_condense_onecall`): intraday für heute (bis 21 Uhr Ortszeit), täglich für die Folgetage.
    Sonst (forecast3h):
    `compact` (Default) = Temperatur/Bewölkung/Regenwahrscheinlichkeit je 3-Stunden-Schritt bis
    zum Planungshorizont (Datenminimum, Iron Rule 7); `full` = komplette 5-Tage-Prognose mit allen
    Feldern. Leer ohne Prognose.
    """
    if not weather:
        return {}
    if weather.get("source") == "onecall":
        if now is None:
            now = datetime.now(UTC)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return _condense_onecall(weather, now=now)
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


# Aus dem Vorplan als Anker relevant (A1): Gerätename + gesetzte Vorschlagsfelder. Diese Keys
# überträgt `plan_to_dict` bereits flach je Gerät (feste Felder + `extra_<obj>_vorschlag`).
_PREV_SKIP_KEYS = frozenset({"name"})


def _condense_previous_plan(previous: dict | None) -> dict:
    """Verdichtet den zuletzt gespeicherten Plan als Anker für den nächsten Lauf (A1).

    Übergibt der KI nur die Gerät-Vorschlagswerte (Name + gesetzte Vorschlagsfelder) und die
    frühere Konfidenz — Zeitstempel, Reasoning und Warnungen bleiben draußen (Datenminimum,
    Iron Rule 7). So kann die KI ohne materiellen Grund nah am Vorplan bleiben und dämpft
    Lauf-zu-Lauf-Sprünge. Leer, wenn es keinen (Geräte-)Vorplan gibt.
    """
    if not previous:
        return {}
    plan = previous.get("plan") or {}
    devices = [
        {k: v for k, v in d.items() if k in _PREV_SKIP_KEYS or k.endswith("_vorschlag")}
        for d in plan.get("devices") or []
        if isinstance(d, dict) and d.get("name")
    ]
    if not devices:
        return {}
    out: dict[str, object] = {"devices": devices}
    if plan.get("confidence") is not None:
        out["confidence"] = plan.get("confidence")
    return out


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
    now: datetime | None = None,
    previous_plan: dict | None = None,
    quantize: dict | None = None,
) -> dict:
    """Stellt den verdichteten KI-Kontext zusammen (Datenminimum, Iron Rule 7).

    `now` (UTC) steuert das stündliche Wetter-Tagesfenster der One-Call-Quelle; ohne Angabe
    gilt die aktuelle Zeit. `previous_plan` (Ausgabe von `Planner.latest_plan()`) wird als
    verdichteter Anker `previous_plan` eingehängt (A1 – Stabilität über Aufrufe); fehlt er,
    entfällt der Schlüssel. `quantize` (Snap-Schritte je Größe) steuert die Eingangs-Rundung
    (A3); ohne Angabe gelten die Modul-Defaults `_DEFAULT_QUANTIZE`.
    """
    context: dict[str, object] = {
        "valid_from": _round_minute(valid_from),
        "valid_until": _round_minute(valid_until),
        "state": _condense_state(state, quantize),
        "forecast": _condense_forecast(forecast, quantize),
        "weather": _condense_weather(
            weather or {}, horizon_h=horizon_h, detail=weather_detail, now=now
        ),
        "devices": [_condense_constraint(c) for c in constraints],
        "objectives": [
            {"key": o.key, "label": o.label, "weight": o.weight} for o in objectives
        ],
    }
    prev = _condense_previous_plan(previous_plan)
    if prev:
        context["previous_plan"] = prev
    return context


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
    "- `technische_freigabe` ist nur der AKTUELLE Zustand des Geräts, kein Verbot für den "
    "Planzeitraum: du darfst eine gerade gesperrte Last freigeben, wenn sie im "
    "Gültigkeitszeitraum des Plans voraussichtlich arbeiten darf.\n"
    "- Vergib den Geräten (NICHT der Batterie) eine eindeutige Rangfolge als "
    "`prio_vorschlag`: beginne bei 10 (höchste Priorität) und steigere in "
    "10er-Schritten – 10, 20, 30 … Keine Werte doppelt, keine Lücken, höchstens 100.\n"
    "- Die Batterie ist konzeptionell stets vorrangig und immer freigegeben; sie "
    "bekommt KEINE Priorität – schlage für sie nur die geschützte "
    "Mindest-Ladeleistung vor.\n"
    "- Erfinde keine Geräte; verwende exakt die `name`-Werte aus `devices`.\n"
    "- Gewichte die weichen Ziele gemäß `objectives` (0–100 %).\n"
    "- Beziehe die Wetterprognose (`weather`) in die Planung ein: bei One Call enthält "
    "`weather.models` je aktiviertem Vorhersagemodell eine Reihe (stündlich/15-Minuten für heute "
    "bis 21 Uhr Ortszeit, täglich für die Folgetage); jeder Eintrag nennt seinen `zeitraum`. "
    "Hohe Bewölkung (`clouds`) und Regenwahrscheinlichkeit (`pop`) senken die erwartete "
    "PV-Erzeugung, niedrige Temperaturen erhöhen tendenziell den Heizbedarf.\n"
    "- Beachte `zusatzwerte` je Gerät: der aktuelle Wert und der `hinweis` erklären dir "
    "dessen Bedeutung. Hat ein Zusatzwert `suggest=true`, liefere deinen Vorschlag exakt "
    "unter dem Feldnamen aus `vorschlagsfeld` (nur diese Felder sind in `allowed_fields`).\n"
    "- Hat ein Gerät das Feld `funktion`, ist das eine vom User verfasste Beschreibung seiner "
    "Funktion/Besonderheiten; berücksichtige sie bei der Planung dieses Geräts.\n"
    "- Bei Messgrößen im `state` zeigt `trend` (steigend/fallend/stabil) den Verlauf aus kurz- "
    "gegen langfristiges Mittel; plane aus dem Verlauf, nicht aus einem einzelnen Momentwert.\n"
    "- Ist `previous_plan` vorhanden, ist das dein zuletzt veröffentlichter Plan (je Gerät die "
    "vorigen Vorschlagswerte). Bleibe ohne materiellen Grund nah daran: ändere Priorität oder "
    "Freigabe nur, wenn die aktuellen Daten es klar erfordern – nicht wegen kleiner "
    "Schwankungen. Das hält den Plan über die Läufe hinweg stabil.\n\n"
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
