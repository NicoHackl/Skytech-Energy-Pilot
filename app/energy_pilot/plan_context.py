"""Kontext-, Prompt- und Antwort-Schema-Aufbau für die KI-Planung (docs/planungs-engine.md).

Hier wird der **Datenminimum**-Kontext für die KI zusammengestellt (eiserne Regel 12):
nur verdichtete, freigegebene Werte (Zustand, PV-Prognose, harte Grenzen, Ziele) –
kein Roh-Dump der HA-Datenbank. Der Prompt erklärt der KI ihre Rolle als
Orchestrator und die je Gerät **erlaubten** Vorschlagsfelder; das Antwort-Schema
zwingt strukturiertes JSON. Die fachliche Grenzprüfung macht danach `validator.py`.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta, timezone

from energy_pilot.constraints import DeviceConstraint
from energy_pilot.devices import BINARY
from energy_pilot.objectives import Objective, Ziel
from energy_pilot.plan_schema import (
    CONFIDENCE_PARTS,
    EXPLANATION_FIELDS,
    suggestion_keys,
)
from energy_pilot.weather import ONECALL_TIMELINES

# Grenzen der Prio-Rangfolge im Antwort-Schema (der Validator normalisiert unabhängig davon).
_PRIO_MIN = 10
_PRIO_MAX = 100

# Zusatz-Entität-Typ (D-048) -> Gemini-Antwort-Schema-Typ (OpenAPI-Subset, Großschreibung).
_KIND_TO_GEMINI: dict[str, str] = {
    "number": "NUMBER",
    "bool": "BOOLEAN",
    "datetime": "STRING",
    "text": "STRING",
}

# --- Quantisierung (D-063) -------------------------------------------------------------------
# Rohe Messwerte zappeln in jedem Poll-Zyklus in der letzten Stelle. Damit ist der Prompt bei
# gleicher Sachlage nie derselbe String, und ein fixer `seed` kann per Definition nichts
# reproduzieren. Deshalb wird jeder Zahlenwert im Kontext auf eine fachlich sinnvolle Stufe
# gerundet — Eingangshygiene, keine inhaltliche Änderung: 5 W Unterschied verändert keinen Plan.
_STEP_BY_UNIT: dict[str, float] = {
    "W": 10.0,
    "kWh": 0.1,
    "%": 1.0,
    "°C": 0.5,
    "A": 0.5,
}
# Stufen der Wetterfelder (Einheit steckt nicht im Slot, daher je Feldname).
_STEP_WEATHER: dict[str, float] = {
    "temp": 0.5,
    "temp_min": 0.5,
    "temp_max": 0.5,
    "clouds": 5.0,
    "pop": 0.05,
    "feels_like": 0.5,
    "wind_speed": 0.5,
    "humidity": 5.0,
    "rain_3h": 0.1,
    "snow_3h": 0.1,
}
# Fallback-Stufe für Zahlen ohne bekannte Einheit (eine Dezimalstelle).
_STEP_DEFAULT = 0.1


def quantize(value: object, step: float) -> object:
    """Rundet eine Zahl auf ein Vielfaches von `step`; alles andere bleibt unberührt.

    Bools sind in Python Zahlen und dürfen hier **nicht** zu 0.0/1.0 werden.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return value
    if step <= 0:
        return value
    stepped = round(float(value) / step) * step
    # Auf die Stellenzahl der Stufe runden, sonst entstehen 74.30000000000001-Artefakte.
    digits = max(0, -math.floor(math.log10(step))) if step < 1 else 0
    return round(stepped, digits)


def _q_unit(value: object, unit: object) -> object:
    """Quantisiert anhand der Einheit einer Mess-Rolle bzw. eines Zusatzwerts."""
    return quantize(value, _STEP_BY_UNIT.get(str(unit or "").strip(), _STEP_DEFAULT))


def _q_weather(field: str, value: object) -> object:
    """Quantisiert ein Wetter-Slot-Feld anhand seines Namens."""
    return quantize(value, _STEP_WEATHER.get(field, _STEP_DEFAULT))


def _condense_state(state: dict) -> list[dict]:
    """Verdichtet den State-Snapshot je Rolle (Werte + Mittel, quantisiert, mit Frische).

    Neu gegenüber D-001: jede Rolle trägt `veraltet` (D-064). Der Collector kennt je Rolle die
    Quelle (`live` = gültig gelesen, `none` = fehlend/unlesbar); dieses Signal wurde früher
    verworfen, sodass ein ausgefallener Sensor im Kontext von einem echten Wert nicht zu
    unterscheiden war. Zahlen sind quantisiert (D-063).
    """
    out: list[dict] = []
    for role, info in state.items():
        unit = info.get("unit")
        entry: dict[str, object] = {
            "role": role,
            "label": info.get("label"),
            "unit": unit,
        }
        if "value" in info:  # Zustandsgrößen: nur Letztwert (SOC …)
            entry["value"] = _q_unit(info.get("value"), unit)
            has_value = info.get("value") is not None
        else:  # Messgrößen: Letztwert + 1/15/60-min-Mittel (nur vorhandene)
            entry["latest"] = _q_unit(info.get("latest"), unit)
            for key in ("mean_1m", "mean_15m", "mean_60m"):
                if info.get(key) is not None:
                    entry[key] = _q_unit(info[key], unit)
            has_value = info.get("latest") is not None
        if info.get("source", "live") != "live" or not has_value:
            entry["veraltet"] = True
        out.append(entry)
    return out


def _data_quality(state_entries: list[dict], devices: list[dict]) -> dict:
    """Zählt, wie viel des Kontexts tatsächlich mit frischen Werten belegt ist (D-064).

    Grundlage der EP-eigenen `datenlage`-Note: Anteil der erwarteten Werte, die frisch und nicht
    `null` sind. Bewertet werden die Mess-Rollen und die Zusatzwerte je Gerät — genau die Größen,
    auf die sich die Regeln des Users stützen. Die Zahl steht auch im Kontext, damit die KI ihre
    eigene Note nicht besser einschätzt als die Datenlage sie zulässt.
    """
    total = 0
    fresh = 0
    missing: list[str] = []
    for entry in state_entries:
        total += 1
        if entry.get("veraltet"):
            missing.append(str(entry.get("role")))
        else:
            fresh += 1
    for device in devices:
        for extra in device.get("zusatzwerte") or []:
            total += 1
            if extra.get("wert") is None:
                missing.append(f"{device.get('name')}.{extra.get('entity')}")
            else:
                fresh += 1
    prozent = 100 if total == 0 else round(fresh * 100 / total)
    return {"frische_prozent": prozent, "fehlende_werte": missing}


# Reichweite der PV-Prognose, ausdrücklich benannt (D-066). Die konfigurierten Sensoren liefern
# genau vier Skalare — laufende Stunde, nächste Stunde, Rest heute, morgen (D-026). Es gibt
# **keine** Stundenkurve und **keinen** Tag 3. Ohne diesen Satz im Kontext erfindet ein Modell
# Erträge für übermorgen; mit ihm muss es den Rückblick heranziehen.
FORECAST_HORIZON_NOTE = (
    "Die PV-Prognose reicht nur bis morgen (vier Summenwerte, keine Stundenkurve). Für spätere "
    "Tage gibt es KEINE Ertragsprognose — schätze sie aus `rueckblick`, indem du den dort "
    "gemessenen Tagesertrag mit der Bewölkung desselben Tages vergleichst und das auf die "
    "Bewölkung der Folgetage überträgst. Erfinde keine Zahlen für übermorgen."
)


def _condense_forecast(forecast: dict) -> dict:
    """Reduziert die PV-Prognose auf die summierten Werte (keine Einzel-Ausrichtungen)."""
    if not forecast:
        return {}
    unit = forecast.get("unit")
    return {
        "unit": unit,
        "horizont": "heute und morgen",
        "hinweis": FORECAST_HORIZON_NOTE,
        "values": [
            {
                "key": v.get("key"),
                "label": v.get("label"),
                "total": _q_unit(v.get("total"), unit),
            }
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
    if isinstance(value, int | float):
        return int(value)
    return 0


def _local_dt(dt_unix: int, offset_s: int) -> datetime:
    """Ortszeit eines Unix-UTC-Zeitstempels anhand des OWM-`timezone_offset` der Wetter-Zone."""
    return datetime.fromtimestamp(dt_unix, tz=timezone(timedelta(seconds=offset_s)))


def _slot_dt(slot: dict) -> int | None:
    """Liest den Unix-UTC-Zeitstempel (`dt`) eines Slots defensiv; ungültig → None."""
    dt = slot.get("dt")
    if isinstance(dt, bool) or not isinstance(dt, int | float):
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
                "temp": _q_weather("temp", s.get("temp")),
                "clouds": _q_weather("clouds", s.get("clouds")),
                "pop": _q_weather("pop", s.get("pop")),
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
            "temp": _q_weather("temp", s.get("temp")),
            "temp_min": _q_weather("temp_min", s.get("temp_min")),
            "temp_max": _q_weather("temp_max", s.get("temp_max")),
            "clouds": _q_weather("clouds", s.get("clouds")),
            "pop": _q_weather("pop", s.get("pop")),
        })
        if len(out) >= DAILY_FORECAST_DAYS:
            break
    return out


def _timeline_offset(weather: dict) -> int:
    """Zeitzonen-Offset der Wetter-Zone aus der ersten Timeline, die einen mitbringt."""
    timelines = weather.get("timelines") or {}
    for res in ONECALL_TIMELINES:
        tl = timelines.get(res) or {}
        if tl.get("slots"):
            return _offset_seconds(tl.get("timezone_offset_s"))
    return 0


def _intraday_slots(weather: dict, offset_s: int) -> list[tuple[datetime, dict]]:
    """Alle feinauflösenden Slots (15min bevorzugt, sonst 1h) als (Ortszeit, Slot)."""
    timelines = weather.get("timelines") or {}
    for res in _INTRADAY_TIMELINES:  # fein -> grob
        tl = timelines.get(res) or {}
        raw = tl.get("slots") or []
        if not raw:
            continue
        out: list[tuple[datetime, dict]] = []
        for s in raw:
            dt = _slot_dt(s)
            if dt is not None:
                out.append((_local_dt(dt, offset_s), s))
        if out:
            return out
    return []


def _daily_slots(weather: dict, offset_s: int) -> list[tuple[datetime, dict]]:
    """Alle Tages-Slots als (Ortszeit, Slot) — **einschließlich heute** (anders als der Auszug)."""
    tl = (weather.get("timelines") or {}).get("1day") or {}
    out: list[tuple[datetime, dict]] = []
    for s in tl.get("slots") or []:
        dt = _slot_dt(s)
        if dt is not None:
            out.append((_local_dt(dt, offset_s), s))
    return out


def _num(value: object) -> float | None:
    """Nimmt nur echte Zahlen (kein Bool) als float; alles andere -> None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _max_over(
    intraday: list[tuple[datetime, dict]],
    daily: list[tuple[datetime, dict]],
    *,
    start: datetime,
    end: datetime,
    intraday_field: str,
    daily_field: str,
) -> float | None:
    """Maximum eines Felds über ein Zeitfenster, aus Intraday- **und** Tagesreihe.

    Beide Quellen zusammen, weil keine allein das Fenster deckt: die Intraday-Reihe endet nach
    rund 24–48 h und beginnt erst zur laufenden Stunde, die Tagesreihe hat keine Auflösung
    innerhalb des Tages. Fehlt eine Quelle, trägt die andere.
    """
    values: list[float] = []
    for local, slot in intraday:
        if start <= local <= end:
            v = _num(slot.get(intraday_field))
            if v is not None:
                values.append(v)
    for local, slot in daily:
        # Ein Tages-Slot zählt, wenn sein Kalendertag das Fenster überhaupt berührt.
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        if day_end > start and day_start <= end:
            v = _num(slot.get(daily_field))
            if v is not None:
                values.append(v)
    return max(values) if values else None


def weather_metrics(weather: dict, *, now: datetime | None = None) -> dict:
    """Verdichtete Wetter-Kennzahlen für die KI (D-062) — immer vorhanden, auch abends.

    Der Slot-Auszug für die KI ist bewusst schmal: die Intraday-Reihe endet um 21 Uhr Ortszeit
    (danach ist sie leer) und die Tagesreihe überspringt heute. Damit fehlte der KI abends jede
    Temperaturangabe für heute — und ein Tagesmaximum musste sie sich ohnehin selbst aus Rohslots
    ableiten. Diese Kennzahlen liefern die Größen, in denen der User denkt („die nächsten Tage
    wird es heiß"), deterministisch aus denselben Rohdaten. Leer, wenn keine Prognose vorliegt.
    """
    if not weather or weather.get("source") != "onecall":
        return {}
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    offset_s = _timeline_offset(weather)
    tz = timezone(timedelta(seconds=offset_s))
    now_local = now.astimezone(tz)
    intraday = _intraday_slots(weather, offset_s)
    daily = _daily_slots(weather, offset_s)
    if not intraday and not daily:
        return {}

    today = now_local.date()
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
    today_daily = [(local, s) for local, s in daily if local.date() == today]
    today_intraday = [(local, s) for local, s in intraday if local.date() == today]

    out: dict[str, object] = {}

    # Temperatur „jetzt": der zeitlich nächste Intraday-Slot (die *gemessene* Außentemperatur
    # kommt separat als Mess-Rolle, D-061 — hier steht der Prognosewert).
    if intraday:
        nearest = min(intraday, key=lambda item: abs((item[0] - now_local).total_seconds()))
        out["temp_jetzt"] = _q_weather("temp", nearest[1].get("temp"))

    # Heutiges Min/Max: bevorzugt aus dem Tages-Slot von heute (deckt den ganzen Tag ab),
    # sonst aus den verbleibenden Intraday-Slots des Tages.
    if today_daily:
        slot = today_daily[0][1]
        out["temp_max_heute"] = _q_weather("temp_max", slot.get("temp_max"))
        out["temp_min_heute"] = _q_weather("temp_min", slot.get("temp_min"))
    elif today_intraday:
        temps = [t for t in (_num(s.get("temp")) for _, s in today_intraday) if t is not None]
        if temps:
            out["temp_max_heute"] = _q_weather("temp_max", max(temps))
            out["temp_min_heute"] = _q_weather("temp_min", min(temps))

    for hours, key in ((24, "temp_max_24h"), (48, "temp_max_48h")):
        value = _max_over(
            intraday, daily,
            start=now_local, end=now_local + timedelta(hours=hours),
            intraday_field="temp", daily_field="temp_max",
        )
        if value is not None:
            out[key] = _q_weather("temp_max", value)

    pop = _max_over(
        intraday, daily,
        start=now_local, end=now_local + timedelta(hours=24),
        intraday_field="pop", daily_field="pop",
    )
    if pop is not None:
        out["pop_max_24h"] = _q_weather("pop", pop)

    clouds = [
        c for c in (_num(s.get("clouds")) for _, s in today_intraday or today_daily)
        if c is not None
    ]
    if clouds:
        out["wolken_mittel_heute"] = _q_weather("clouds", sum(clouds) / len(clouds))

    if out:
        out["hinweis"] = (
            "Verdichtete Kennzahlen aus derselben Prognose wie `models`, aber über den ganzen "
            "Tag und unabhängig vom Slot-Fenster. Für Aussagen über Tageshöchst- oder "
            "Tagestiefstwerte sind diese Werte maßgeblich, nicht die Slot-Reihen."
        )
        out["fenster_heute"] = f"{day_start:%d.%m.%Y %H:%M} bis {day_end:%d.%m.%Y %H:%M}"
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
    # Kennzahlen (D-062) stehen unabhängig von den Slot-Auszügen zur Verfügung — genau deshalb
    # existieren sie: abends ist die Stundenreihe leer, die Kennzahlen sind es nicht.
    kennzahlen = weather_metrics(weather, now=now)
    if not models and not kennzahlen:
        return {}
    out: dict[str, object] = {"source": "onecall", "units": weather.get("units")}
    if models:
        out["models"] = models
    if kennzahlen:
        out["kennzahlen"] = kennzahlen
    return out


def _condense_weather(
    weather: dict, *, horizon_h: int, detail: str, now: datetime | None = None
) -> dict:
    """Verdichtet die OWM-Wetterprognose für den KI-Kontext (quellen-/detailabhängig).

    Bei `source="onecall"` geht **jedes aktivierte Vorhersagemodell** ein (`weather.models`, siehe
    `_condense_onecall`): intraday für heute (bis 21 Uhr Ortszeit), täglich für die Folgetage.
    Sonst (forecast3h):
    `compact` (Default) = Temperatur/Bewölkung/Regenwahrscheinlichkeit je 3-Stunden-Schritt bis
    zum Planungshorizont (Datenminimum, eiserne Regel 12); `full` = komplette
    5-Tage-Prognose mit allen Feldern. Leer ohne Prognose.
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

    _fields_full = (
        "temp", "feels_like", "clouds", "pop", "wind_speed", "humidity", "rain_3h", "snow_3h",
    )
    if detail == "full":
        out_slots = [
            {
                "time": s.get("time"),
                **{f: _q_weather(f, s.get(f)) for f in _fields_full},
                "condition": s.get("condition"),
            }
            for s in slots
        ]
    else:  # compact
        max_steps = max(1, math.ceil(horizon_h / _FORECAST_STEP_H))
        out_slots = [
            {
                "time": s.get("time"),
                "temp": _q_weather("temp", s.get("temp")),
                "clouds": _q_weather("clouds", s.get("clouds")),
                "pop": _q_weather("pop", s.get("pop")),
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
        # D-061: `rolle` sagt, WAS der Wert ist. Ohne sie liest ein Modell einen Sollwert wie
        # „Max. Wassertemperatur 85 °C" als Ist-Temperatur und plant daran vorbei.
        "rolle": ex.rolle,
        "rolle_bedeutung": ex.rolle_text,
        "wert": _q_unit(ce.value, ex.unit) if ce.kind == "number" else ce.value,
        "einheit": ex.unit or None,
        "hinweis": ex.ai_hint or None,
        "suggest": ex.ai_suggestion,
        "vorschlagsfeld": ex.plan_field if ex.ai_suggestion else None,
    }
    if ce.value is None:
        item["veraltet"] = True  # D-064: nicht gelesen -> für Entscheidungen unbrauchbar
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
    # Funktion/Besonderheiten. Nur wenn gesetzt, um den Kontext schlank zu halten
    # (eiserne Regel 12).
    if constraint.ai_prompt:
        entry["funktion"] = constraint.ai_prompt
    # User-gepflegte Betriebsregeln (D-060): die Vorgabe, gegen die die KI ihre Entscheidung für
    # dieses Gerät begründen muss (`angewandte_regeln`). Getrennt von `funktion`, weil das eine
    # Hintergrundwissen ist und das andere der Wille des Users.
    if constraint.ai_regeln:
        entry["regeln"] = constraint.ai_regeln
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


def _condense_rueckblick(rueckblick: list[dict] | None) -> dict:
    """Verdichtet den Tages-Rückblick für die KI (D-065).

    Das ist der Block, ohne den die eigentliche Frage nicht beantwortbar ist: „reicht der
    Speicherinhalt, bis die nächste nicht-elektrische Wärme kommt?" Der Hinweis nennt den
    Zusammenhang ausdrücklich, weil er die ganze Bilanz trägt — steigt die Temperatur, während
    die elektrische Energie bei 0 liegt, kam die Wärme von einer anderen Quelle.
    """
    if not rueckblick:
        return {}
    return {
        "hinweis": (
            "Gemessene Tageswerte der letzten Tage (`delta` = Änderung über den Tag). Steigt eine "
            "Speichertemperatur, während die elektrische Tagesenergie desselben Geräts bei ~0 "
            "liegt, kam die Wärme von einer anderen Quelle (z.B. Solarthermie). Stelle diese Tage "
            "der Bewölkung desselben Tages gegenüber, um die Folgetage einzuschätzen."
        ),
        "tage": rueckblick,
    }


def _condense_features(features: list | None, system: dict | None) -> dict:
    """Verdichtet die gerechneten Merkmale (D-066) für die KI.

    Bewusst **Zahlen, keine Empfehlung**: Reserve, Bedarf, beobachtete Fremdwärme und die daraus
    folgende Deckung in Tagen. Die Abwägung bleibt Sache der KI (D-060). Fehlende Eingaben stehen
    als `fehlt` daneben, damit das Modell eine Lücke nicht als Null missversteht.
    """
    out: dict[str, object] = {}
    geraete: list[dict] = []
    for merkmal in features or []:
        eintrag: dict[str, object] = {"name": merkmal.name}
        for key in (
            "ist_c", "komfort_min_c", "ziel_c", "volumen_liter",
            "reserve_kwh", "energiebedarf_kwh", "fremdwaerme_mittel_kwh", "deckung_tage",
        ):
            wert = getattr(merkmal, key)
            if wert is not None:
                eintrag[key] = wert
        if merkmal.fremdwaerme_tage:
            eintrag["fremdwaerme_tage"] = [
                {
                    "tag": tag.tag,
                    "delta_c": tag.delta_c,
                    "energie_kwh": tag.energie_kwh,
                    "wolken_mittel": tag.wolken_mittel,
                    "elektrisch_kwh": tag.elektrisch_kwh,
                }
                for tag in merkmal.fremdwaerme_tage
            ]
        if merkmal.fehlt:
            eintrag["fehlt"] = list(merkmal.fehlt)
        if merkmal.hinweise:
            eintrag["hinweise"] = list(merkmal.hinweise)
        geraete.append(eintrag)
    if geraete:
        out["geraete"] = geraete
    if system:
        out["system"] = system
    if out:
        out["hinweis"] = (
            "Gerechnete Größen, keine Empfehlung. `reserve_kwh` ist die Energie über dem "
            "Komfortminimum, `energiebedarf_kwh` die Lücke bis zum Zielwert, `deckung_tage` die "
            "Zeit, die die Reserve beim beobachteten Verlust ohne Strom trägt. Fehlt ein Wert, "
            "steht der Grund in `fehlt` — behandle ihn dann als unbekannt, nicht als 0."
        )
    return out


def _condense_previous_plan(previous: dict | None) -> dict:
    """Verdichtet den zuletzt gespeicherten Plan als Anker für den nächsten Lauf (A1).

    Übergibt der KI nur die Gerät-Vorschlagswerte (Name + gesetzte Vorschlagsfelder) und die
    frühere Konfidenz — Zeitstempel, Reasoning und Warnungen bleiben draußen (Datenminimum,
    eiserne Regel 12). So kann die KI ohne materiellen Grund nah am Vorplan bleiben und dämpft
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
    global_regeln: str = "",
    rueckblick: list[dict] | None = None,
    features: list | None = None,
    system_features: dict | None = None,
) -> dict:
    """Stellt den verdichteten KI-Kontext zusammen (Datenminimum, eiserne Regel 12).

    `now` (UTC) steuert das stündliche Wetter-Tagesfenster der One-Call-Quelle **und** steht der
    KI als eigenes Feld zur Verfügung (vorher kannte sie die Uhrzeit nur indirekt über
    `valid_from`). `previous_plan` (Ausgabe von `Planner.latest_plan()`) wird als verdichteter
    Anker eingehängt (A1 – Stabilität über Aufrufe); fehlt er, entfällt der Schlüssel.
    `global_regeln` sind die hausweiten Freitext-Regeln (D-060).

    Alle Zahlen sind quantisiert (D-063) und jeder Wert trägt bei fehlender Frische `veraltet`
    (D-064); `datenlage` fasst zusammen, wie viel des Kontexts überhaupt belegt ist.
    """
    state_entries = _condense_state(state)
    device_entries = [_condense_constraint(c) for c in constraints]
    context: dict[str, object] = {
        "now": (now or datetime.now(UTC)).isoformat(),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "state": state_entries,
        "forecast": _condense_forecast(forecast),
        "weather": _condense_weather(
            weather or {}, horizon_h=horizon_h, detail=weather_detail, now=now
        ),
        "devices": device_entries,
        "objectives": [
            {"key": o.key, "label": o.label, "weight": o.weight} for o in objectives
        ],
        "datenlage": _data_quality(state_entries, device_entries),
    }
    if global_regeln.strip():
        context["globale_regeln"] = global_regeln.strip()
    # Rückblick und Merkmale (D-065/D-066): erst damit ist „reicht es die nächsten Tage?" eine
    # Rechnung. Nur einhängen, wenn vorhanden — ein leerer Block kostet Kontext ohne Nutzen.
    rueckblick_block = _condense_rueckblick(rueckblick)
    if rueckblick_block:
        context["rueckblick"] = rueckblick_block
    merkmale = _condense_features(features, system_features)
    if merkmale:
        context["merkmale"] = merkmale
    prev = _condense_previous_plan(previous_plan)
    if prev:
        context["previous_plan"] = prev
    return context


# Kontext-Schlüssel, die NICHT in den Hash eingehen (D-063). Alle drei haben denselben Grund:
# sie sind keine Information über die **Anlage**, sondern Nebenprodukt des Laufs — bliebe eines
# drin, wäre der Hash bei unveränderter Sachlage trotzdem jedes Mal ein anderer und die
# Wiederverwendung könnte nie greifen.
# - `now`: ändert sich zwangsläufig. `valid_from`/`valid_until` sind dagegen auf das
#   Planungsraster gerundet und damit vergleichbar (siehe `planner._floor_to_grid`).
# - `previous_plan`: EPs eigene vorige Ausgabe.
# - `objectives`: die Zielgewichte stammen aus dem Klassifizierungs-Aufruf, sind also selbst
#   Modellausgabe. Streut das Modell dort, würde genau diese Streuung den Mechanismus
#   aushebeln, der Streuung unterdrücken soll. Hat sich die Sachlage wirklich geändert, ändert
#   sie den Hash bereits über `state`/`forecast`/`weather`/`devices`.
_HASH_EXCLUDED_KEYS = frozenset({"now", "previous_plan", "objectives"})


def context_hash(context: dict, *, prompt: str = "", model: str = "") -> str:
    """Fingerabdruck der **Sachlage** inkl. Instruktion und Modell (D-063).

    Grundlage jeder Aussage über Stabilität: nur wenn dieser Hash zwischen zwei Läufen gleich
    ist, war die Sachlage tatsächlich identisch — weicht der Plan dann trotzdem ab, ist es
    Modellstreuung und nicht neue Information. Was bewusst draußen bleibt und warum, steht in
    `_HASH_EXCLUDED_KEYS`.
    """
    payload = {k: v for k, v in context.items() if k not in _HASH_EXCLUDED_KEYS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256()
    digest.update(raw.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(prompt.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(model.encode("utf-8"))
    return digest.hexdigest()


def build_classification_context(
    state: dict,
    forecast: dict,
    constraints: list[DeviceConstraint],
    ziele: list[Ziel],
    *,
    valid_from: str,
    valid_until: str,
    weather: dict | None = None,
    horizon_h: int = 24,
    weather_detail: str = "compact",
    now: datetime | None = None,
    previous_plan: dict | None = None,
    global_regeln: str = "",
    rueckblick: list[dict] | None = None,
    features: list | None = None,
    system_features: dict | None = None,
) -> dict:
    """Kontext für den vorgelagerten Klassifizierungs-Aufruf (D-055).

    Exakt dieselbe Datenbasis wie `build_context` (Datenminimum, eiserne Regel 12) – nur der Key
    `objectives` (Gewicht bereits bekannt) wird durch `ziele` ersetzt: die user-definierten
    Zieldefinitionen (id/name/beschreibung/geraete) OHNE Gewicht. Die Klassifizierungs-KI
    leitet daraus die Gewichtung ab (`objectives_from_classification`), die dann in den
    eigentlichen Plan-Kontext (`build_context`) einfließt.
    """
    context = build_context(
        state, forecast, constraints, [],
        valid_from=valid_from, valid_until=valid_until,
        weather=weather, horizon_h=horizon_h, weather_detail=weather_detail,
        now=now, previous_plan=previous_plan, global_regeln=global_regeln,
        rueckblick=rueckblick, features=features, system_features=system_features,
    )
    del context["objectives"]
    context["ziele"] = [
        {"id": z.id, "name": z.name, "beschreibung": z.beschreibung, "geraete": list(z.devices)}
        for z in ziele
    ]
    return context


# Standard-Instruktion für die Planung. Über die EP-Oberfläche editierbar (in der
# `config`-Tabelle persistiert); der `Daten:`-Block wird IMMER von `build_prompt`
# angehängt, das Antwort-Schema bleibt code-kontrolliert und der Validator erzwingt die
# harten Grenzen unabhängig vom Prompt (eiserne Regeln 10/11).
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
    "- Ist `previous_plan` vorhanden, ist das dein zuletzt veröffentlichter Plan (je Gerät die "
    "vorigen Vorschlagswerte). Bleibe ohne materiellen Grund nah daran: ändere Priorität oder "
    "Freigabe nur, wenn die aktuellen Daten es klar erfordern – nicht wegen kleiner "
    "Schwankungen. Das hält den Plan über die Läufe hinweg stabil.\n\n"
    "Regeln des Users (wichtigster Block):\n"
    "- `regeln` je Gerät und `globale_regeln` sind die vom User in eigenen Worten formulierten "
    "Betriebsvorgaben. Sie sind **verbindlich** und stehen über jeder Optimierung: greift eine "
    "Regel auf die aktuelle Lage zu, richte deinen Vorschlag danach – auch wenn ein Ziel etwas "
    "anderes nahelegt.\n"
    "- Nenne je Gerät in `angewandte_regeln`, auf welche dieser Regeln du dich stützt, und "
    "begründe deinen Vorschlag in `begruendung` mit der maßgeblichen Messgröße samt Wert. "
    "Greift keine Regel, gib eine leere Liste zurück und sage das in der Begründung.\n"
    "- Unterscheide `funktion` (was das Gerät ist) von `regeln` (was der User will).\n\n"
    "Werte richtig lesen:\n"
    "- `now` ist der aktuelle Zeitpunkt. Datumsangaben in deinen Texten als TT.MM.JJJJ, "
    "Uhrzeiten als hh:mm in Berliner Zeit, ohne Zeitzonen-Kürzel.\n"
    "- Jeder `zusatzwerte`-Eintrag hat eine `rolle`: `ist` = gemessener Wert, `grenze` = vom User "
    "gesetzte Ober-/Untergrenze, `sollwert` = Vorgabe. **Verwechsle eine `grenze` oder einen "
    "`sollwert` nie mit einem Messwert.** Die gemessenen Größen des Hauses stehen in `state`.\n"
    "- `state` führt je Mess-Rolle den Letztwert (`latest`) und die Mittel über 1/15/60 Minuten. "
    "Der Vergleich der Mittel zeigt den Verlauf: steigt z.B. die Warmwassertemperatur, ohne dass "
    "der Heizstab Leistung zieht, erwärmt eine andere Quelle den Speicher – dann braucht es "
    "keinen elektrischen Nachschub.\n"
    "- `weather.kennzahlen` ist für Tagesaussagen maßgeblich (`temp_max_heute`, `temp_max_24h`, "
    "`temp_max_48h`): die Slot-Reihen in `weather.models` sind abends leer bzw. überspringen "
    "heute. Leite Tageshöchstwerte NICHT aus den Slots ab, wenn Kennzahlen vorliegen.\n"
    "- Werte mit `veraltet: true` oder `wert: null` sind **unbekannt**, nicht null und nicht in "
    "Ordnung. Ein unbekannter Wert ist kein Freibrief: wähle dann die vorsichtige Variante "
    "(Last nicht freigeben, Grenze nicht anheben) und vermerke es in `unsicherheiten`.\n"
    "- `datenlage.frische_prozent` sagt dir, wie viel des Kontexts überhaupt belegt ist.\n\n"
    "Über mehrere Tage bilanzieren, nicht auf Schwellen schauen:\n"
    "- **Ein Messwert allein entscheidet nichts.** Ein Wärmespeicher mit 65 °C braucht keinen "
    "Strom, wenn die nächsten Tage sonnig sind und die Solarthermie liefert — und er braucht "
    "welchen, wenn die nächsten Tage trüb sind und heute der letzte Überschuss ist. Dieselbe "
    "Temperatur, zwei entgegengesetzte richtige Antworten. Entscheide deshalb nie an einer "
    "Schwelle, sondern an der Bilanz.\n"
    "- `rueckblick` liefert die gemessenen Tageswerte. Vergleiche dort die Änderung einer "
    "Speichertemperatur (`delta`) mit der elektrischen Tagesenergie desselben Geräts: war die "
    "Energie ~0 und die Temperatur ist gestiegen, hat eine andere Quelle geheizt. Halte das gegen "
    "die Bewölkung des Tages, um die Folgetage abzuschätzen.\n"
    "- `merkmale.geraete` rechnet das für dich: `reserve_kwh` (Energie über dem Komfortminimum), "
    "`energiebedarf_kwh` (Lücke bis zum Zielwert), `fremdwaerme_mittel_kwh` (beobachteter Gewinn "
    "ohne Strom) und `deckung_tage`. Fehlt ein Wert, steht der Grund in `fehlt` — dann ist er "
    "unbekannt, nicht 0.\n"
    "- Reicht die Reserve über die Tage, bis wieder Fremdwärme kommt, gib keine elektrische Last "
    "frei. Reicht sie nicht, wähle das Fenster mit dem größten Überschuss "
    "(`merkmale.system.ueberschuss`) — und wenn der morgen wegfällt, ist das heute.\n"
    "- Nenne in `begruendung` die Bilanz mit Zahlen, nicht nur die Regel: „Reserve 4,1 kWh, "
    "letzte Tage +6 kWh/Tag ohne Strom, Folgetage ähnlich bewölkt ⇒ kein elektrischer Eintrag\".\n"
    "\n"
    "Konfidenz:\n"
    "- Gib `konfidenz` als vier Teilnoten (0–100) gemäß der Beschreibung im Schema aus. Bewerte "
    "sie ehrlich und unabhängig voneinander – EP rechnet daraus die Gesamtkonfidenz und "
    "vergleicht deine `datenlage`-Note mit der real gemessenen Datenlage.\n"
    "- Liste in `unsicherheiten` konkret, was dir gefehlt hat.\n\n"
    "Gib zusätzlich eine kurze deutsche `reasoning`-Begründung und optionale `warnings` aus. "
    "Antworte ausschließlich als JSON gemäß dem vorgegebenen Schema."
)


def planning_instruction(template: str | None = None) -> str:
    """Die Instruktion allein: user-gepflegtes Template oder `DEFAULT_PLANNING_PROMPT`.

    Geht als **System-Anweisung** an den Provider (D-062). Anweisung und Daten in getrennten
    Kanälen zu halten verbessert die Regeltreue merklich — vorher lagen Rollentext, harte Regeln
    und ein mehrere Kilobyte großer JSON-Block in derselben User-Nachricht.
    """
    return (template or "").strip() or DEFAULT_PLANNING_PROMPT


def build_data_block(context: dict) -> str:
    """Der Datenblock allein (User-Nachricht): der verdichtete Kontext als JSON."""
    return f"Daten:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n"


def build_prompt(context: dict, template: str | None = None) -> str:
    """Baut den vollständigen Planungs-Prompt: Instruktion + angehängter Datenblock.

    `template` ist die optional vom User in der EP-Oberfläche gepflegte Instruktion; fehlt sie,
    gilt `DEFAULT_PLANNING_PROMPT`. Der `Daten:`-Block wird unabhängig vom Template immer
    angehängt, damit der Kontext nie versehentlich fehlt.

    Diese zusammengesetzte Form ist die **dokumentierte** Sicht: sie geht in die UI, in den
    Plan-Datensatz (D-063) und in den Kontext-Hash. Beim Aufruf werden Instruktion und Daten
    getrennt übergeben (`planning_instruction` / `build_data_block`, D-062).
    """
    return f"{planning_instruction(template)}\n\n{build_data_block(context)}"


# Standard-Instruktion für die Klassifizierung (D-055). Läuft VOR dem Planungs-Aufruf, bekommt
# dieselben Daten (`build_classification_context`) und leitet nur die Gewichtung der user-
# definierten Ziele ab; über die EP-Oberfläche editierbar (in der `config`-Tabelle persistiert).
DEFAULT_CLASSIFICATION_PROMPT = (
    "Du bist der Ziel-Klassifizierer des Home-Assistant-Addons „Skytech Energy Pilot“. "
    "Du erzeugst KEINEN Energieplan, sondern leitest aus den folgenden Daten eine Gewichtung "
    "(0–100 %) für jedes vom User definierte Ziel ab – als Vorbereitung für den nachfolgenden "
    "Planungs-Aufruf.\n\n"
    "Regeln:\n"
    "- `ziele` listet die vom User definierten Ziele: `id`, `name`, `beschreibung` und "
    "`geraete` (die diesem Ziel zugeordneten Gerätenamen aus `devices`, kann leer sein für "
    "geräteunabhängige/globale Ziele).\n"
    "- Leite je Ziel-`id` ein Gewicht 0–100 ab, wie wichtig/dringend dieses Ziel JETZT ist – "
    "auf Basis von `state` (aktuelle Werte), `forecast` (PV-Prognose), `weather`, den "
    "harten Grenzen/Zusatzwerten der zugeordneten `geraete` und `previous_plan` (falls "
    "vorhanden, für Stabilität über Läufe hinweg).\n"
    "- Höheres Gewicht = wichtiger/dringender im aktuellen Kontext, NICHT eine feste Rangfolge.\n"
    "- Beachte `regeln` je Gerät und `globale_regeln`: sperrt eine Regel eine Last für die "
    "aktuelle Lage, ist ein Ziel, das genau diese Last fordert, jetzt nicht dringend.\n"
    "- `weather.kennzahlen` (`temp_max_heute`, `temp_max_24h`, `temp_max_48h`) ist für "
    "Tagesaussagen maßgeblich; Werte mit `veraltet: true` oder `null` sind unbekannt.\n"
    "- Antworte für JEDE Ziel-`id` aus `ziele` mit exakt einem Gewicht; erfinde keine Ziele.\n"
    "- Gib zusätzlich eine kurze deutsche `reasoning`-Begründung aus. Antworte ausschließlich "
    "als JSON gemäß dem vorgegebenen Schema."
)


def classification_instruction(template: str | None = None) -> str:
    """Die Klassifizierungs-Instruktion allein (System-Kanal, D-062)."""
    return (template or "").strip() or DEFAULT_CLASSIFICATION_PROMPT


def build_classification_prompt(context: dict, template: str | None = None) -> str:
    """Baut den vollständigen Klassifizierungs-Prompt: Instruktion + angehängter Datenblock.

    Identischer Aufbau wie `build_prompt` (D-055): `template` ist die optional vom User
    gepflegte Instruktion; fehlt sie, gilt `DEFAULT_CLASSIFICATION_PROMPT`. Der `Daten:`-Block
    wird unabhängig vom Template immer angehängt.
    """
    return f"{classification_instruction(template)}\n\n{build_data_block(context)}"


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
        # Grenzen zusätzlich als Schema-Keyword (D-062): sie wirken damit im Decoder und nicht
        # nur als Prosa, die ein kleines Modell überlesen kann.
        if ce.min is not None:
            prop["minimum"] = ce.min
        if ce.max is not None:
            prop["maximum"] = ce.max
    elif ce.kind == "datetime":
        desc.append(f"Format {_datetime_format(ce.has_date, ce.has_time)}.")
    elif ce.kind == "select" and ce.options:
        # Auswahlpool als Enum erzwingen (D-049): die KI MUSS genau eine Option wählen.
        prop["enum"] = list(ce.options)
        desc.append("Wähle genau einen dieser Werte: " + ", ".join(ce.options) + ".")
    if desc:
        prop["description"] = " ".join(str(p) for p in desc)
    return prop


def _fixed_field_schema(key: str, constraint: DeviceConstraint) -> dict:
    """Antwort-Schema-Property eines festen Vorschlagsfelds (Prio/Freigabe/Mindestleistung).

    Die harten Grenzen des Geräts gehen als `minimum`/`maximum` mit ins Schema (D-062): sie
    wirken damit schon im Decoder statt nur als Prosa im Prompt. Der Validator klemmt weiterhin
    unabhängig davon — das Schema ist eine Hilfe für das Modell, keine Sicherheitsgarantie.
    """
    if key == "prio_vorschlag":
        return {
            "type": "INTEGER",
            "minimum": _PRIO_MIN,
            "maximum": _PRIO_MAX,
            "description": "10er-Rangfolge ab 10 (höchste Prio); nicht für die Batterie.",
        }
    if key == "freigabe_vorschlag":
        return {"type": "BOOLEAN"}
    # geschutzte_mindestleistung_{w,a}_vorschlag
    prop: dict[str, object] = {"type": "NUMBER"}
    lo = constraint.min_power if constraint.min_power is not None else 0.0
    prop["minimum"] = max(0.0, float(lo))
    if constraint.max_power is not None:
        prop["maximum"] = float(constraint.max_power)
    einheit = "A" if key.endswith("_a_vorschlag") else "W"
    prop["description"] = (
        f"Geschützte Mindestleistung in {einheit}, innerhalb der technischen Grenzen des Geräts."
    )
    return prop


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
            else _fixed_field_schema(key, constraint)
        )
    # Erzwungene Selbsterklärung (D-060): das Modell muss seine Entscheidung für DIESES Gerät
    # gegen die Freitext-Regeln des Users begründen. Kein Vorschlagswert, keine Korrektur —
    # aber eine falsche Entscheidung ist damit im Plan-Tab lesbar statt rätselhaft.
    properties["begruendung"] = {
        "type": "STRING",
        "description": (
            "Ein deutscher Satz: warum diese Werte für dieses Gerät. Nenne die maßgebliche "
            "Messgröße mit Wert."
        ),
    }
    properties["angewandte_regeln"] = {
        "type": "ARRAY",
        "items": {"type": "STRING"},
        "description": (
            "Die User-Regeln aus `regeln`/`globale_regeln`, auf die sich diese Entscheidung "
            "stützt — jeweils sinngemäß in einem Halbsatz. Greift keine Regel, gib eine leere "
            "Liste zurück und sage das in der Begründung."
        ),
    }
    order = ["name", *keys, *EXPLANATION_FIELDS]
    return {
        "type": "OBJECT",
        "properties": properties,
        "required": order,
        "propertyOrdering": order,
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
            # Konfidenz als definierte Teilnoten (D-064): eine einzelne Gesamtnote wäre frei
            # erfunden und als Grundlage eines Veröffentlichungs-Gates wertlos. EP aggregiert
            # die Teilnoten in Code als schwächstes Glied.
            "konfidenz": {
                "type": "OBJECT",
                "properties": {
                    part: {
                        "type": "INTEGER",
                        "minimum": 0,
                        "maximum": 100,
                        "description": rubrik,
                    }
                    for part, rubrik in CONFIDENCE_PARTS.items()
                },
                "required": list(CONFIDENCE_PARTS),
                "propertyOrdering": list(CONFIDENCE_PARTS),
            },
            "unsicherheiten": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": (
                    "Was du für diese Entscheidung nicht wusstest — fehlende Messwerte, "
                    "unklare Regeln, unsichere Prognose. Leere Liste, wenn nichts fehlte."
                ),
            },
            "reasoning": {"type": "STRING"},
            "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["devices", "konfidenz", "reasoning"],
        "propertyOrdering": [
            "devices", "konfidenz", "unsicherheiten", "reasoning", "warnings",
        ],
    }


def build_classification_response_schema(ziele: list[Ziel]) -> dict:
    """Gemini-Antwort-Schema der Klassifizierung: ein Gewicht je Ziel-`id`, ALLE Pflicht (D-055).

    Gleiches Muster wie `build_response_schema` (Pflichtfeld je bekanntem Schlüssel,
    `propertyOrdering` für stabile Ausgaben) – hier ein Property je Ziel statt je Gerät.
    """
    ids = [str(z.id) for z in ziele]
    return {
        "type": "OBJECT",
        "properties": {
            "gewichtung": {
                "type": "OBJECT",
                "properties": {
                    i: {"type": "INTEGER", "description": "Gewicht 0–100 %."} for i in ids
                },
                "required": ids,
                "propertyOrdering": ids,
            },
            "reasoning": {"type": "STRING"},
        },
        "required": ["gewichtung"],
        "propertyOrdering": ["gewichtung", "reasoning"],
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
