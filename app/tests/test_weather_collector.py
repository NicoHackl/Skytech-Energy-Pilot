"""Tests für den Weather Collector (Fake-HA-Client + Fake-OWM-Client)."""

from energy_pilot.database import init_db
from energy_pilot.weather import (
    OneCallAlert,
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
    def __init__(self, slots_by_res=None, error=None, *, pages_by_res=None,
                 alert_ids_by_res=None, alert_details=None, alert_error=None):
        self._slots = slots_by_res or {}
        self._pages = pages_by_res or {}  # wie viele Seiten je Timeline verfügbar sind
        self._error = error
        # Alert-IDs, die die jeweilige Timeline-Antwort in `data[].alerts` mitträgt.
        self._alert_ids = alert_ids_by_res or {}
        # ID → Detail-Alert (One Call 4.0 löst je ID separat auf).
        self._alert_details = alert_details or {}
        self._alert_error = alert_error
        self.calls = []
        self.alert_calls = []

    async def fetch_timeline(self, resolution, lat, lon, *, max_calls=1):
        self.calls.append((resolution, lat, lon, max_calls))
        if self._error is not None:
            raise self._error
        pages = min(max_calls, self._pages.get(resolution, 1))  # paginiert bis max_calls
        per_page = self._slots.get(resolution, 1)
        slots = [
            OneCallSlot(
                dt=i, time="t", temp=20.0, feels_like=19.0, temp_min=None, temp_max=None,
                clouds=10.0, pop=0.1, wind_speed=3.0, humidity=50.0, rain=None, snow=None,
                condition="klar", condition_id=800,
            )
            for i in range(per_page * pages)
        ]
        timeline = OneCallTimeline(
            resolution=resolution, lat=lat, lon=lon, timezone_offset_s=7200, slots=slots,
            alert_ids=list(self._alert_ids.get(resolution, [])),
        )
        return timeline, pages

    async def fetch_alert(self, alert_id):
        self.alert_calls.append(alert_id)
        if self._alert_error is not None:
            raise self._alert_error
        return self._alert_details[alert_id]

    def masked_request_url(self, resolution, lat, lon):
        return f"https://owm/timeline/{resolution}?lat={lat}&lon={lon}&appid=***&units=metric&lang=de"

    def masked_alert_url(self, alert_id=None):
        return f"https://owm/alert/{alert_id or '{id}'}?appid=***&lang=de"


def _oc_cfg(api_key="key", *, enable_15min=False, enable_1h=True, enable_1day=True,
            refresh_15min=15, refresh_1h=60, refresh_1day=180, llm_timeline="1h",
            pages_15min=1, pages_1h=1, pages_1day=1, daily_call_budget=1000,
            enable_alerts=True, refresh_alerts=30):
    return WeatherConfig(
        api_key=api_key, zone_entity="zone.home", units="metric", lang="de",
        refresh_min=60, source="onecall",
        onecall=OneCallConfig(
            enable_15min=enable_15min, enable_1h=enable_1h, enable_1day=enable_1day,
            refresh_15min=refresh_15min, refresh_1h=refresh_1h, refresh_1day=refresh_1day,
            llm_timeline=llm_timeline, pages_15min=pages_15min, pages_1h=pages_1h,
            pages_1day=pages_1day, daily_call_budget=daily_call_budget,
            enable_alerts=enable_alerts, refresh_alerts=refresh_alerts,
        ),
    )


def _calls_by_res(client):
    out: dict[str, int] = {}
    for entry in client.calls:
        res = entry[0]
        out[res] = out.get(res, 0) + 1
    return out


async def test_onecall_disabled_without_api_key():
    collector = OneCallCollector(_FakeHAClient(_zone_state()), _oc_cfg(api_key=""), None)
    assert collector.enabled is False
    await collector.collect_once(now=1000.0)
    assert collector.snapshot()["timelines"]["1h"]["slots"] == []


async def test_onecall_disabled_without_active_timeline():
    client = _FakeOneCallClient()
    cfg = _oc_cfg(enable_1h=False, enable_1day=False, enable_alerts=False)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client)
    assert collector.enabled is False
    await collector.collect_once(now=1000.0)
    assert client.calls == []
    assert client.alert_calls == []


async def test_onecall_enabled_with_only_alerts():
    # Alerts allein (ohne aktive Timeline) halten den Collector aktiv (neue O3-Semantik).
    client = _FakeOneCallClient()
    cfg = _oc_cfg(enable_1h=False, enable_1day=False, enable_alerts=True)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client)
    assert collector.enabled is True


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


# --- O2: Pagination + Tages-Call-Budget ------------------------------------------------------

async def test_onecall_pagination_accumulates_slots_and_consumes_budget():
    db = init_db(":memory:")
    client = _FakeOneCallClient(slots_by_res={"1h": 2}, pages_by_res={"1h": 3})
    cfg = _oc_cfg(enable_1day=False, enable_alerts=False, pages_1h=3, daily_call_budget=100)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    await collector.collect_once(now=1000.0)

    snap = collector.snapshot()
    assert len(snap["timelines"]["1h"]["slots"]) == 6  # 2 Slots × 3 Seiten
    assert snap["timelines"]["1h"]["pages"] == 3
    assert snap["calls_today"] == 3  # 3 bezahlte Seiten-Calls verbucht


async def test_onecall_pages_capped_by_remaining_budget():
    db = init_db(":memory:")
    client = _FakeOneCallClient(slots_by_res={"1h": 1}, pages_by_res={"1h": 5})
    cfg = _oc_cfg(enable_1day=False, enable_alerts=False, pages_1h=5, daily_call_budget=2)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    await collector.collect_once(now=1000.0)

    snap = collector.snapshot()
    # Budget 2 begrenzt die 5 konfigurierten Seiten auf 2.
    assert client.calls[0][3] == 2  # max_calls an den Client = min(pages, remaining)
    assert len(snap["timelines"]["1h"]["slots"]) == 2
    assert snap["calls_today"] == 2
    assert snap["budget_exhausted"] is True


async def test_onecall_budget_skips_further_timelines_when_exhausted():
    db = init_db(":memory:")
    client = _FakeOneCallClient(slots_by_res={"1h": 2, "1day": 2})
    cfg = _oc_cfg(daily_call_budget=1, enable_alerts=False)  # nur 1 Call/Tag
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    await collector.collect_once(now=1000.0)

    by_res = _calls_by_res(client)
    assert by_res.get("1h") == 1  # erste Timeline verbraucht das Budget
    assert "1day" not in by_res  # zweite Timeline wird übersprungen
    snap = collector.snapshot()
    assert snap["calls_today"] == 1
    assert snap["budget_remaining"] == 0
    assert snap["budget_exhausted"] is True


async def test_onecall_budget_resets_on_new_utc_day():
    db = init_db(":memory:")
    from energy_pilot import onecall_budget
    onecall_budget.consume(db, 5, now_day="2026-06-26")
    assert onecall_budget.calls_today(db, now_day="2026-06-26") == 5
    # Neuer Tag → Zähler springt auf 0 (OWM-Quota-Reset um Mitternacht UTC).
    assert onecall_budget.calls_today(db, now_day="2026-06-27") == 0
    assert onecall_budget.remaining(db, 1000, now_day="2026-06-27") == 1000


async def test_onecall_budget_survives_fresh_connection(tmp_path):
    from energy_pilot import onecall_budget
    db_path = str(tmp_path / "ep.db")
    db1 = init_db(db_path)
    onecall_budget.consume(db1, 3, now_day="2026-06-26")
    db1.close()
    # „Neustart": frische Connection auf dieselbe Datei → Zähler bleibt erhalten.
    db2 = init_db(db_path)
    assert onecall_budget.calls_today(db2, now_day="2026-06-26") == 3


# --- O3: Unwetter-Alerts ---------------------------------------------------------------------

async def test_onecall_collect_resolves_alert_ids_into_details():
    # Alert-IDs stammen aus der Timeline-Antwort; je ID ein Detail-Call (One Call 4.0).
    db = init_db(":memory:")
    client = _FakeOneCallClient(
        slots_by_res={"1h": 1},
        alert_ids_by_res={"1h": ["ID-A", "ID-B"]},
        alert_details={
            "ID-A": OneCallAlert("DWD", "Sturm", 1, 2, "Sturmböen", ["Wind"]),
            "ID-B": OneCallAlert("DWD", "Hitze", 3, 4, "Hitzewelle", []),
        },
    )
    cfg = _oc_cfg(enable_1day=False, enable_alerts=True, daily_call_budget=100)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    await collector.collect_once(now=1000.0)

    assert client.alert_calls == ["ID-A", "ID-B"]
    snap = collector.snapshot()
    assert snap["alerts_enabled"] is True
    assert [a["event"] for a in snap["alerts"]] == ["Sturm", "Hitze"]
    # 1 Timeline-Call + 2 Alert-Detail-Calls gegen dasselbe Budget.
    assert snap["calls_today"] == 3


async def test_onecall_no_active_alerts_makes_no_detail_call():
    # Timeline ohne Alert-IDs → keine aktiven Warnungen, kein Detail-Call, kein Fehler.
    db = init_db(":memory:")
    client = _FakeOneCallClient(slots_by_res={"1h": 1}, alert_ids_by_res={"1h": []})
    cfg = _oc_cfg(enable_1day=False, enable_alerts=True, daily_call_budget=100)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    await collector.collect_once(now=1000.0)

    assert client.alert_calls == []
    snap = collector.snapshot()
    assert snap["alerts"] == []
    assert snap["alerts_last_error"] is None
    assert snap["calls_today"] == 1  # nur der Timeline-Call


async def test_onecall_alerts_skipped_when_budget_exhausted():
    db = init_db(":memory:")
    client = _FakeOneCallClient(
        slots_by_res={"1h": 1}, alert_ids_by_res={"1h": ["ID-A"]},
        alert_details={"ID-A": OneCallAlert(None, "Sturm", 1, 2, None, [])},
    )
    cfg = _oc_cfg(enable_1day=False, enable_alerts=True, daily_call_budget=1)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    await collector.collect_once(now=1000.0)

    # 1h verbraucht das eine erlaubte Call → Alert-Detail-Call wird übersprungen.
    assert client.alert_calls == []
    assert collector.snapshot()["alerts"] == []


async def test_onecall_alerts_need_active_timeline():
    # Alerts an, aber keine Timeline aktiv → keine Alert-IDs ermittelbar (klarer Hinweis).
    db = init_db(":memory:")
    client = _FakeOneCallClient()
    cfg = _oc_cfg(enable_1h=False, enable_1day=False, enable_alerts=True)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    await collector.collect_once(now=1000.0)

    assert client.alert_calls == []
    snap = collector.snapshot()
    assert "Timeline" in (snap["alerts_last_error"] or "")

    result = await collector.test_fetch(now=1000.0)
    assert result["alerts"]["ok"] is False
    assert "Timeline" in result["alerts"]["reason"]


async def test_onecall_test_fetch_reports_alerts_and_budget():
    db = init_db(":memory:")
    client = _FakeOneCallClient(
        slots_by_res={"1h": 2, "1day": 2}, alert_ids_by_res={"1h": ["ID-A"]},
        alert_details={"ID-A": OneCallAlert(None, "Hitze", 1, 2, None, [])},
    )
    cfg = _oc_cfg(daily_call_budget=1, enable_alerts=True)
    collector = OneCallCollector(_FakeHAClient(_zone_state()), cfg, client, db=db)

    result = await collector.test_fetch(now=1000.0)

    by_res = {t["resolution"]: t for t in result["timelines"]}
    assert by_res["1h"]["ok"] is True
    assert by_res["1day"]["ok"] is False
    assert "Budget" in by_res["1day"]["reason"]
    assert result["alerts"]["ok"] is False  # Budget bereits erschöpft
    assert result["calls_today"] == 1
    assert result["daily_call_budget"] == 1
