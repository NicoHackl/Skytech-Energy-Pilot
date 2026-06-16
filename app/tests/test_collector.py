"""Tests für den State Collector (mit Fake-HA-Client)."""

import pytest

from energy_pilot.aggregation import RollingAggregator
from energy_pilot.collector import StateCollector
from energy_pilot.entity_map import EntityMapping
from energy_pilot.roles import MEASUREMENT_ROLES, Role

PV = Role("pv_power", "PV-Leistung", averaged=True, unit="W")
SOC = Role("battery_soc", "Batterie-SOC", averaged=False, unit="%")


class _FakeHAClient:
    def __init__(self, states):
        self._states = states

    async def get_state(self, entity_id):
        if entity_id not in self._states:
            raise RuntimeError("not found")
        return {"state": self._states[entity_id]}


def _collector(ha_client, roles):
    return StateCollector(ha_client, RollingAggregator(), roles)


@pytest.mark.asyncio
async def test_live_value_is_collected_and_averaged():
    ha = _FakeHAClient({"sensor.pv": "1500"})
    collector = _collector(ha, (PV,))
    collector.set_mapping({"pv_power": EntityMapping("pv_power", "sensor.pv")})

    sources = await collector.collect_once(now=100.0)
    assert sources["pv_power"] == "live"

    snap = collector.snapshot(now=100.0)
    assert snap["pv_power"]["latest"] == 1500.0
    assert snap["pv_power"]["mean_1m"] == 1500.0


@pytest.mark.asyncio
async def test_fallback_used_when_entity_invalid():
    ha = _FakeHAClient({"sensor.pv": "unavailable"})
    collector = _collector(ha, (PV,))
    collector.set_mapping({"pv_power": EntityMapping("pv_power", "sensor.pv", fallback_value=0.0)})

    sources = await collector.collect_once(now=1.0)
    assert sources["pv_power"] == "fallback"
    assert collector.snapshot(now=1.0)["pv_power"]["latest"] == 0.0


@pytest.mark.asyncio
async def test_fallback_used_when_entity_missing():
    ha = _FakeHAClient({})
    collector = _collector(ha, (PV,))
    collector.set_mapping(
        {"pv_power": EntityMapping("pv_power", "sensor.fehlt", fallback_value=5.0)}
    )

    sources = await collector.collect_once(now=1.0)
    assert sources["pv_power"] == "fallback"


@pytest.mark.asyncio
async def test_unmapped_role_reports_none():
    collector = _collector(_FakeHAClient({}), (PV,))
    sources = await collector.collect_once(now=1.0)
    assert sources["pv_power"] == "none"


@pytest.mark.asyncio
async def test_non_averaged_role_keeps_last_value():
    ha = _FakeHAClient({"sensor.soc": "55"})
    collector = _collector(ha, (SOC,))
    collector.set_mapping({"battery_soc": EntityMapping("battery_soc", "sensor.soc")})

    await collector.collect_once(now=1.0)
    snap = collector.snapshot(now=1.0)
    assert snap["battery_soc"]["value"] == 55.0
    assert "mean_1m" not in snap["battery_soc"]


def test_snapshot_covers_all_roles_without_data():
    collector = _collector(None, MEASUREMENT_ROLES)
    snap = collector.snapshot(now=1.0)
    assert set(snap) == {role.key for role in MEASUREMENT_ROLES}
