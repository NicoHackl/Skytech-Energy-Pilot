"""Tests für den State Collector (mit Fake-HA-Client)."""

import pytest

from energy_pilot.aggregation import RollingAggregator
from energy_pilot.collector import StateCollector
from energy_pilot.entity_map import EntityMapping
from energy_pilot.roles import MEASUREMENT_ROLES, ROLES_BY_KEY, Role

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
async def test_invalid_entity_value_reports_none():
    ha = _FakeHAClient({"sensor.pv": "unavailable"})
    collector = _collector(ha, (PV,))
    collector.set_mapping({"pv_power": EntityMapping("pv_power", "sensor.pv")})

    sources = await collector.collect_once(now=1.0)
    assert sources["pv_power"] == "none"


@pytest.mark.asyncio
async def test_missing_entity_reports_none():
    ha = _FakeHAClient({})
    collector = _collector(ha, (PV,))
    collector.set_mapping({"pv_power": EntityMapping("pv_power", "sensor.fehlt")})

    sources = await collector.collect_once(now=1.0)
    assert sources["pv_power"] == "none"


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


@pytest.mark.asyncio
async def test_temperature_roles_are_averaged_so_the_trend_is_visible():
    """D-061: Warmwasser- und Außentemperatur laufen als gemittelte Rollen.

    Nicht der Absolutwert trägt die Information, sondern der Verlauf: eine steigende
    Speichertemperatur ohne Heizstableistung heißt „eine andere Wärmequelle lädt".
    """
    ww = ROLES_BY_KEY["hot_water_temp"]
    assert ww.averaged is True and ww.unit == "°C"
    assert ROLES_BY_KEY["outdoor_temp"].averaged is True

    ha = _FakeHAClient({"sensor.ww": "70.0"})
    collector = _collector(ha, (ww,))
    collector.set_mapping({"hot_water_temp": EntityMapping("hot_water_temp", "sensor.ww")})
    await collector.collect_once(now=0.0)
    ha._states["sensor.ww"] = "76.0"
    await collector.collect_once(now=1800.0)

    snap = collector.snapshot(now=1800.0)["hot_water_temp"]
    assert snap["latest"] == 76.0
    # Der 60-min-Mittelwert liegt unter dem Letztwert => der Speicher wird gerade wärmer.
    assert snap["mean_60m"] < snap["latest"]


def test_measurement_roles_include_both_temperatures():
    keys = {role.key for role in MEASUREMENT_ROLES}
    assert {"hot_water_temp", "outdoor_temp"} <= keys
