"""Tests für den Forecast Collector (Fake-HA-Client)."""

import pytest

from energy_pilot.forecast import PVOrientation
from energy_pilot.forecast_collector import ForecastCollector


class _FakeHAClient:
    def __init__(self, states):
        self._states = states

    async def get_state(self, entity_id):
        if entity_id not in self._states:
            raise RuntimeError("not found")
        return {"state": self._states[entity_id]}


def _totals(snapshot):
    return {v["key"]: v["total"] for v in snapshot["values"]}


def _two_orientations():
    return [
        PVOrientation(
            "Ost", {"current_hour": "sensor.ost_jetzt", "tomorrow": "sensor.ost_morgen"}
        ),
        PVOrientation(
            "West", {"current_hour": "sensor.west_jetzt", "tomorrow": "sensor.west_morgen"}
        ),
    ]


@pytest.mark.asyncio
async def test_sums_across_orientations():
    ha = _FakeHAClient(
        {
            "sensor.ost_jetzt": "1.5",
            "sensor.ost_morgen": "10",
            "sensor.west_jetzt": "2.5",
            "sensor.west_morgen": "12",
        }
    )
    collector = ForecastCollector(ha, unit="kWh")
    collector.set_orientations(_two_orientations())

    await collector.collect_once(now=1.0)
    snap = collector.snapshot()
    totals = _totals(snap)

    assert totals["current_hour"] == 4.0
    assert totals["tomorrow"] == 22.0
    # Nicht konfigurierte Wert-Typen tauchen als Summe None auf.
    assert totals["next_hour"] is None
    assert snap["unit"] == "kWh"


@pytest.mark.asyncio
async def test_missing_sensor_excluded_from_sum():
    ha = _FakeHAClient({"sensor.ost_jetzt": "1.5"})  # West fehlt
    collector = ForecastCollector(ha)
    collector.set_orientations(_two_orientations())

    await collector.collect_once(now=1.0)
    snap = collector.snapshot()

    assert _totals(snap)["current_hour"] == 1.5  # nur Ost zählt
    west = next(o for o in snap["orientations"] if o["label"] == "West")
    assert west["values"]["current_hour"]["source"] == "none"


@pytest.mark.asyncio
async def test_all_missing_yields_none_total():
    collector = ForecastCollector(_FakeHAClient({}))
    collector.set_orientations(_two_orientations())

    await collector.collect_once(now=1.0)
    assert _totals(collector.snapshot())["current_hour"] is None


@pytest.mark.asyncio
async def test_without_ha_client_all_none():
    collector = ForecastCollector(None)
    collector.set_orientations(_two_orientations())

    await collector.collect_once(now=1.0)
    snap = collector.snapshot()
    assert all(v["total"] is None for v in snap["values"])


def test_snapshot_empty_without_orientations():
    snap = ForecastCollector(None, unit="Wh").snapshot()
    assert snap["orientations"] == []
    assert all(v["total"] is None for v in snap["values"])
    assert snap["unit"] == "Wh"
