"""Tests für den KI-Kontext-, Prompt- und Antwort-Schema-Aufbau (Datenminimum)."""

from datetime import UTC, datetime, timedelta, timezone

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device, DeviceExtra
from energy_pilot.objectives import Objective, Ziel
from energy_pilot.plan_context import (
    DEFAULT_CLASSIFICATION_PROMPT,
    DEFAULT_PLANNING_PROMPT,
    _condense_weather,
    build_classification_context,
    build_classification_prompt,
    build_classification_response_schema,
    build_context,
    build_prompt,
    build_repair_prompt,
    build_response_schema,
    context_hash,
    quantize,
    weather_metrics,
)

# Fixe Objective-Liste als Ersatz für das frühere `objectives_from_config({})` (D-055: Ziele
# sind jetzt user-definiert + LLM-gewichtet, keine Config-Defaults mehr).
_OBJECTIVES = [Objective("test_ziel", "Test-Ziel", 80)]


def _weather_snapshot(n_slots=20):
    # OWM-Snapshot-Form wie WeatherCollector.snapshot(): forecast.slots[] in 3h-Schritten.
    slots = [
        {
            "time": f"2026-06-25 {3 * i:02d}:00:00",
            "temp": 20.0 + i,
            "feels_like": 19.0 + i,
            "clouds": 10.0 * (i % 10),
            "pop": 0.1,
            "wind_speed": 3.0,
            "humidity": 50.0,
            "rain_3h": None,
            "snow_3h": None,
            "condition": "klar",
        }
        for i in range(n_slots)
    ]
    return {"enabled": True, "units": "metric", "forecast": {"city": "Wien", "slots": slots}}


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


def test_build_response_schema_forces_all_fields_per_device():
    schema = build_response_schema(_constraints())
    assert schema["type"] == "OBJECT"
    # Konfidenz als definierte Teilnoten statt einer frei erfundenen Gesamtnote (D-064).
    konfidenz = schema["properties"]["konfidenz"]
    assert set(konfidenz["required"]) == {
        "datenlage", "prognosesicherheit", "regelklarheit", "zielkonflikt",
    }
    assert all(prop.get("description") for prop in konfidenz["properties"].values())
    assert "unsicherheiten" in schema["properties"]
    # Kein JSON-Schema-Dialekt, den Gemini ablehnt:
    assert "$schema" not in schema
    assert "additionalProperties" not in schema
    devices = schema["properties"]["devices"]
    # `devices` ist ein OBJECT (Property je Gerätename), kein Array – nur so lässt sich pro Gerät
    # ein eigenes `required` erzwingen (Kernfix D-050 gegen schwankende Ausgabefelder).
    assert devices["type"] == "OBJECT"
    assert set(devices["required"]) == {"batterie", "heizstab", "heizluefter_1"}
    heizstab = devices["properties"]["heizstab"]
    assert heizstab["properties"]["name"]["type"] == "STRING"
    # ALLE Vertragsfelder des Heizstabs sind Pflicht (das Modell darf keines weglassen), plus
    # die erzwungene Selbsterklärung je Gerät (D-060).
    assert set(heizstab["required"]) == {
        "name", "prio_vorschlag", "freigabe_vorschlag",
        "geschutzte_mindestleistung_w_vorschlag",
        "begruendung", "angewandte_regeln", "entscheidungsfaktoren",
    }
    # Harte Grenzen wirken als Schema-Keyword, nicht nur als Prosa (D-062).
    assert heizstab["properties"]["prio_vorschlag"]["minimum"] == 10
    assert heizstab["properties"]["geschutzte_mindestleistung_w_vorschlag"]["maximum"] == 3000.0
    # Batterie: nur geschützte Mindestleistung Pflicht, keine Prio (D-037).
    assert set(devices["properties"]["batterie"]["required"]) == {
        "name", "geschutzte_mindestleistung_w_vorschlag",
        "begruendung", "angewandte_regeln", "entscheidungsfaktoren",
    }


def _typed_extra_constraints():
    # Ein Gerät mit vier Zusatz-Entitäten unterschiedlicher Domäne (D-048).
    extras = (
        DeviceExtra(read_entity_id="input_number.min_soc", ai_suggestion=True, ai_hint="Min-SOC"),
        DeviceExtra(read_entity_id="input_boolean.eco", ai_suggestion=True),
        DeviceExtra(read_entity_id="input_datetime.abfahrt", ai_suggestion=True),
        DeviceExtra(read_entity_id="input_text.notiz", ai_suggestion=True),
    )
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, "ampere", extras=extras)
    readings = {"wallbox": {
        "extra_min_soc": {"value": 20.0, "attrs": {"min": 0, "max": 100}},
        "extra_abfahrt": {"value": "2026-07-02 08:00:00",
                          "attrs": {"has_date": True, "has_time": True}},
    }}
    return build_constraints([dev], readings)


def test_response_schema_types_follow_extra_domain():
    wallbox = build_response_schema(_typed_extra_constraints())["properties"]["devices"][
        "properties"
    ]["wallbox"]
    props = wallbox["properties"]
    assert props["extra_min_soc_vorschlag"]["type"] == "NUMBER"
    assert props["extra_eco_vorschlag"]["type"] == "BOOLEAN"
    assert props["extra_abfahrt_vorschlag"]["type"] == "STRING"
    assert props["extra_notiz_vorschlag"]["type"] == "STRING"
    # min/max und Format landen in der Feldbeschreibung.
    assert "0 bis 100" in props["extra_min_soc_vorschlag"]["description"]
    assert "Datum und Uhrzeit" in props["extra_abfahrt_vorschlag"]["description"]
    # D-050: alle aktivierten Zusatz-Vorschlagsfelder sind Pflicht -> werden nie mehr „vergessen".
    for extra_field in (
        "extra_min_soc_vorschlag", "extra_eco_vorschlag",
        "extra_abfahrt_vorschlag", "extra_notiz_vorschlag",
    ):
        assert extra_field in wallbox["required"]


def test_context_zusatzwerte_carry_type_bounds_and_format():
    from energy_pilot.plan_context import _condense_constraint

    entry = _condense_constraint(_typed_extra_constraints()[0])
    by_field = {z["vorschlagsfeld"]: z for z in entry["zusatzwerte"]}
    num = by_field["extra_min_soc_vorschlag"]
    assert num["typ"] == "number" and num["untergrenze"] == 0.0 and num["obergrenze"] == 100.0
    dt = by_field["extra_abfahrt_vorschlag"]
    assert dt["typ"] == "datetime" and "Datum und Uhrzeit" in dt["format"]


def _select_constraints():
    ex = DeviceExtra(read_entity_id="input_select.lademodus", ai_suggestion=True, ai_hint="Modus")
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, "ampere", extras=(ex,))
    readings = {"wallbox": {"extra_lademodus": {
        "value": "PV-Überschuss", "attrs": {"options": ["Aus", "PV-Überschuss", "Schnell"]},
    }}}
    return build_constraints([dev], readings)


def test_response_schema_select_uses_enum_pool():
    # input_select (D-049): Antwort-Schema erzwingt genau eine Option (Enum).
    props = build_response_schema(_select_constraints())["properties"]["devices"]["properties"][
        "wallbox"
    ]["properties"]
    field = props["extra_lademodus_vorschlag"]
    assert field["type"] == "STRING"
    assert field["enum"] == ["Aus", "PV-Überschuss", "Schnell"]
    assert "PV-Überschuss" in field["description"]


def test_build_repair_prompt_lists_missing_fields():
    # D-050: die Nachforderung hängt an den Basis-Prompt an und benennt exakt die Lücken.
    base = build_prompt(
        build_context({}, {}, _constraints(), _OBJECTIVES,
                      valid_from="A", valid_until="B")
    )
    out = build_repair_prompt(base, {"heizstab": ["prio_vorschlag", "freigabe_vorschlag"]})
    assert out.startswith(base)
    assert "unvollständig" in out
    assert "heizstab: prio_vorschlag, freigabe_vorschlag" in out


def test_context_select_carries_option_pool():
    from energy_pilot.plan_context import _condense_constraint

    entry = _condense_constraint(_select_constraints()[0])
    z = entry["zusatzwerte"][0]
    assert z["typ"] == "select"
    assert z["optionen"] == ["Aus", "PV-Überschuss", "Schnell"]


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
        state, forecast, _constraints(), _OBJECTIVES,
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
        {}, {}, _constraints(), _OBJECTIVES, valid_from="A", valid_until="B"
    )
    prompt = build_prompt(ctx)
    assert isinstance(prompt, str)
    assert "Orchestrator" in prompt
    assert "heizstab" in prompt  # die verdichteten Gerätedaten stehen im Prompt


def test_default_prompt_mentions_weather():
    assert "weather" in DEFAULT_PLANNING_PROMPT or "Wetter" in DEFAULT_PLANNING_PROMPT


def test_build_prompt_uses_custom_template_and_always_appends_data():
    ctx = build_context(
        {}, {}, _constraints(), _OBJECTIVES, valid_from="A", valid_until="B"
    )
    prompt = build_prompt(ctx, "MEIN EIGENER PROMPT")
    assert prompt.startswith("MEIN EIGENER PROMPT")
    assert "Orchestrator" not in prompt  # Default-Text ersetzt
    assert "Daten:" in prompt  # Datenblock wird IMMER angehängt
    assert "heizstab" in prompt


def test_build_prompt_blank_template_falls_back_to_default():
    ctx = build_context(
        {}, {}, _constraints(), _OBJECTIVES, valid_from="A", valid_until="B"
    )
    assert "Orchestrator" in build_prompt(ctx, "   ")


def test_condense_weather_compact_trims_to_horizon_and_keeps_few_fields():
    out = _condense_weather(_weather_snapshot(20), horizon_h=24, detail="compact")
    # 24h / 3h-Schritte = 8 Schritte
    assert len(out["slots"]) == 8
    assert out["detail"] == "compact"
    assert out["city"] == "Wien"
    slot = out["slots"][0]
    assert set(slot.keys()) == {"time", "temp", "clouds", "pop"}


def test_condense_weather_full_keeps_all_slots_and_fields():
    out = _condense_weather(_weather_snapshot(20), horizon_h=24, detail="full")
    assert len(out["slots"]) == 20  # nicht gekürzt
    assert out["detail"] == "full"
    assert "wind_speed" in out["slots"][0]
    assert "humidity" in out["slots"][0]


def test_condense_weather_empty_without_forecast():
    assert _condense_weather({}, horizon_h=24, detail="compact") == {}
    no_fc = {"enabled": False, "forecast": None}
    assert _condense_weather(no_fc, horizon_h=24, detail="compact") == {}


def test_build_context_includes_weather():
    ctx = build_context(
        {}, {}, _constraints(), _OBJECTIVES,
        valid_from="A", valid_until="B",
        weather=_weather_snapshot(4), horizon_h=24, weather_detail="full",
    )
    assert ctx["weather"]["detail"] == "full"
    assert len(ctx["weather"]["slots"]) == 4


# Fester Bezugszeitpunkt für die One-Call-Tests: 10.07.2026, 09:30 UTC = 11:30 Ortszeit (+2 h).
_OC_OFFSET_S = 7200
_OC_NOW = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)


def _onecall_snapshot(now=_OC_NOW, *, offset_s=_OC_OFFSET_S,
                      enable_15min=False, enable_1h=True, enable_1day=True, n_days=8):
    """OneCallCollector.snapshot()-Form mit echten Unix-Zeitstempeln relativ zu `now`.

    Je Vorhersagemodell per `enable_*` an/aus (steuert `enabled` + ob Slots vorliegen). Stündliche/
    15-min-Slots liegen dicht um `now` (~2 Tage voraus), Tages-Slots ab heute für `n_days` Tage.
    """
    tz = timezone(timedelta(seconds=offset_s))
    now_local = now.astimezone(tz)

    def entry(t, **extra):
        return {
            "dt": int(t.timestamp()),
            "time": t.astimezone(UTC).strftime("%Y-%m-%d %H:%M"),
            "temp": 20.0, "clouds": 10.0, "pop": 0.1, **extra,
        }

    base_h = now_local.replace(minute=0, second=0, microsecond=0)
    hourly = [entry(base_h + timedelta(hours=k)) for k in range(-6, 43)] if enable_1h else []

    q = now_local.replace(second=0, microsecond=0)
    q -= timedelta(minutes=q.minute % 15)
    q15 = [entry(q + timedelta(minutes=15 * k)) for k in range(-8, 4 * 24)] if enable_15min else []

    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    daily = ([entry(midnight + timedelta(days=k), temp_min=10.0 + k, temp_max=25.0 + k)
              for k in range(n_days)] if enable_1day else [])

    return {
        "enabled": True,
        "source": "onecall",
        "units": "metric",
        "timelines": {
            "15min": {"enabled": enable_15min, "timezone_offset_s": offset_s, "slots": q15},
            "1h": {"enabled": enable_1h, "timezone_offset_s": offset_s, "slots": hourly},
            "1day": {"enabled": enable_1day, "timezone_offset_s": offset_s, "slots": daily},
        },
    }


def test_condense_weather_onecall_hourly_window_today_until_21():
    # 11:30 Ortszeit → Stundenreihe 12:00 … 21:00 des heutigen Tages (upcoming_changes.md).
    out = _condense_weather(_onecall_snapshot(), horizon_h=24, detail="compact", now=_OC_NOW)
    assert out["source"] == "onecall"
    hourly = out["models"]["1h"]
    assert hourly["aufloesung"] == "stündlich"
    times = [s["time"] for s in hourly["slots"]]
    assert times[0] == "2026-07-10 12:00"
    assert times[-1] == "2026-07-10 21:00"
    assert len(times) == 10
    assert set(hourly["slots"][0].keys()) == {"time", "temp", "clouds", "pop"}


def test_condense_weather_onecall_hourly_empty_after_21():
    # 22:30 Ortszeit → keine stündlichen Slots mehr heute; Tagesausblick bleibt bestehen.
    now = datetime(2026, 7, 10, 20, 30, tzinfo=UTC)
    out = _condense_weather(_onecall_snapshot(now), horizon_h=24, detail="compact", now=now)
    assert out["models"]["1h"]["slots"] == []
    assert len(out["models"]["1day"]["slots"]) == 5


def test_condense_weather_onecall_hourly_starts_at_six_when_early():
    # 04:00 Ortszeit → Start frühestens 6 Uhr, bis 21 Uhr.
    now = datetime(2026, 7, 10, 2, 0, tzinfo=UTC)
    out = _condense_weather(_onecall_snapshot(now), horizon_h=24, detail="compact", now=now)
    times = [s["time"] for s in out["models"]["1h"]["slots"]]
    assert times[0] == "2026-07-10 06:00"
    assert times[-1] == "2026-07-10 21:00"
    assert len(times) == 16  # 06:00 … 21:00 inklusiv


def test_condense_weather_onecall_daily_next_five_days_from_tomorrow():
    # Heute 10.07. → Tagesprognose 11.07.–15.07. (heute deckt bereits die Stundenreihe ab).
    out = _condense_weather(_onecall_snapshot(), horizon_h=24, detail="compact", now=_OC_NOW)
    daily = out["models"]["1day"]
    assert daily["aufloesung"] == "täglich"
    days = [s["time"] for s in daily["slots"]]
    assert days == ["2026-07-11", "2026-07-12", "2026-07-13", "2026-07-14", "2026-07-15"]
    assert "temp_min" in daily["slots"][0]
    assert "temp_max" in daily["slots"][0]


def test_condense_weather_onecall_combines_all_active_models():
    # 15min + 1h + 1day aktiv → alle drei Modelle gehen gemeinsam an die KI (D-054).
    out = _condense_weather(
        _onecall_snapshot(enable_15min=True, enable_1h=True, enable_1day=True),
        horizon_h=24, detail="compact", now=_OC_NOW,
    )
    assert set(out["models"]) == {"15min", "1h", "1day"}
    q = out["models"]["15min"]
    assert q["aufloesung"] == "15-Minuten"
    times = [s["time"] for s in q["slots"]]
    assert times[0] == "2026-07-10 11:30"  # nächster 15-min-Schritt ab 11:30
    assert times[-1] == "2026-07-10 21:00"  # 21:15 liegt bereits hinter dem Fenster


def test_condense_weather_onecall_only_selected_models_included():
    # Nur das Tagesmodell aktiv → nur `1day` erscheint (keine Stundenreihe).
    out = _condense_weather(
        _onecall_snapshot(enable_15min=False, enable_1h=False, enable_1day=True),
        horizon_h=24, detail="compact", now=_OC_NOW,
    )
    assert set(out["models"]) == {"1day"}


def test_condense_weather_onecall_skips_disabled_even_with_stale_slots():
    # Deaktiviertes Modell mit noch vorhandenen (alten) Slots darf NICHT an die KI gehen.
    snap = _onecall_snapshot(enable_1h=True, enable_1day=True)
    snap["timelines"]["1day"]["enabled"] = False
    out = _condense_weather(snap, horizon_h=24, detail="compact", now=_OC_NOW)
    assert set(out["models"]) == {"1h"}


def test_condense_weather_onecall_empty_without_any_active_model():
    snap = _onecall_snapshot(enable_15min=False, enable_1h=False, enable_1day=False)
    assert _condense_weather(snap, horizon_h=24, detail="compact", now=_OC_NOW) == {}


def test_build_context_includes_onecall_weather():
    ctx = build_context(
        {}, {}, _constraints(), _OBJECTIVES,
        valid_from="A", valid_until="B",
        weather=_onecall_snapshot(), horizon_h=24, now=_OC_NOW,
    )
    assert ctx["weather"]["source"] == "onecall"
    assert len(ctx["weather"]["models"]["1h"]["slots"]) == 10
    assert len(ctx["weather"]["models"]["1day"]["slots"]) == 5


def test_build_context_includes_device_funktion_only_when_set():
    # KI-Beschreibung je Gerät (D-051): erscheint als Kontext-Feld `funktion`, nur wenn gesetzt.
    devices = [
        Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt",
               ai_prompt="Versorgt die Fußbodenheizung, träge."),
        Device("heizluefter_1", "Heizlüfter 1", "heizluefter_1", BINARY, "watt"),
    ]
    readings = {
        "heizstab": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 500.0},
            "max_technisch": {"value": 3000.0},
        },
        "heizluefter_1": {"technische_freigabe": {"value": True}, "leistung_w": {"value": 1500.0}},
    }
    ctx = build_context(
        {}, {}, build_constraints(devices, readings), _OBJECTIVES,
        valid_from="A", valid_until="B",
    )
    by_name = {d["name"]: d for d in ctx["devices"]}
    assert by_name["heizstab"]["funktion"] == "Versorgt die Fußbodenheizung, träge."
    assert "funktion" not in by_name["heizluefter_1"]  # ohne Prompt kein Feld (Datenminimum)


def test_default_prompt_mentions_funktion():
    assert "funktion" in DEFAULT_PLANNING_PROMPT


# --- A1: Vorplan als Anker in den KI-Kontext -------------------------------------------------

def _prev_plan():
    # Form wie Planner.latest_plan(): {ts, ok, plan, validation}.
    return {
        "ts": "2026-07-11T10:00:00+00:00",
        "ok": True,
        "plan": {
            "plan_id": "abc123",
            "valid_from": "2026-07-11T09:45:00+00:00",
            "valid_until": "2026-07-11T10:45:00+00:00",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "confidence": 82,
            "reasoning": "Langer Vorplan-Text, gehört nicht in den Kontext.",
            "warnings": ["egal"],
            "devices": [
                {"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                 "geschutzte_mindestleistung_w_vorschlag": 800.0},
                {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
            ],
        },
        "validation": {"ok": True, "errors": [], "clamped": []},
    }


def test_build_context_includes_condensed_previous_plan():
    ctx = build_context(
        {}, {}, _constraints(), _OBJECTIVES,
        valid_from="A", valid_until="B", previous_plan=_prev_plan(),
    )
    prev = ctx["previous_plan"]
    # Nur Gerät-Vorschlagswerte + Konfidenz – kein Reasoning/Warnings/Zeitstempel (Datenminimum).
    assert prev["confidence"] == 82
    assert "reasoning" not in prev and "warnings" not in prev and "valid_from" not in prev
    heizstab = next(d for d in prev["devices"] if d["name"] == "heizstab")
    assert heizstab["prio_vorschlag"] == 10
    assert heizstab["freigabe_vorschlag"] is True
    assert heizstab["geschutzte_mindestleistung_w_vorschlag"] == 800.0


def test_build_context_omits_previous_plan_when_absent():
    # Kein Vorplan (erster Lauf) -> Schlüssel fehlt komplett, kein leeres Objekt.
    ctx = build_context(
        {}, {}, _constraints(), _OBJECTIVES,
        valid_from="A", valid_until="B",
    )
    assert "previous_plan" not in ctx
    # Auch ein Vorplan ohne Geräte hängt keinen Anker an.
    empty = build_context(
        {}, {}, _constraints(), _OBJECTIVES,
        valid_from="A", valid_until="B",
        previous_plan={"ok": True, "plan": {"devices": []}},
    )
    assert "previous_plan" not in empty


def test_default_prompt_mentions_previous_plan():
    assert "previous_plan" in DEFAULT_PLANNING_PROMPT


# --- D-055: Klassifizierungs-Kontext/Prompt/Schema (vorgelagerter Ziel-Aufruf) -----------------

def _ziele():
    return [
        Ziel(
            id=1, name="Warmwasserkomfort", beschreibung="Genug warmes Wasser",
            devices=("heizstab",),
        ),
        Ziel(id=2, name="Netzbezug minimieren", beschreibung="", devices=()),
    ]


def test_build_classification_context_replaces_objectives_with_ziele():
    ctx = build_classification_context(
        {}, {}, _constraints(), _ziele(), valid_from="A", valid_until="B"
    )
    assert "objectives" not in ctx
    assert ctx["ziele"] == [
        {"id": 1, "name": "Warmwasserkomfort", "beschreibung": "Genug warmes Wasser",
         "geraete": ["heizstab"]},
        {"id": 2, "name": "Netzbezug minimieren", "beschreibung": "", "geraete": []},
    ]
    # Gleiche Datenbasis wie build_context (Datenminimum, eiserne Regel 12):
    # state/forecast/weather/devices bleiben.
    assert "state" in ctx and "forecast" in ctx and "weather" in ctx and "devices" in ctx


def test_build_classification_prompt_uses_default_and_template():
    ctx = build_classification_context(
        {}, {}, _constraints(), _ziele(), valid_from="A", valid_until="B"
    )
    default_prompt = build_classification_prompt(ctx)
    assert default_prompt.startswith(DEFAULT_CLASSIFICATION_PROMPT)
    assert "Daten:" in default_prompt
    custom = build_classification_prompt(ctx, "SONDER-INSTRUKTION")
    assert custom.startswith("SONDER-INSTRUKTION")


def test_build_classification_response_schema_requires_all_ziel_ids():
    schema = build_classification_response_schema(_ziele())
    gewichtung = schema["properties"]["gewichtung"]
    assert set(gewichtung["required"]) == {"1", "2"}
    assert gewichtung["properties"]["1"]["type"] == "INTEGER"
    assert schema["required"] == ["gewichtung"]


def test_build_classification_response_schema_empty_ziele():
    schema = build_classification_response_schema([])
    assert schema["properties"]["gewichtung"]["required"] == []


# --- Wetter-Kennzahlen (D-062) ---------------------------------------------------------------


def test_weather_kennzahlen_present_alongside_models():
    """Kennzahlen liegen zusätzlich zu den Slot-Reihen vor und tragen das heutige Maximum."""
    out = _condense_weather(_onecall_snapshot(), horizon_h=24, detail="compact", now=_OC_NOW)
    kennzahlen = out["kennzahlen"]
    # Tages-Slot von heute: temp_max = 25.0 (Fixture k=0) – die Stundenreihe kennt nur 20.0.
    assert kennzahlen["temp_max_heute"] == 25.0
    assert kennzahlen["temp_min_heute"] == 10.0
    assert kennzahlen["temp_jetzt"] == 20.0
    assert kennzahlen["temp_max_24h"] >= 25.0
    assert kennzahlen["temp_max_48h"] >= kennzahlen["temp_max_24h"]
    assert kennzahlen["pop_max_24h"] == 0.1


def test_weather_kennzahlen_survive_after_21_when_hourly_window_is_empty():
    """Kernfall des Abendlochs: 23:30 Ortszeit – Stundenreihe leer, Kennzahlen vollständig."""
    now = _OC_NOW.replace(hour=21, minute=30)  # 23:30 Ortszeit (+2 h)
    out = _condense_weather(_onecall_snapshot(now), horizon_h=24, detail="compact", now=now)
    assert out["models"]["1h"]["slots"] == []  # bisheriges Verhalten unverändert
    kennzahlen = out["kennzahlen"]
    assert kennzahlen["temp_max_heute"] == 25.0
    assert "temp_max_48h" in kennzahlen


def test_weather_kennzahlen_without_daily_fall_back_to_intraday():
    """Ohne Tagesmodell entsteht das Tagesmaximum aus den verbleibenden Stunden-Slots."""
    snap = _onecall_snapshot(enable_1h=True, enable_1day=False)
    out = _condense_weather(snap, horizon_h=24, detail="compact", now=_OC_NOW)
    assert out["kennzahlen"]["temp_max_heute"] == 20.0


def test_weather_kennzahlen_empty_without_forecast():
    assert weather_metrics({}, now=_OC_NOW) == {}
    assert weather_metrics({"source": "forecast3h"}, now=_OC_NOW) == {}


# --- Frische, Datenlage, Quantisierung (D-063/D-064) -----------------------------------------


def _state(*, source="live", pv=1234.7):
    return {
        "pv_power": {
            "label": "PV-Leistung", "unit": "W", "averaged": True, "source": source,
            "latest": pv, "mean_1m": pv, "mean_15m": pv, "mean_60m": pv,
        },
        "hot_water_temp": {
            "label": "Warmwassertemperatur", "unit": "°C", "averaged": True, "source": "live",
            "latest": 76.13, "mean_1m": 76.0, "mean_15m": 74.82, "mean_60m": 71.21,
        },
    }


def _ctx(state=None, *, constraints=None, global_regeln="", now=None):
    return build_context(
        state if state is not None else _state(),
        {}, constraints if constraints is not None else _constraints(), _OBJECTIVES,
        valid_from="2026-07-10T09:30:00+00:00",
        valid_until="2026-07-10T10:30:00+00:00",
        now=now or _OC_NOW,
        global_regeln=global_regeln,
    )


def test_context_quantizes_numbers():
    """Rohe Messwerte werden auf fachliche Stufen gerundet – sonst ist kein Hash stabil."""
    ctx = _ctx()
    pv = next(e for e in ctx["state"] if e["role"] == "pv_power")
    assert pv["latest"] == 1230.0  # 10-W-Raster
    ww = next(e for e in ctx["state"] if e["role"] == "hot_water_temp")
    assert ww["latest"] == 76.0  # 0,5-°C-Raster
    assert ww["mean_15m"] == 75.0
    assert ww["mean_60m"] == 71.0


def test_context_marks_stale_values_and_reports_data_quality():
    """Ein nicht gelesener Wert ist als `veraltet` erkennbar und senkt die gemessene Datenlage."""
    ctx = _ctx(_state(source="none", pv=None))
    pv = next(e for e in ctx["state"] if e["role"] == "pv_power")
    assert pv["veraltet"] is True
    ww = next(e for e in ctx["state"] if e["role"] == "hot_water_temp")
    assert "veraltet" not in ww
    # Zwei erwartete Mess-Rollen, eine davon nicht gelesen (die Geräte hier haben keine
    # Zusatzwerte, die zusätzlich zählen würden).
    assert ctx["datenlage"]["frische_prozent"] == 50
    assert ctx["datenlage"]["fehlende_werte"] == ["pv_power"]


def test_context_data_quality_full_when_everything_read():
    assert _ctx()["datenlage"]["frische_prozent"] == 100


def test_context_carries_now_and_global_regeln():
    ctx = _ctx(global_regeln="Im Sommer keine elektrische Nachheizung.")
    assert ctx["now"] == _OC_NOW.isoformat()
    assert ctx["globale_regeln"] == "Im Sommer keine elektrische Nachheizung."


def test_context_omits_global_regeln_when_empty():
    assert "globale_regeln" not in _ctx(global_regeln="   ")


def test_context_hash_ignores_now_but_not_data():
    """Gleiche Sachlage ⇒ gleicher Hash, obwohl `now` sich zwischen den Läufen bewegt."""
    first = _ctx(now=_OC_NOW)
    second = _ctx(now=_OC_NOW + timedelta(minutes=3))
    assert first["now"] != second["now"]
    assert context_hash(first, prompt="P", model="M") == context_hash(second, prompt="P", model="M")
    # Ein geänderter Messwert ändert den Hash – sonst wäre er als Nachweis wertlos.
    changed = _ctx(_state(pv=5000.0))
    assert context_hash(changed, prompt="P", model="M") != context_hash(
        first, prompt="P", model="M"
    )
    # Instruktion und Modell gehen mit ein (anderer Prompt ⇒ anderer Plan).
    assert context_hash(first, prompt="Q", model="M") != context_hash(first, prompt="P", model="M")
    assert context_hash(first, prompt="P", model="N") != context_hash(first, prompt="P", model="M")


def test_quantize_leaves_non_numbers_and_bools_untouched():
    assert quantize(True, 10) is True
    assert quantize("76.1", 0.5) == "76.1"
    assert quantize(None, 0.5) is None
    assert quantize(76.13, 0.5) == 76.0


# --- Geräteregeln und Rollen-Semantik (D-060/D-061) ------------------------------------------


def test_device_regeln_and_extra_role_in_context():
    devices = [
        Device(
            "heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt",
            extras=(
                DeviceExtra(
                    read_entity_id="input_number.e3dc_heizstab_maxtemperatur",
                    ai_suggestion=True, label="Obergrenze", unit="°C", rolle="grenze",
                ),
            ),
            ai_regeln="Über 70 °C Warmwasser bleibt der Heizstab gesperrt.",
        ),
    ]
    readings = {
        "heizstab": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 0.0},
            "max_technisch": {"value": 3500.0},
            "extra_e3dc_heizstab_maxtemperatur": {"value": 85.0, "attrs": {"min": 50, "max": 95}},
        },
    }
    ctx = _ctx(constraints=build_constraints(devices, readings))
    entry = ctx["devices"][0]
    assert entry["regeln"] == "Über 70 °C Warmwasser bleibt der Heizstab gesperrt."
    extra = entry["zusatzwerte"][0]
    # Der 85-°C-Wert ist eine Grenze, kein Messwert – genau die Verwechslung, die den
    # 80-°C-Vorschlag bei 76 °C Ist-Temperatur ermöglicht hat.
    assert extra["rolle"] == "grenze"
    assert "kein Messwert" in extra["rolle_bedeutung"]


def test_planning_prompt_names_the_new_context_blocks():
    """Der Prompt muss die neuen Blöcke benennen, sonst liest das Modell sie nicht."""
    for needle in ("regeln", "kennzahlen", "rolle", "veraltet", "konfidenz", "angewandte_regeln"):
        assert needle in DEFAULT_PLANNING_PROMPT


def test_context_hash_ignores_model_derived_keys():
    """`objectives` und `previous_plan` sind Modell-/EP-Ausgabe, keine Sachlage (D-063).

    Steckten sie im Hash, würde ein streuender Klassifizierungs-Aufruf bzw. der eigene Vorplan
    den Vergleich bei jedem Lauf zerstören — und die Wiederverwendung könnte nie greifen.
    """
    base = _ctx()
    other_weights = build_context(
        _state(), {}, _constraints(), [Objective('test_ziel', 'Test-Ziel', 20)],
        valid_from="2026-07-10T09:30:00+00:00",
        valid_until="2026-07-10T10:30:00+00:00",
        now=_OC_NOW,
    )
    with_previous = build_context(
        _state(), {}, _constraints(), _OBJECTIVES,
        valid_from="2026-07-10T09:30:00+00:00",
        valid_until="2026-07-10T10:30:00+00:00",
        now=_OC_NOW,
        previous_plan={"plan": {"devices": [{"name": "heizstab", "prio_vorschlag": 10}]}},
    )

    assert base["objectives"] != other_weights["objectives"]
    assert "previous_plan" in with_previous
    for variant in (other_weights, with_previous):
        assert context_hash(variant, prompt="P", model="M") == context_hash(
            base, prompt="P", model="M"
        )
