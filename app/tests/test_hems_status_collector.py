"""Tests für den HEMS-Status-Collector (Poll, Fail-Soft, Drosselung, Spiegelung)."""

from datetime import UTC, datetime, timedelta

from energy_pilot.database import init_db
from energy_pilot.devices import CONTROLLABLE, Device
from energy_pilot.hems_status_collector import HEMSStatusCollector

DEVICES = [Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt")]


def _status_payload(priority=10):
    return {
        "status": {
            "pool_w": 1000.0,
            "current_deficit_w": 0.0,
            "global_mode": "auto",
            "devices": [
                {"type": "controllable", "id": "heizstab", "label": "Heizstab",
                 "priority": priority, "eligible": True, "schutz_w": 800.0, "actual_w": 500.0},
            ],
        },
        "last_cycle_at": "2026-06-26 12:00:00",
        "cycle_count": 5,
        "error": "",
        "interval_s": 1,
    }


class _FakeHEMS:
    def __init__(self, payload=None, raises=None):
        self.payload = payload
        self.raises = raises
        self.calls = 0

    async def status(self):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.payload


class _FakePlanner:
    def __init__(self, latest):
        self._latest = latest

    def latest_plan(self):
        return self._latest


class _FakeDeviceCollector:
    devices = DEVICES


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def set_state(self, entity_id, state, attributes=None):
        self.calls.append((entity_id, state, attributes))


def _latest():
    now = datetime.now(UTC)
    return {
        "ok": True,
        "plan": {
            "plan_id": "p1",
            "valid_from": (now - timedelta(minutes=5)).isoformat(),
            "valid_until": (now + timedelta(minutes=55)).isoformat(),
            "devices": [
                {"name": "heizstab", "prio_vorschlag": 10,
                 "geschutzte_mindestleistung_w_vorschlag": 800.0},
            ],
        },
    }


def _collector(hems, *, ha=None, db=None, publish=True, interval=60.0):
    return HEMSStatusCollector(
        hems,
        planner=_FakePlanner(_latest()),
        device_collector=_FakeDeviceCollector(),
        ha_client=ha,
        db=db,
        publish_status_enabled=publish,
        interval_s=interval,
    )


async def test_collect_online_derives_and_publishes():
    conn = init_db(":memory:")
    ha = _FakeHA()
    coll = _collector(_FakeHEMS(payload=_status_payload()), ha=ha, db=conn)

    await coll.collect_once(now=100.0)

    assert coll.online is True
    assert coll.last_error is None
    assert coll.last_feedback["overall"] == "beobachtet_konform"
    written = {c[0] for c in ha.calls}
    assert written == {"sensor.ep_hems_verbindung", "sensor.ep_plan_status"}
    rows = conn.execute("SELECT COUNT(*) AS n FROM hems_feedback").fetchone()["n"]
    assert rows == 1
    conn.close()


async def test_collect_offline_is_fail_soft():
    coll = _collector(_FakeHEMS(raises=RuntimeError("connection refused")), ha=_FakeHA())

    await coll.collect_once(now=100.0)

    assert coll.online is False
    assert "connection refused" in coll.last_error
    assert coll.last_feedback["overall"] == "unbekannt"
    snap = coll.snapshot()
    assert snap["online"] is False
    assert snap["pool_w"] is None


async def test_collect_is_self_throttled():
    hems = _FakeHEMS(payload=_status_payload())
    coll = _collector(hems, ha=_FakeHA(), interval=60.0)

    await coll.collect_once(now=100.0)
    await coll.collect_once(now=130.0)  # < interval → übersprungen
    assert hems.calls == 1

    await coll.collect_once(now=200.0)  # > interval → erneut
    assert hems.calls == 2


async def test_publish_disabled_writes_nothing():
    ha = _FakeHA()
    coll = _collector(_FakeHEMS(payload=_status_payload()), ha=ha, publish=False)

    await coll.collect_once(now=100.0)

    assert ha.calls == []
    assert coll.last_feedback is not None


async def test_snapshot_exposes_hems_fields():
    coll = _collector(_FakeHEMS(payload=_status_payload()), ha=_FakeHA())
    await coll.collect_once(now=100.0)
    snap = coll.snapshot()
    assert snap["online"] is True
    assert snap["pool_w"] == 1000.0
    assert snap["cycle_count"] == 5
    assert snap["global_mode"] == "auto"
    assert len(snap["devices"]) == 1


async def test_test_fetch_not_configured():
    coll = HEMSStatusCollector(None)
    result = await coll.test_fetch()
    assert result["ok"] is False
    assert "konfiguriert" in result["reason"]


async def test_test_fetch_online():
    coll = _collector(_FakeHEMS(payload=_status_payload()), ha=_FakeHA())
    result = await coll.test_fetch()
    assert result["ok"] is True
    assert result["cycle_count"] == 5
    assert result["feedback"]["overall"] == "beobachtet_konform"
