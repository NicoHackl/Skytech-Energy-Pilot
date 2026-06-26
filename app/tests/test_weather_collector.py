"""Tests für den Weather Collector (Fake-HA-Client + Fake-OWM-Client)."""

from energy_pilot.weather import (
    OneCallConfig,
    OneCallSlot,
    OneCallTimeline,
    WeatherConfig,
    WeatherForecast,
    WeatherSlot,
)
from energy_pilot.weather_client import WeatherClientError
from energy_pilot.weather_collector import (
    OneCallCollector,
    WeatherCollector,
    resolve_zone_coords,
)


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

    def masked_request_url(self, lat, lon):
        return f"https://owm/forecast?lat={lat}&lon={lon}&appid=***&units=metric&lang=de"


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
    assert snap["source"] == "forecast3h"
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


async def test_test_fetch_success_bypasses_refresh_guard():
    owm = _FakeOWMClient(forecast=_forecast())
    collector = WeatherCollector(_FakeHAClient(_zone_state()), _cfg(refresh_min=30), owm)

    # Erster Abruf füllt last_fetch_ts; ein Live-Test ignoriert den Refresh-Guard.
    await collector.collect_once(now=1000.0)
    result = await collector.test_fetch(now=1000.0 + 60)

    assert result["ok"] is True
    assert result["city"] == "Wien"
    assert result["slots"] == 1
    assert result["coords"] == {"lat": 48.2, "lon": 16.3}
    assert "appid=***" in result["request_url"]
    assert len(owm.calls) == 2  # trotz kurz zurückliegendem Abruf erneut aufgerufen


async def test_test_fetch_disabled_returns_reason():
    collector = WeatherCollector(_FakeHAClient(_zone_state()), _cfg(api_key=""), None)
    result = await collector.test_fetch(now=1000.0)
    assert result["ok"] is False
    assert "Schlüssel" in result["reason"]


async def test_test_fetch_surfaces_fetch_error_and_masked_url():
    owm = _FakeOWMClient(error=WeatherClientError("HTTP 401: Invalid API key"))
    collector = WeatherCollector(_FakeHAClient(_zone_state()), _cfg(), owm)

    result = await collector.test_fetch(now=1000.0)

    assert result["ok"] is False
    assert "Invalid API key" in result["reason"]
    assert "appid=***" in result["request_url"]


async def test_test_fetch_missing_coords_returns_reason():
    owm = _FakeOWMClient(forecast=_forecast())
    collector = WeatherCollector(_FakeHAClient(_zone_state(lat=None)), _cfg(), owm)

    result = await collector.test_fetch(now=1000.0)
    assert result["ok"] is False
    assert "latitude" in result["reason"]
    assert owm.calls == []


# --- One Call API 4.0 (OneCallCollector) -----------------------------------------------------

class _FakeOneCallClient:
    def __init__(self, slots_by_res=None, error=None):
        self._slots = slots_by_res or {}
        self._error = error
        self.calls = []

    async def fetch_timeline(self, resolution, lat, lon):
        self.calls.append((resolution, lat, lon))
        if self._error is not None:
            raise self._error
        n = self._slots.get(resolution, 1)
        slots = [
            OneCallSlot(
                dt=i, time="t", temp=20.0, feels_like=19.0, temp_min=None, temp_max=None,
                clouds=10.0, pop=0.1, wind_speed=3.0, humidity=50.0, rain=None, snow=None,
                condition="klar", condition_id=800,
            )
            for i in range(n)
        ]
        return OneCallTimeline(
            resolution=resolution, lat=lat, lon=lon, timezone_offset_s=7200, slots=slots
        )

    def masked_request_url(self, resolution, lat, lon):
        return f"https://owm/timeline/{resolution}?lat={lat}&lon={lon}&appid=***&units=metric&lang=de"


def _oc_cfg(api_key="key", *, enable_15min=False, enable_1h=True, enable_1day=True,
            refresh_15min=15, refresh_1h=60, refresh_1day=180, llm_timeline="1h"):
    return WeatherConfig(
        api_key=api_key, zone_entity="zone.home", units="metric", lang="de",
        refresh_min=60, source="onecall",
        onecall=OneCallConfig(
            enable_15min=enable_15min, enable_1h=enable_1h, enable_1day=enable_1day,
            refresh_15min=refresh_15min, refresh_1h=refresh_1h, refresh_1day=refresh_1day,
            llm_timeline=llm_timeline,
        ),
    )


def _calls_by_res(client):
    out: dict[str, int] = {}
    for res, _lat, _lon in client.calls:
        out[res] = out.get(res, 0) + 1
    return out


async def test_onecall_disabled_without_api_key():
    collector = OneCallCollector(_FakeHAClient(_zone_state()), _oc_cfg(api_key=""), None)
    assert collector.enabled is False
    await collector.collect_once(now=1000.0)
    assert collector.snapshot()["timelines"]["1h"]["slots"] == []


async def test_onecall_disabled_without_active_timeline():
    client = _FakeOneCallClient()
    cfg = _oc_cfg(enable_1h=False, enable_1day=False)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client)
    assert collector.enabled is False
    await collector.collect_once(now=1000.0)
    assert client.calls == []


async def test_onecall_collect_fetches_only_enabled_timelines():
    client = _FakeOneCallClient(slots_by_res={"1h": 3, "1day": 2})
    collector = OneCallCollector(_FakeHAClient(_zone_state()), _oc_cfg(), client)

    await collector.collect_once(now=1000.0)

    assert _calls_by_res(client) == {"1h": 1, "1day": 1}  # 15min ist aus
    snap = collector.snapshot()
    assert snap["source"] == "onecall"
    assert snap["enabled"] is True
    assert snap["coords"] == {"lat": 48.2, "lon": 16.3}
    assert snap["llm_timeline"] == "1h"
    assert len(snap["timelines"]["1h"]["slots"]) == 3
    assert len(snap["timelines"]["1day"]["slots"]) == 2
    assert snap["timelines"]["15min"]["enabled"] is False
    assert snap["timelines"]["15min"]["slots"] == []


async def test_onecall_per_timeline_refresh_gating():
    client = _FakeOneCallClient()
    collector = OneCallCollector(_FakeHAClient(_zone_state()), _oc_cfg(), client)

    await collector.collect_once(now=1000.0)  # beide fällig (noch nie geholt)
    assert _calls_by_res(client) == {"1h": 1, "1day": 1}

    # +1 h: 1h ist fällig (>=60 min), 1day noch nicht (braucht 180 min).
    await collector.collect_once(now=1000.0 + 60 * 60 + 1)
    assert _calls_by_res(client) == {"1h": 2, "1day": 1}

    # +3 h: jetzt ist auch 1day fällig.
    await collector.collect_once(now=1000.0 + 180 * 60 + 1)
    assert _calls_by_res(client) == {"1h": 3, "1day": 2}


async def test_onecall_test_fetch_returns_per_timeline_results():
    client = _FakeOneCallClient(slots_by_res={"1h": 4, "1day": 2})
    collector = OneCallCollector(_FakeHAClient(_zone_state()), _oc_cfg(), client)

    result = await collector.test_fetch(now=1000.0)

    assert result["ok"] is True
    assert result["coords"] == {"lat": 48.2, "lon": 16.3}
    by_res = {t["resolution"]: t for t in result["timelines"]}
    assert by_res["1h"]["ok"] is True
    assert by_res["1h"]["slots"] == 4
    assert "appid=***" in by_res["1h"]["request_url"]
    assert set(by_res) == {"1h", "1day"}  # nur aktivierte Timelines


async def test_onecall_fetch_error_isolated_no_crash():
    client = _FakeOneCallClient(error=WeatherClientError("HTTP 401: Invalid API key"))
    collector = OneCallCollector(_FakeHAClient(_zone_state()), _oc_cfg(), client)

    await collector.collect_once(now=1000.0)
    snap = collector.snapshot()
    assert "401" in (snap["last_error"] or "")
    assert snap["timelines"]["1h"]["slots"] == []
    assert "401" in (snap["timelines"]["1h"]["last_error"] or "")
    # Fehlerhafter Abruf setzt last_fetch_ts nicht → nächster Zyklus versucht es erneut.
    assert snap["timelines"]["1h"]["last_fetch_ts"] is None


async def test_resolve_zone_coords_helper_shared_behavior():
    coords, err = await resolve_zone_coords(_FakeHAClient(_zone_state()), "zone.home")
    assert coords == (48.2, 16.3)
    assert err is None

    coords2, err2 = await resolve_zone_coords(_FakeHAClient(_zone_state(lat=None)), "zone.home")
    assert coords2 is None
    assert "latitude" in err2
