"""Tests für den KI-Kontext-, Prompt- und Antwort-Schema-Aufbau (Datenminimum)."""

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device, DeviceExtra
from energy_pilot.objectives import objectives_from_config
from energy_pilot.plan_context import (
    DEFAULT_PLANNING_PROMPT,
    _condense_weather,
    build_context,
    build_prompt,
    build_repair_prompt,
    build_response_schema,
)


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
    assert "confidence" in schema["properties"]
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
    # ALLE Vertragsfelder des Heizstabs sind Pflicht (das Modell darf keines weglassen).
    assert set(heizstab["required"]) == {
        "name", "prio_vorschlag", "freigabe_vorschlag",
        "geschutzte_mindestleistung_w_vorschlag",
    }
    # Batterie: nur geschützte Mindestleistung Pflicht, keine Prio (D-037).
    assert set(devices["properties"]["batterie"]["required"]) == {
        "name", "geschutzte_mindestleistung_w_vorschlag",
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
        build_context({}, {}, _constraints(), objectives_from_config({}),
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


def test_default_prompt_mentions_weather():
    assert "weather" in DEFAULT_PLANNING_PROMPT or "Wetter" in DEFAULT_PLANNING_PROMPT


def test_build_prompt_uses_custom_template_and_always_appends_data():
    ctx = build_context(
        {}, {}, _constraints(), objectives_from_config({}), valid_from="A", valid_until="B"
    )
    prompt = build_prompt(ctx, "MEIN EIGENER PROMPT")
    assert prompt.startswith("MEIN EIGENER PROMPT")
    assert "Orchestrator" not in prompt  # Default-Text ersetzt
    assert "Daten:" in prompt  # Datenblock wird IMMER angehängt
    assert "heizstab" in prompt


def test_build_prompt_blank_template_falls_back_to_default():
    ctx = build_context(
        {}, {}, _constraints(), objectives_from_config({}), valid_from="A", valid_until="B"
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
        {}, {}, _constraints(), objectives_from_config({}),
        valid_from="A", valid_until="B",
        weather=_weather_snapshot(4), horizon_h=24, weather_detail="full",
    )
    assert ctx["weather"]["detail"] == "full"
    assert len(ctx["weather"]["slots"]) == 4


def _onecall_snapshot(llm_timeline="1h", n_15min=12, n_1h=30, n_1day=8):
    # OneCallCollector.snapshot()-Form: timelines je Auflösung mit slots[].
    def slot(i, daily=False):
        d = {"time": f"t{i}", "temp": 20.0 + i, "clouds": 10.0, "pop": 0.1}
        if daily:
            d["temp_min"] = 10.0 + i
            d["temp_max"] = 25.0 + i
        return d

    return {
        "enabled": True,
        "source": "onecall",
        "units": "metric",
        "llm_timeline": llm_timeline,
        "timelines": {
            "15min": {"enabled": True, "slots": [slot(i) for i in range(n_15min)]},
            "1h": {"enabled": True, "slots": [slot(i) for i in range(n_1h)]},
            "1day": {"enabled": True, "slots": [slot(i, daily=True) for i in range(n_1day)]},
        },
    }


def test_condense_weather_onecall_1h_trims_to_horizon():
    out = _condense_weather(_onecall_snapshot("1h"), horizon_h=24, detail="compact")
    assert out["source"] == "onecall"
    assert out["timeline"] == "1h"
    assert len(out["slots"]) == 24  # 24 h / 1-h-Schritte
    assert set(out["slots"][0].keys()) == {"time", "temp", "clouds", "pop"}


def test_condense_weather_onecall_15min_trims_to_horizon():
    out = _condense_weather(_onecall_snapshot("15min"), horizon_h=2, detail="compact")
    assert out["timeline"] == "15min"
    assert len(out["slots"]) == 8  # 2 h * 60 / 15 min


def test_condense_weather_onecall_1day_full_with_minmax():
    out = _condense_weather(_onecall_snapshot("1day"), horizon_h=24, detail="compact")
    assert out["timeline"] == "1day"
    assert len(out["slots"]) == 8  # Tages-Timeline wird nicht gekürzt
    assert "temp_min" in out["slots"][0]
    assert "temp_max" in out["slots"][0]


def test_condense_weather_onecall_empty_timeline():
    snap = _onecall_snapshot("1h", n_1h=0)
    assert _condense_weather(snap, horizon_h=24, detail="compact") == {}


def test_build_context_includes_onecall_weather():
    ctx = build_context(
        {}, {}, _constraints(), objectives_from_config({}),
        valid_from="A", valid_until="B",
        weather=_onecall_snapshot("1day"), horizon_h=24,
    )
    assert ctx["weather"]["source"] == "onecall"
    assert ctx["weather"]["timeline"] == "1day"
