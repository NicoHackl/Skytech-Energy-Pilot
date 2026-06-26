"""Tests für den One-Call-4.0-Client (Fake-Session, keine echte Verbindung)."""

import pytest

from energy_pilot.onecall_client import OneCallClient, parse_alerts, parse_timeline
from energy_pilot.weather_client import WeatherClientError


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


def _onecall_1h_payload():
    return {
        "lat": 48.2,
        "lon": 16.3,
        "timezone": "Europe/Vienna",
        "timezone_offset": 7200,
        "data": [
            {
                "dt": 1719316800,
                "temp": 24.5,
                "feels_like": 24.0,
                "humidity": 50,
                "clouds": 5,
                "wind_speed": 3.2,
                "wind_deg": 180,
                "pop": 0.1,
                "rain": {"1h": 0.0},
                "weather": [{"id": 800, "main": "Clear", "description": "klarer Himmel"}],
            },
            {
                "dt": 1719320400,
                "temp": 22.0,
                "feels_like": 21.5,
                "humidity": 60,
                "clouds": 75,
                "wind_speed": 4.0,
                "pop": 0.8,
                "rain": {"1h": 1.4},
                "weather": [{"id": 500, "main": "Rain", "description": "leichter Regen"}],
            },
        ],
        "next": "https://api.openweathermap.org/data/4.0/onecall/timeline/1h?start=1719320400",
    }


def _onecall_1day_payload():
    return {
        "lat": 48.2,
        "lon": 16.3,
        "timezone_offset": 7200,
        "data": [
            {
                "dt": 1719273600,
                "temp": {"day": 25.0, "min": 14.0, "max": 27.0, "night": 16.0},
                "feels_like": {"day": 24.5},
                "humidity": 55,
                "clouds": 20,
                "pop": 0.2,
                "wind_speed": 3.0,
                "rain": 2.5,  # Tagesmenge als Zahl (nicht {"1h": …})
                "weather": [{"id": 802, "description": "leicht bewölkt"}],
            }
        ],
    }


def test_parse_timeline_1h_normalizes_point_values():
    tl = parse_timeline("1h", _onecall_1h_payload())
    assert tl.resolution == "1h"
    assert tl.lat == 48.2
    assert tl.timezone_offset_s == 7200
    assert len(tl.slots) == 2
    s0, s1 = tl.slots
    assert s0.temp == 24.5
    assert s0.temp_min is None and s0.temp_max is None  # nur daily
    assert s0.clouds == 5.0
    assert s0.condition == "klarer Himmel"
    assert s0.condition_id == 800
    assert s1.rain == 1.4
    assert s1.pop == 0.8
    assert s0.time  # ISO-Zeit aus dt abgeleitet


def test_parse_timeline_1day_extracts_temp_min_max_and_daily_rain():
    tl = parse_timeline("1day", _onecall_1day_payload())
    assert tl.resolution == "1day"
    s = tl.slots[0]
    assert s.temp == 25.0  # temp.day
    assert s.temp_min == 14.0
    assert s.temp_max == 27.0
    assert s.feels_like == 24.5  # feels_like.day
    assert s.rain == 2.5  # Tagesmenge als Zahl
    assert s.condition == "leicht bewölkt"


def test_parse_timeline_handles_missing_optional_blocks():
    tl = parse_timeline("15min", {"data": [{"dt": 1, "temp": 10}]})
    assert tl.lat is None
    s = tl.slots[0]
    assert s.temp == 10.0
    assert s.clouds is None
    assert s.condition is None
    assert s.rain is None


async def test_fetch_timeline_sends_key_as_param_not_in_url():
    session = _FakeSession(_FakeResponse(payload=_onecall_1h_payload()))
    client = OneCallClient("secret-key", units="metric", lang="de", session=session)

    tl, calls = await client.fetch_timeline("1h", 48.2, 16.3)

    assert calls == 1  # Default max_calls=1 → nur die erste Seite (trotz `next`)
    assert len(tl.slots) == 2
    call = session.calls[0]
    assert call["url"].endswith("/timeline/1h")
    assert call["params"]["appid"] == "secret-key"
    assert "secret-key" not in call["url"]
    assert call["params"]["lat"] == "48.2"
    assert call["params"]["units"] == "metric"


async def test_fetch_timeline_paginates_following_next_up_to_max_calls():
    # Das Payload trägt immer einen `next`-Link → bis max_calls Seiten werden geholt.
    session = _FakeSession(_FakeResponse(payload=_onecall_1h_payload()))
    client = OneCallClient("secret-key", session=session)

    tl, calls = await client.fetch_timeline("1h", 48.2, 16.3, max_calls=3)

    assert calls == 3
    assert len(tl.slots) == 6  # 2 Slots je Seite × 3 Seiten
    assert len(session.calls) == 3
    for c in session.calls:  # Schlüssel nie in der URL, immer als appid-Param (Iron Rule 6)
        assert "secret-key" not in c["url"]
        assert c["params"]["appid"] == "secret-key"


async def test_fetch_timeline_stops_when_no_next_link():
    payload = _onecall_1h_payload()
    payload.pop("next")
    session = _FakeSession(_FakeResponse(payload=payload))
    client = OneCallClient("k", session=session)

    tl, calls = await client.fetch_timeline("1h", 1.0, 2.0, max_calls=5)

    assert calls == 1  # keine Folgeseite vorhanden → früher Stopp trotz max_calls=5
    assert len(tl.slots) == 2


async def test_fetch_timeline_unknown_resolution_raises():
    client = OneCallClient("k", session=_FakeSession(_FakeResponse(payload={"data": []})))
    with pytest.raises(WeatherClientError):
        await client.fetch_timeline("5min", 1.0, 2.0)


async def test_fetch_timeline_invalid_key_surfaces_owm_message():
    body = '{"cod":401,"message":"Invalid API key."}'
    session = _FakeSession(_FakeResponse(status=401, text=body))
    client = OneCallClient("bad-key", session=session)
    with pytest.raises(WeatherClientError) as exc:
        await client.fetch_timeline("1h", 1.0, 2.0)
    msg = str(exc.value)
    assert "401" in msg
    assert "Invalid API key" in msg
    assert "bad-key" not in msg  # Schlüssel nie in der Meldung (Iron Rule 6)


async def test_fetch_timeline_rate_limit_raises():
    session = _FakeSession(_FakeResponse(status=429, text="quota"))
    client = OneCallClient("k", session=session)
    with pytest.raises(WeatherClientError) as exc:
        await client.fetch_timeline("15min", 1.0, 2.0)
    assert "429" in str(exc.value)


def test_masked_request_url_hides_key():
    client = OneCallClient("super-secret", units="metric", lang="de")
    url = client.masked_request_url("15min", 48.2, 16.3)
    assert url.endswith("/timeline/15min?lat=48.2&lon=16.3&appid=***&units=metric&lang=de")
    assert "super-secret" not in url


# --- Unwetter-Alerts (O3) --------------------------------------------------------------------

def test_parse_alerts_normalizes_entries_and_skips_garbage():
    payload = {
        "alerts": [
            {"sender_name": "DWD", "event": "Sturm", "start": 100, "end": 200,
             "description": "Sturmböen", "tags": ["Wind"]},
            "kein-dict",  # wird übersprungen
            {"event": "Hitzewarnung"},  # fehlende Felder → None/[]
        ]
    }
    alerts = parse_alerts(payload)
    assert len(alerts) == 2
    assert alerts[0].sender_name == "DWD"
    assert alerts[0].start == 100
    assert alerts[0].tags == ["Wind"]
    assert alerts[1].event == "Hitzewarnung"
    assert alerts[1].sender_name is None
    assert alerts[1].tags == []


def test_parse_alerts_missing_list_returns_empty():
    assert parse_alerts({}) == []
    assert parse_alerts({"alerts": None}) == []


async def test_fetch_alerts_returns_normalized_list_with_masked_key():
    payload = {"alerts": [{"event": "Sturm", "start": 1, "end": 2, "tags": ["Wind"]}]}
    session = _FakeSession(_FakeResponse(payload=payload))
    client = OneCallClient("secret", session=session)

    alerts = await client.fetch_alerts(48.2, 16.3)

    assert len(alerts) == 1
    assert alerts[0].event == "Sturm"
    call = session.calls[0]
    assert call["url"].endswith("/alert")
    assert call["params"]["appid"] == "secret"
    assert "secret" not in call["url"]


def test_masked_alert_url_hides_key():
    client = OneCallClient("super-secret", units="metric", lang="de")
    url = client.masked_alert_url(48.2, 16.3)
    assert url.endswith("/alert?lat=48.2&lon=16.3&appid=***&units=metric&lang=de")
    assert "super-secret" not in url
