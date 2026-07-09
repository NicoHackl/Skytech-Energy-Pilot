"""Tests für das Wetter-Config-Parsing und die Normalisierungs-Dataclasses."""

from energy_pilot.weather import (
    DEFAULT_REFRESH_MIN,
    DEFAULT_SOURCE,
    DEFAULT_ZONE_ENTITY,
    OneCallSlot,
    WeatherSlot,
    weather_config_from_options,
)


def test_defaults_when_no_weather_option():
    cfg = weather_config_from_options({})
    assert cfg.api_key == ""
    assert cfg.enabled is False
    assert cfg.zone_entity == DEFAULT_ZONE_ENTITY
    assert cfg.units == "metric"
    assert cfg.lang == "de"
    assert cfg.refresh_min == DEFAULT_REFRESH_MIN


def test_parses_values_and_enabled_with_key():
    cfg = weather_config_from_options(
        {
            "weather": {
                "api_key": "  secret  ",
                "zone_entity": "zone.ferienhaus",
                "units": "imperial",
                "lang": "en",
                "refresh_min": 15,
            }
        }
    )
    assert cfg.api_key == "secret"  # getrimmt
    assert cfg.enabled is True
    assert cfg.zone_entity == "zone.ferienhaus"
    assert cfg.units == "imperial"
    assert cfg.lang == "en"
    assert cfg.refresh_min == 15


def test_llm_detail_default_and_parsing():
    assert weather_config_from_options({}).llm_detail == "compact"
    full = weather_config_from_options({"weather": {"llm_detail": "FULL"}})
    assert full.llm_detail == "full"  # normalisiert auf Kleinschreibung
    # Ungültiger Wert fällt auf den Default zurück.
    assert weather_config_from_options({"weather": {"llm_detail": "xxl"}}).llm_detail == "compact"


def test_invalid_refresh_falls_back_to_default():
    cfg = weather_config_from_options({"weather": {"refresh_min": "abc"}})
    assert cfg.refresh_min == DEFAULT_REFRESH_MIN
    cfg2 = weather_config_from_options({"weather": {"refresh_min": 0}})
    assert cfg2.refresh_min == DEFAULT_REFRESH_MIN


def test_non_dict_weather_option_ignored():
    cfg = weather_config_from_options({"weather": "kaputt"})
    assert cfg.zone_entity == DEFAULT_ZONE_ENTITY
    assert cfg.enabled is False


def test_slot_as_dict_roundtrip():
    slot = WeatherSlot(
        dt=1, time="2026-06-25 12:00:00", temp=20.0, feels_like=19.0, clouds=40.0,
        pop=0.2, wind_speed=3.0, humidity=55.0, rain_3h=None, snow_3h=None,
        condition="leicht bewölkt", condition_id=802,
    )
    d = slot.as_dict()
    assert d["temp"] == 20.0
    assert d["clouds"] == 40.0
    assert d["pop"] == 0.2
    assert d["condition_id"] == 802


def test_source_default_and_parsing():
    assert weather_config_from_options({}).source == DEFAULT_SOURCE == "forecast3h"
    assert weather_config_from_options({"weather": {"source": "onecall"}}).source == "onecall"
    # Ungültiger Wert fällt auf den Default zurück.
    assert weather_config_from_options({"weather": {"source": "xyz"}}).source == "forecast3h"


def test_default_refresh_min_is_sixty():
    # W3/D-044: forecast3h-Default ist 60 Minuten.
    assert DEFAULT_REFRESH_MIN == 60
    assert weather_config_from_options({}).refresh_min == 60


def test_onecall_config_defaults():
    oc = weather_config_from_options({}).onecall
    assert oc.enable_15min is False
    assert oc.enable_1h is True
    assert oc.enable_1day is True
    assert oc.refresh_15min == 15
    assert oc.refresh_1h == 60
    assert oc.refresh_1day == 180
    # Aktive Modelle = die ans LLM gehende Kombination (D-054, kein Einzel-Select mehr).
    assert oc.enabled_timelines == ("1h", "1day")


def test_onecall_config_overrides_and_validation():
    oc = weather_config_from_options(
        {
            "weather": {
                "onecall": {
                    "enable_15min": True,
                    "enable_1h": False,
                    "refresh_15min": 5,
                    "refresh_1day": 0,  # ungültig (<1) → Default 180
                }
            }
        }
    ).onecall
    assert oc.enable_15min is True
    assert oc.enable_1h is False
    assert oc.refresh_15min == 5
    assert oc.refresh_1day == 180
    # Beliebige Kombination: hier 15min + 1day aktiv.
    assert oc.enabled_timelines == ("15min", "1day")
    assert oc.is_enabled("1h") is False
    assert oc.refresh_for("15min") == 5


def test_onecall_pages_defaults_and_clamping():
    # Default: 1 Seite je Timeline (erste Seite, O2).
    oc = weather_config_from_options({}).onecall
    assert oc.pages_for("1h") == 1
    assert oc.pages_for("15min") == 1
    assert oc.pages_for("1day") == 1
    # 1–5 clamping: <1 → 1, >5 → 5, ungültig → Default 1.
    oc2 = weather_config_from_options(
        {"weather": {"onecall": {"pages_15min": 0, "pages_1h": 9, "pages_1day": "x"}}}
    ).onecall
    assert oc2.pages_for("15min") == 1
    assert oc2.pages_for("1h") == 5
    assert oc2.pages_for("1day") == 1


def test_onecall_daily_call_budget_default_and_parsing():
    assert weather_config_from_options({}).onecall.daily_call_budget == 1000
    oc = weather_config_from_options({"weather": {"onecall": {"daily_call_budget": 250}}}).onecall
    assert oc.daily_call_budget == 250
    # Ungültig/<1 → Default 1000.
    assert weather_config_from_options(
        {"weather": {"onecall": {"daily_call_budget": 0}}}
    ).onecall.daily_call_budget == 1000
    assert weather_config_from_options(
        {"weather": {"onecall": {"daily_call_budget": "abc"}}}
    ).onecall.daily_call_budget == 1000


def test_onecall_alerts_defaults_and_parsing():
    oc = weather_config_from_options({}).onecall
    assert oc.enable_alerts is True  # O3: standardmäßig an
    assert oc.refresh_alerts == 30
    oc2 = weather_config_from_options(
        {"weather": {"onecall": {"enable_alerts": False, "refresh_alerts": 90}}}
    ).onecall
    assert oc2.enable_alerts is False
    assert oc2.refresh_alerts == 90


def test_onecall_alert_as_dict_roundtrip():
    from energy_pilot.weather import OneCallAlert
    alert = OneCallAlert(
        sender_name="DWD", event="Sturm", start=100, end=200,
        description="Sturmböen", tags=["Wind", "Sturm"],
    )
    d = alert.as_dict()
    assert d["sender_name"] == "DWD"
    assert d["event"] == "Sturm"
    assert d["start"] == 100
    assert d["tags"] == ["Wind", "Sturm"]


def test_onecall_slot_as_dict_roundtrip():
    slot = OneCallSlot(
        dt=1, time="2026-06-25 12:00", temp=25.0, feels_like=24.5, temp_min=14.0,
        temp_max=27.0, clouds=20.0, pop=0.2, wind_speed=3.0, humidity=55.0,
        rain=2.5, snow=None, condition="leicht bewölkt", condition_id=802,
    )
    d = slot.as_dict()
    assert d["temp"] == 25.0
    assert d["temp_min"] == 14.0
    assert d["temp_max"] == 27.0
    assert d["rain"] == 2.5
