"""Tests für das lokale Plan-Sicherheits-Gate (Validator, Stufen 1–3)."""

from datetime import UTC, datetime

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import BINARY, CONTROLLABLE, Device, DeviceExtra
from energy_pilot.validator import validate

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)

# Heizstab mit aktivierter Zusatz-Entität (D-047) – erzeugt das Feld
# `extra_heizstab_max_temperatur_vorschlag` im Schreibvertrag (ersetzt den Hardcode D-035).
_HEIZSTAB_EXTRA = DeviceExtra(
    read_entity_id="input_number.ep_heizstab_max_temperatur", ai_suggestion=True, unit="°C"
)


def _constraints():
    devices = [
        Device("batterie", "Batterie", "batterie", CONTROLLABLE, "watt"),
        Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt", extras=(_HEIZSTAB_EXTRA,)),
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
            "extra_heizstab_max_temperatur": {"value": 60.0},
        },
        "heizluefter_1": {"technische_freigabe": {"value": False}, "leistung_w": {"value": 1500.0}},
    }
    return build_constraints(devices, readings)


def _plan(devices, **overrides):
    base = {
        "schema_version": "1.0",
        "plan_id": "p1",
        "valid_from": "2026-06-19T12:00:00+00:00",
        "valid_until": "2026-06-19T13:00:00+00:00",
        "provider": "gemini",
        "model": "gemini-3.5-flash",
        "confidence": 80,
        "reasoning": "",
        "warnings": [],
        "devices": devices,
    }
    base.update(overrides)
    return base


def _surplus_heater_constraints():
    hard_limit = DeviceExtra(
        read_entity_id="input_number.e3dc_heizstab_maxtemperatur",
        rolle="grenze",
        label="Maximaltemperatur",
        unit="°C",
    )
    device = Device(
        "heizstab",
        "Heizstab",
        "heizstab",
        CONTROLLABLE,
        "watt",
        control_policy="pv_surplus_only",
        extras=(hard_limit,),
    )
    readings = {
        "heizstab": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 500.0},
            "max_technisch": {"value": 3000.0},
            hard_limit.read_key: {"value": 85.0},
        }
    }
    return build_constraints([device], readings)


def _heater_plan(enabled: bool, reason: str, factors=None):
    return _plan(
        [
            {
                "name": "heizstab",
                "prio_vorschlag": 10,
                "freigabe_vorschlag": enabled,
                "geschutzte_mindestleistung_w_vorschlag": 500.0,
                "begruendung": reason,
                "angewandte_regeln": [],
                "entscheidungsfaktoren": factors or ["komfortreserve"],
            }
        ]
    )


def _thermal_context(
    *, current=65.0, target=75.0, need=3.0, proxy=None, quality="unbekannt",
    reserve_after=None,
):
    return {
        "state": [{"role": "hot_water_temp", "latest": current}],
        "merkmale": {
            "geraete": [
                {
                    "name": "heizstab",
                    "ziel_c": target,
                    "volumen_liter": 300.0,
                    "energiebedarf_kwh": need,
                    "solarthermie_proxy_kwh": proxy,
                    "solarthermie_proxy_datenqualitaet": quality,
                    "reserve_nach_horizont_kwh": reserve_after,
                }
            ]
        },
    }


def test_grid_import_is_not_a_valid_shutdown_reason_for_surplus_device():
    result = validate(
        _heater_plan(False, "Ausschalten, um den Netzbezug zu reduzieren."),
        _surplus_heater_constraints(),
        now=NOW,
        context=_thermal_context(),
    )
    assert not result.ok
    assert any("Netzbezug" in error for error in result.errors)


def test_too_hot_reason_is_rejected_below_target_and_hard_limit():
    result = validate(
        _heater_plan(False, "Der Speicher ist mit 65 °C zu heiß."),
        _surplus_heater_constraints(),
        now=NOW,
        context=_thermal_context(current=65.0, target=75.0),
    )
    assert not result.ok
    assert any("numerisch nicht belegt" in error for error in result.errors)


def test_sunny_replay_blocks_electric_release_when_proxy_covers_demand():
    context = _thermal_context(need=2.0, proxy=3.0, quality="mittel", reserve_after=1.0)
    result = validate(
        _heater_plan(
            True,
            "Erwartete Nettowärme 3 kWh deckt 2 kWh Bedarf.",
            ["solarthermie_proxy"],
        ),
        _surplus_heater_constraints(),
        now=NOW,
        context=context,
    )
    assert not result.ok
    assert any("elektrische Freigabe" in error for error in result.errors)


def test_cloudy_replay_requires_release_for_safe_pv_surplus_buffering():
    context = _thermal_context(need=2.0, proxy=0.0, quality="mittel", reserve_after=-1.0)
    result = validate(
        _heater_plan(False, "Es fehlt 3 kWh Wärme, kein Proxy-Ertrag erwartet."),
        _surplus_heater_constraints(),
        now=NOW,
        context=context,
    )
    assert not result.ok
    assert any("freigegeben bleiben" in error for error in result.errors)


def test_happy_path_ok_without_clamps():
    # Vollständiger Plan für ALLE erkannten Geräte (D-050): fehlt keines und keins ein
    # Pflichtfeld, füllt/klemmt der Validator nichts.
    plan = _plan(
        [
            {
                "name": "heizstab",
                "prio_vorschlag": 10,  # Rang 1 -> bleibt 10 (unverändert)
                "freigabe_vorschlag": True,
                "geschutzte_mindestleistung_w_vorschlag": 800.0,
                "extra_heizstab_max_temperatur_vorschlag": 55.0,
            },
            {"name": "heizluefter_1", "prio_vorschlag": 20, "freigabe_vorschlag": False},
            {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
        ]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    assert result.clamped == []
    assert result.errors == []


def test_protected_min_power_is_clamped_not_rejected():
    plan = _plan(
        [{"name": "heizstab", "prio_vorschlag": 1, "freigabe_vorschlag": True,
          "geschutzte_mindestleistung_w_vorschlag": 9000.0}]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok  # geklemmt, nicht abgelehnt
    assert result.normalized_plan["devices"][0]["geschutzte_mindestleistung_w_vorschlag"] == 3000.0
    assert result.clamped


def test_extra_suggestion_passes_through_unclamped():
    # Zusatz-Vorschläge (D-047) sind advisorisch (nur HA-Sensor) und werden NICHT geklemmt.
    plan = _plan(
        [{"name": "heizstab", "prio_vorschlag": 1, "freigabe_vorschlag": True,
          "geschutzte_mindestleistung_w_vorschlag": 600.0,
          "extra_heizstab_max_temperatur_vorschlag": 99.0}]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    assert result.normalized_plan["devices"][0]["extra_heizstab_max_temperatur_vorschlag"] == 99.0
    assert not any("max_temperatur" in c for c in result.clamped)


def test_input_number_extra_clamped_to_attr_bounds():
    # input_number-Zusatz (D-048): Vorschlag wird auf den min/max-Bereich der Quelle geklemmt.
    ex = DeviceExtra(read_entity_id="input_number.min_soc", ai_suggestion=True)
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, "ampere", extras=(ex,))
    readings = {"wallbox": {"extra_min_soc": {"value": 20.0, "attrs": {"min": 0, "max": 100}}}}
    cons = build_constraints([dev], readings)
    plan = _plan([{"name": "wallbox", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                   "extra_min_soc_vorschlag": 150.0}])
    result = validate(plan, cons, now=NOW)
    assert result.ok
    assert result.normalized_plan["devices"][0]["extra_min_soc_vorschlag"] == 100.0
    assert any("extra_min_soc_vorschlag" in c for c in result.clamped)


def test_datetime_extra_string_passes_through():
    # input_datetime-Zusatz: String-Vorschlag wird unverändert durchgereicht (kein Klemmen).
    ex = DeviceExtra(read_entity_id="input_datetime.abfahrt", ai_suggestion=True)
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, "ampere", extras=(ex,))
    readings = {"wallbox": {"extra_abfahrt": {"value": "2026-07-02 07:00:00",
                                              "attrs": {"has_date": True, "has_time": True}}}}
    cons = build_constraints([dev], readings)
    plan = _plan([{"name": "wallbox", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                   "extra_abfahrt_vorschlag": "2026-07-02 08:30:00"}])
    result = validate(plan, cons, now=NOW)
    assert result.ok
    assert result.normalized_plan["devices"][0]["extra_abfahrt_vorschlag"] == "2026-07-02 08:30:00"


def _select_constraints():
    ex = DeviceExtra(read_entity_id="input_select.lademodus", ai_suggestion=True)
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, "ampere", extras=(ex,))
    readings = {"wallbox": {"extra_lademodus": {
        "value": "Aus", "attrs": {"options": ["Aus", "PV-Überschuss", "Schnell"]}}}}
    return build_constraints([dev], readings)


def test_input_select_valid_option_passes():
    plan = _plan([{"name": "wallbox", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                   "geschutzte_mindestleistung_a_vorschlag": 0.0,
                   "extra_lademodus_vorschlag": "Schnell"}])
    result = validate(plan, _select_constraints(), now=NOW)
    assert result.ok
    assert result.normalized_plan["devices"][0]["extra_lademodus_vorschlag"] == "Schnell"
    assert result.clamped == []


def test_input_select_out_of_pool_value_dropped():
    # Wert außerhalb des Auswahlpools (D-049): wird verworfen, Plan bleibt gültig (advisorisch).
    plan = _plan([{"name": "wallbox", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                   "extra_lademodus_vorschlag": "Turbo"}])
    result = validate(plan, _select_constraints(), now=NOW)
    assert result.ok
    assert "extra_lademodus_vorschlag" not in result.normalized_plan["devices"][0]
    assert any("Wertepool" in c for c in result.clamped)


def test_unknown_extra_field_rejected_by_write_contract():
    # Ein `extra_*_vorschlag` ohne aktivierte Zusatz-Entität ist nicht im Schreibvertrag.
    plan = _plan(
        [{"name": "heizstab", "prio_vorschlag": 1, "freigabe_vorschlag": True,
          "extra_unbekannt_vorschlag": 5.0}]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("Schreibvertrag" in e for e in result.errors)


def test_freigabe_true_despite_current_technical_block_allowed():
    # D-054: `technische_freigabe=false` ist nur der AKTUELLE Ist-Zustand, kein Verbot fuer
    # den gesamten Planzeitraum. heizluefter_1 ist in _constraints() aktuell gesperrt
    # (technische_freigabe=False, Zeile 36), der Plan darf ihn trotzdem freigeben.
    plan = _plan([{"name": "heizluefter_1", "prio_vorschlag": 3, "freigabe_vorschlag": True}])
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok


def test_write_contract_violation_rejected():
    # Batterie darf keine Priorität vorschlagen (D-037).
    device = {
        "name": "batterie",
        "prio_vorschlag": 1,
        "geschutzte_mindestleistung_w_vorschlag": 1000.0,
    }
    result = validate(_plan([device]), _constraints(), now=NOW)
    assert not result.ok
    assert any("Schreibvertrag" in e for e in result.errors)


def test_unknown_device_rejected():
    plan = _plan([{"name": "spuelmaschine", "prio_vorschlag": 1, "freigabe_vorschlag": True}])
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("unbekannt" in e.lower() for e in result.errors)


def test_expired_plan_rejected():
    plan = _plan(
        [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}],
        valid_from="2026-06-19T08:00:00+00:00",
        valid_until="2026-06-19T09:00:00+00:00",
    )
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("abgelaufen" in e for e in result.errors)


def test_invalid_time_order_rejected():
    plan = _plan(
        [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}],
        valid_from="2026-06-19T14:00:00+00:00",
        valid_until="2026-06-19T15:00:00+00:00",
    )
    # valid_until liegt in der Zukunft (nicht abgelaufen), aber start < end ist verletzt:
    plan["valid_until"] = "2026-06-19T13:30:00+00:00"
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert any("valid_from muss vor valid_until" in e for e in result.errors)


def test_schema_failure_returns_no_normalized_plan():
    plan = _plan([{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}])
    del plan["devices"]
    result = validate(plan, _constraints(), now=NOW)
    assert not result.ok
    assert result.normalized_plan is None


def test_naive_timestamps_treated_as_utc():
    plan = _plan(
        [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 1000.0}],
        valid_from="2026-06-19T12:00:00",
        valid_until="2026-06-19T13:00:00",
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok


def _ranked_constraints():
    # Drei freigegebene Prio-Geräte (keine Batterie), um die Rangfolge zu prüfen.
    devices = [
        Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt"),
        Device("heizluefter_1", "Heizlüfter 1", "heizluefter_1", BINARY, "watt"),
        Device("heizluefter_2", "Heizlüfter 2", "heizluefter_2", BINARY, "watt"),
    ]
    readings = {
        "heizstab": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 500.0},
            "max_technisch": {"value": 3000.0},
            "ep_max_temperatur": {"value": 60.0},
        },
        "heizluefter_1": {"technische_freigabe": {"value": True}, "leistung_w": {"value": 1500.0}},
        "heizluefter_2": {"technische_freigabe": {"value": True}, "leistung_w": {"value": 1500.0}},
    }
    return build_constraints(devices, readings)


def test_priorities_normalized_to_strict_ranking():
    # KI liefert unsaubere Prios (Duplikate, Lücken, >100); EP kanonisiert auf 10/20/30
    # in relativer Reihenfolge und klemmt – statt den Plan abzulehnen.
    # Alle Pflichtfelder gesetzt, damit nur die Prio-Neuvergabe klemmt (keine Fallback-Füllung).
    plan = _plan(
        [
            {"name": "heizstab", "prio_vorschlag": 90, "freigabe_vorschlag": True,
             "geschutzte_mindestleistung_w_vorschlag": 1000.0},
            {"name": "heizluefter_1", "prio_vorschlag": 5, "freigabe_vorschlag": True},
            {"name": "heizluefter_2", "prio_vorschlag": 5, "freigabe_vorschlag": True},
        ]
    )
    result = validate(plan, _ranked_constraints(), now=NOW)
    assert result.ok
    prios = {d["name"]: d["prio_vorschlag"] for d in result.normalized_plan["devices"]}
    # Sortierung (Prio, Index): lüfter1(5,1)->10, lüfter2(5,2)->20, heizstab(90,0)->30
    assert prios == {"heizluefter_1": 10, "heizluefter_2": 20, "heizstab": 30}
    assert len(result.clamped) == 3


def test_missing_contract_fields_filled_from_state():
    # D-050: fehlt dem Modell ein Pflichtfeld (hier freigabe + Max-Wassertemperatur des
    # Heizstabs), füllt EP es deterministisch aus dem Ist-Zustand statt es zu übergehen.
    plan = _plan(
        [
            {"name": "heizstab", "prio_vorschlag": 10,
             "geschutzte_mindestleistung_w_vorschlag": 800.0},
            {"name": "heizluefter_1", "prio_vorschlag": 20, "freigabe_vorschlag": False},
            {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
        ]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    heizstab = next(d for d in result.normalized_plan["devices"] if d["name"] == "heizstab")
    # freigabe aus der aktuellen technischen Freigabe (True), Max-Temp aus dem Lesewert (60.0).
    assert heizstab["freigabe_vorschlag"] is True
    assert heizstab["extra_heizstab_max_temperatur_vorschlag"] == 60.0
    assert any("freigabe_vorschlag: fehlt" in c for c in result.clamped)
    assert any("max_temperatur_vorschlag: fehlt" in c for c in result.clamped)


def test_missing_device_is_appended_and_filled():
    # D-050: ein vom Modell ganz ausgelassenes Gerät wird ergänzt und vollständig gefüllt,
    # statt lautlos aus dem Plan zu verschwinden ("mal nur manche Geräte").
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                   "geschutzte_mindestleistung_w_vorschlag": 800.0,
                   "extra_heizstab_max_temperatur_vorschlag": 55.0}])
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    names = {d["name"] for d in result.normalized_plan["devices"]}
    assert names == {"heizstab", "heizluefter_1", "batterie"}
    heizluefter = next(d for d in result.normalized_plan["devices"] if d["name"] == "heizluefter_1")
    # Binärlast: freigabe aus Ist-Zustand (False = gesperrt), Prio ans Ende gereiht.
    assert heizluefter["freigabe_vorschlag"] is False
    assert heizluefter["prio_vorschlag"] == 20
    assert any("Gerät fehlte" in c for c in result.clamped)


def test_missing_priority_ranked_last_deterministically():
    # D-050: fehlt ein Prio-Wert, wird das Gerät ans Ende der 10er-Rangfolge gestellt (statt das
    # Feld zu verlieren) – vorhandene Prios behalten Vorrang.
    plan = _plan(
        [
            {"name": "heizstab", "freigabe_vorschlag": True,
             "geschutzte_mindestleistung_w_vorschlag": 1000.0},  # Prio fehlt -> ans Ende
            {"name": "heizluefter_1", "prio_vorschlag": 5, "freigabe_vorschlag": True},
            {"name": "heizluefter_2", "prio_vorschlag": 8, "freigabe_vorschlag": True},
        ]
    )
    result = validate(plan, _ranked_constraints(), now=NOW)
    assert result.ok
    prios = {d["name"]: d["prio_vorschlag"] for d in result.normalized_plan["devices"]}
    assert prios == {"heizluefter_1": 10, "heizluefter_2": 20, "heizstab": 30}
    assert any("prio_vorschlag: fehlt" in c for c in result.clamped)


def test_battery_excluded_from_priority_ranking():
    # Batterie trägt keine Priorität (D-037) und darf die Rangfolge nicht stören;
    # das einzige echte Prio-Gerät erhält Rang 1 (= 10).
    plan = _plan(
        [
            {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
            {"name": "heizstab", "prio_vorschlag": 7},
        ]
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    devs = {d["name"]: d for d in result.normalized_plan["devices"]}
    assert "prio_vorschlag" not in devs["batterie"]
    assert devs["heizstab"]["prio_vorschlag"] == 10


# --- Konfidenz als Teilnoten, Gegenrechnung und Veröffentlichungs-Gate (D-064) ----------------


def _full_devices(**heizstab_extra):
    heizstab = {
        "name": "heizstab",
        "prio_vorschlag": 10,
        "freigabe_vorschlag": True,
        "geschutzte_mindestleistung_w_vorschlag": 800.0,
        "extra_heizstab_max_temperatur_vorschlag": 55.0,
    }
    heizstab.update(heizstab_extra)
    return [
        heizstab,
        {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
        {"name": "heizluefter_1", "prio_vorschlag": 20, "freigabe_vorschlag": False},
    ]


def _teilnoten_plan(parts, **overrides):
    return _plan(_full_devices(), konfidenz_teilnoten=parts, **overrides)


def test_confidence_aggregates_as_weakest_link():
    """Minimum statt Mittelwert: eine schwache Teilnote darf nicht wegrechenbar sein."""
    plan = _teilnoten_plan(
        {"datenlage": 90, "prognosesicherheit": 80, "regelklarheit": 40, "zielkonflikt": 70}
    )
    result = validate(plan, _constraints(), now=NOW)
    assert result.ok
    assert result.normalized_plan["confidence"] == 40


def test_confidence_gate_blocks_publishing_and_names_weakest_part():
    plan = _teilnoten_plan(
        {"datenlage": 90, "prognosesicherheit": 80, "regelklarheit": 40, "zielkonflikt": 70}
    )
    result = validate(plan, _constraints(), now=NOW, min_confidence=70)
    # Der Plan ist NICHT ungültig – er wird nur nicht wirksam.
    assert result.ok
    assert "40 %" in result.publish_blocked
    assert "70 %" in result.publish_blocked
    assert "regelklarheit" in result.publish_blocked


def test_confidence_gate_passes_when_above_threshold():
    plan = _teilnoten_plan(
        {"datenlage": 90, "prognosesicherheit": 80, "regelklarheit": 75, "zielkonflikt": 90}
    )
    result = validate(plan, _constraints(), now=NOW, min_confidence=70)
    assert result.publish_blocked is None
    assert result.normalized_plan["confidence"] == 75


def test_ep_measurement_caps_optimistic_datenlage_note():
    """Behauptet das Modell 90 bei 40 % veralteten Werten, gewinnt die EP-Messung."""
    plan = _teilnoten_plan(
        {"datenlage": 90, "prognosesicherheit": 95, "regelklarheit": 95, "zielkonflikt": 95}
    )
    context = {"datenlage": {"frische_prozent": 60, "fehlende_werte": ["pv_power"]}}
    result = validate(plan, _constraints(), now=NOW, context=context)
    assert result.normalized_plan["konfidenz_teilnoten"]["datenlage"] == 60
    assert result.normalized_plan["confidence"] == 60
    assert any("konfidenz.datenlage: 90 -> 60" in entry for entry in result.clamped)


def test_ep_measurement_does_not_raise_a_pessimistic_note():
    """Die Gegenrechnung deckelt nur – sie hebt eine ehrliche Selbsteinschätzung nie an."""
    plan = _teilnoten_plan(
        {"datenlage": 30, "prognosesicherheit": 95, "regelklarheit": 95, "zielkonflikt": 95}
    )
    context = {"datenlage": {"frische_prozent": 100, "fehlende_werte": []}}
    result = validate(plan, _constraints(), now=NOW, context=context)
    assert result.normalized_plan["konfidenz_teilnoten"]["datenlage"] == 30
    assert result.clamped == [] or not any("konfidenz" in c for c in result.clamped)


def test_unknown_confidence_keys_are_dropped():
    plan = _teilnoten_plan({"datenlage": 80, "erfunden": 5})
    result = validate(plan, _constraints(), now=NOW)
    assert result.normalized_plan["konfidenz_teilnoten"] == {"datenlage": 80}
    assert result.normalized_plan["confidence"] == 80


def test_flat_confidence_without_teilnoten_survives_unchanged():
    """Ältere Templates liefern nur eine Gesamtnote – Verhalten bleibt wie vorher."""
    result = validate(_plan(_full_devices(), confidence=55), _constraints(), now=NOW)
    assert result.normalized_plan["confidence"] == 55
    assert result.publish_blocked is None


def test_no_gate_without_threshold():
    plan = _teilnoten_plan({"datenlage": 5, "prognosesicherheit": 5,
                            "regelklarheit": 5, "zielkonflikt": 5})
    assert validate(plan, _constraints(), now=NOW).publish_blocked is None


def test_explanation_fields_are_not_a_contract_violation():
    """Begründung und angewandte Regeln sind Diagnose, kein Vorschlagswert (D-060)."""
    devices = _full_devices(
        begruendung="Warmwasser bei 76 °C, Regel greift.",
        angewandte_regeln=["Über 70 °C kein Heizstab"],
    )
    result = validate(_plan(devices), _constraints(), now=NOW)
    assert result.ok, result.errors
    entry = next(d for d in result.normalized_plan["devices"] if d["name"] == "heizstab")
    assert entry["begruendung"].startswith("Warmwasser")
    assert entry["angewandte_regeln"] == ["Über 70 °C kein Heizstab"]
