"""Tests für das Wetter-Config-Parsing und die Normalisierungs-Dataclasses."""

from energy_pilot.weather import (
    DEFAULT_REFRESH_MIN,
    DEFAULT_ZONE_ENTITY,
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
