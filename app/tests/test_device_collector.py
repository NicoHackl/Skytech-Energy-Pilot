"""Tests für den Device Collector (Fake-HA-Client)."""

import pytest

from energy_pilot.device_collector import DeviceCollector, parse_bool
from energy_pilot.devices import CONTROLLABLE, Device


class _FakeHAClient:
    def __init__(self, states):
        self._states = states

    async def get_state(self, entity_id):
        if entity_id not in self._states:
            raise RuntimeError("not found")
        return {"state": self._states[entity_id]}


HEIZSTAB = Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE)


@pytest.mark.parametrize(
    "raw,expected",
    [("on", True), ("off", False), (True, True), ("unknown", None), ("", None)],
)
def test_parse_bool(raw, expected):
    assert parse_bool(raw) is expected


@pytest.mark.asyncio
async def test_collect_reads_device_values():
    ha = _FakeHAClient(
        {
            "input_boolean.ems_heizstab_technische_freigabe": "on",
            "input_number.ems_heizstab_min_technisch_w": "500",
            "input_number.ems_heizstab_max_technisch_w": "3000",
            "input_number.ep_heizstab_max_temperatur": "60",
        }
    )
    collector = DeviceCollector(ha)
    collector.set_devices([HEIZSTAB], source="hems")

    await collector.collect_once(now=1.0)
    snap = collector.snapshot()

    assert len(snap) == 1
    fields = {f["key"]: f for f in snap[0]["fields"]}
    assert fields["technische_freigabe"]["value"] is True
    assert fields["technische_freigabe"]["source"] == "live"
    assert fields["min_technisch"]["value"] == 500.0
    assert fields["max_technisch"]["value"] == 3000.0
    assert fields["ep_max_temperatur"]["value"] == 60.0
    assert collector.discovery_source == "hems"


@pytest.mark.asyncio
async def test_missing_entity_reported_as_none():
    ha = _FakeHAClient({})  # keine Zustände vorhanden
    collector = DeviceCollector(ha)
    collector.set_devices([HEIZSTAB])

    await collector.collect_once(now=1.0)
    fields = {f["key"]: f for f in collector.snapshot()[0]["fields"]}
    assert fields["min_technisch"]["value"] is None
    assert fields["min_technisch"]["source"] == "none"


@pytest.mark.asyncio
async def test_without_ha_client_all_none():
    collector = DeviceCollector(None)
    collector.set_devices([HEIZSTAB])

    await collector.collect_once(now=1.0)
    snap = collector.snapshot()
    assert all(f["source"] == "none" for f in snap[0]["fields"])


def test_snapshot_empty_without_devices():
    assert DeviceCollector(None).snapshot() == []
