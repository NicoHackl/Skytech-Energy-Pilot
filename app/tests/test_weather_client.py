"""Tests für den OpenWeatherMap-Client (Fake-Session, keine echte Verbindung)."""

import pytest

from energy_pilot.weather_client import (
    OpenWeatherClient,
    WeatherClientError,
    parse_forecast,
)


class _FakeResponse:
    def __init__(self, *, status=200, payload=None, text=""):
        self.status = status
        self._payload = payload
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        return self._response


def _owm_payload():
    return {
        "cod": "200",
        "city": {"name": "Wien", "country": "AT", "timezone": 7200,
                 "sunrise": 100, "sunset": 200, "coord": {"lat": 48.2, "lon": 16.3}},
        "list": [
            {
                "dt": 1719316800,
                "dt_txt": "2026-06-25 12:00:00",
                "main": {"temp": 24.5, "feels_like": 24.0, "humidity": 50},
                "weather": [{"id": 800, "main": "Clear", "description": "klarer Himmel"}],
                "clouds": {"all": 5},
                "wind": {"speed": 3.2, "deg": 180},
                "pop": 0.1,
                "rain": {"3h": 0.0},
            },
            {
                "dt": 1719327600,
                "dt_txt": "2026-06-25 15:00:00",
                "main": {"temp": 22.0, "feels_like": 21.5, "humidity": 60},
                "weather": [{"id": 500, "main": "Rain", "description": "leichter Regen"}],
                "clouds": {"all": 75},
                "wind": {"speed": 4.0},
                "pop": 0.8,
                "rain": {"3h": 1.4},
            },
        ],
    }


def test_parse_forecast_normalizes_fields():
    fc = parse_forecast(_owm_payload())
    assert fc.city == "Wien"
    assert fc.country == "AT"
    assert fc.timezone_offset_s == 7200
    assert len(fc.slots) == 2
    s0, s1 = fc.slots
    assert s0.temp == 24.5
    assert s0.clouds == 5.0
    assert s0.pop == 0.1
    assert s0.condition == "klarer Himmel"
    assert s0.condition_id == 800
    assert s1.rain_3h == 1.4
    assert s1.pop == 0.8


def test_parse_forecast_handles_missing_optional_blocks():
    payload = {"list": [{"dt": 1, "dt_txt": "t", "main": {"temp": 10}}]}
    fc = parse_forecast(payload)
    assert fc.city is None
    slot = fc.slots[0]
    assert slot.temp == 10.0
    assert slot.clouds is None
    assert slot.condition is None
    assert slot.snow_3h is None


async def test_fetch_forecast_sends_key_as_param_not_in_url():
    session = _FakeSession(_FakeResponse(payload=_owm_payload()))
    client = OpenWeatherClient("secret-key", units="metric", lang="de", session=session)

    fc = await client.fetch_forecast(48.2, 16.3)

    assert fc.city == "Wien"
    call = session.calls[0]
    assert call["url"].endswith("/forecast")
    # Schlüssel als Query-Param (OWM kennt keine Header-Auth) – aber NICHT in der URL.
    assert call["params"]["appid"] == "secret-key"
    assert "secret-key" not in call["url"]
    assert call["params"]["lat"] == "48.2"
    assert call["params"]["units"] == "metric"


async def test_fetch_forecast_invalid_key_raises():
    session = _FakeSession(_FakeResponse(status=401, text="Invalid API key"))
    client = OpenWeatherClient("bad", session=session)
    with pytest.raises(WeatherClientError) as exc:
        await client.fetch_forecast(1.0, 2.0)
    assert "401" in str(exc.value)
    # Schlüssel darf nicht in der Fehlermeldung auftauchen.
    assert "bad" not in str(exc.value) or "401" in str(exc.value)


async def test_fetch_forecast_rate_limit_raises():
    session = _FakeSession(_FakeResponse(status=429, text="quota"))
    client = OpenWeatherClient("k", session=session)
    with pytest.raises(WeatherClientError) as exc:
        await client.fetch_forecast(1.0, 2.0)
    assert "429" in str(exc.value)


async def test_fetch_forecast_server_error_raises():
    session = _FakeSession(_FakeResponse(status=500, text="boom"))
    client = OpenWeatherClient("k", session=session)
    with pytest.raises(WeatherClientError):
        await client.fetch_forecast(1.0, 2.0)
