"""Tests für den Weather Collector (Fake-HA-Client + Fake-OWM-Client)."""

from energy_pilot.weather import WeatherConfig, WeatherForecast, WeatherSlot
from energy_pilot.weather_client import WeatherClientError
from energy_pilot.weather_collector import WeatherCollector


class _FakeHAClient:
    def __init__(self, state):
        self._state = state

    async def get_state(self, entity_id):
        if self._state is None:
            raise RuntimeError("not found")
        return self._state


class _FakeOWMClient:
    def __init__(self, forecast=None, error=None):
        self._forecast = forecast
        self._error = error
        self.calls = []

    async def fetch_forecast(self, lat, lon):
        self.calls.append((lat, lon))
        if self._error is not None:
            raise self._error
        return self._forecast


def _cfg(api_key="key", refresh_min=30):
    return WeatherConfig(
        api_key=api_key, zone_entity="zone.home", units="metric",
        lang="de", refresh_min=refresh_min,
    )


def _zone_state(lat=48.2, lon=16.3):
    attrs = {}
    if lat is not None:
        attrs["latitude"] = lat
    if lon is not None:
        attrs["longitude"] = lon
    return {"entity_id": "zone.home", "state": "zoning", "attributes": attrs}


def _forecast():
    return WeatherForecast(
        city="Wien", country="AT", timezone_offset_s=7200, sunrise=1, sunset=2,
        slots=[WeatherSlot(1, "t", 20.0, 19.0, 30.0, 0.1, 3.0, 50.0, None, None, "klar", 800)],
    )


async def test_disabled_without_api_key():
    collector = WeatherCollector(_FakeHAClient(_zone_state()), _cfg(api_key=""), None)
    assert collector.enabled is False
    await collector.collect_once(now=1000.0)
    assert collector.snapshot()["forecast"] is None


async def test_collect_resolves_zone_and_fetches():
    owm = _FakeOWMClient(forecast=_forecast())
    collector = WeatherCollector(_FakeHAClient(_zone_state()), _cfg(), owm)

    await collector.collect_once(now=1000.0)

    assert owm.calls == [(48.2, 16.3)]
    snap = collector.snapshot()
    assert snap["enabled"] is True
    assert snap["coords"] == {"lat": 48.2, "lon": 16.3}
    assert snap["forecast"]["city"] == "Wien"
    assert snap["last_error"] is None


async def test_refresh_guard_skips_recent_fetch():
    owm = _FakeOWMClient(forecast=_forecast())
    collector = WeatherCollector(_FakeHAClient(_zone_state()), _cfg(refresh_min=30), owm)

    await collector.collect_once(now=1000.0)
    await collector.collect_once(now=1000.0 + 60)  # < 30 min später → kein neuer Abruf
    assert len(owm.calls) == 1

    await collector.collect_once(now=1000.0 + 30 * 60 + 1)  # nach Ablauf → neuer Abruf
    assert len(owm.calls) == 2


async def test_missing_coordinates_no_fetch():
    owm = _FakeOWMClient(forecast=_forecast())
    collector = WeatherCollector(_FakeHAClient(_zone_state(lat=None)), _cfg(), owm)

    await collector.collect_once(now=1000.0)
    assert owm.calls == []
    assert "latitude" in (collector.last_error or "")


async def test_zone_read_error_no_fetch():
    owm = _FakeOWMClient(forecast=_forecast())
    collector = WeatherCollector(_FakeHAClient(None), _cfg(), owm)

    await collector.collect_once(now=1000.0)
    assert owm.calls == []
    assert collector.last_error is not None


async def test_fetch_error_recorded_no_crash():
    owm = _FakeOWMClient(error=WeatherClientError("HTTP 401"))
    collector = WeatherCollector(_FakeHAClient(_zone_state()), _cfg(), owm)

    await collector.collect_once(now=1000.0)
    snap = collector.snapshot()
    assert snap["forecast"] is None
    assert "401" in snap["last_error"]
    # Fehlerhafter Abruf setzt last_fetch_ts nicht → nächster Zyklus versucht es erneut.
    assert snap["last_fetch_ts"] is None
