"""Tests für den Device Collector (Fake-HA-Client)."""

import pytest

from energy_pilot.control_mode import HA_GLOBAL_MODE
from energy_pilot.device_collector import DeviceCollector, parse_bool, parse_by_kind, parse_text
from energy_pilot.devices import CONTROLLABLE, Device, DeviceExtra, HEMSField


class _FakeHAClient:
    def __init__(self, states):
        self._states = states

    async def get_state(self, entity_id):
        if entity_id not in self._states:
            raise RuntimeError("not found")
        return {"state": self._states[entity_id]}


class _FakeHAClientAttrs:
    """Fake-HA-Client, der je Entität Zustand UND Attribute liefert (für D-048-Tests)."""

    def __init__(self, states):  # states: entity -> {"state":..., "attributes":{...}}
        self._states = states

    async def get_state(self, entity_id):
        if entity_id not in self._states:
            raise RuntimeError("not found")
        return self._states[entity_id]


HEIZSTAB = Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE)
# Heizstab mit Zusatz-Entität (D-047): wird gelesen, erscheint aber nicht in `fields`.
_MAX_TEMP_EXTRA = DeviceExtra(
    read_entity_id="input_number.ep_heizstab_max_temperatur", ai_suggestion=True, unit="°C"
)
HEIZSTAB_WITH_EXTRA = Device(
    "heizstab", "Heizstab", "heizstab", CONTROLLABLE, extras=(_MAX_TEMP_EXTRA,)
)


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
    collector.set_devices([HEIZSTAB_WITH_EXTRA], source="hems")

    await collector.collect_once(now=1.0)
    snap = collector.snapshot()

    assert len(snap) == 1
    fields = {f["key"]: f for f in snap[0]["fields"]}
    assert fields["technische_freigabe"]["value"] is True
    assert fields["technische_freigabe"]["source"] == "live"
    assert fields["min_technisch"]["value"] == 500.0
    assert fields["max_technisch"]["value"] == 3000.0
    # Zusatz-Entität (D-047) wird gelesen (last_values), erscheint aber NICHT in `fields`.
    assert "extra_heizstab_max_temperatur" not in fields
    read = collector.last_values["heizstab"]["extra_heizstab_max_temperatur"]
    assert read["value"] == 60.0 and read["source"] == "live"
    assert collector.discovery_source == "hems"


@pytest.mark.asyncio
async def test_collect_reads_global_hems_userinputs_once():
    collector = DeviceCollector(
        _FakeHAClient(
            {
                "input_number.ems_globaler_puffer_w": "250",
                HA_GLOBAL_MODE: "manuell",
                "input_select.ems_heizstab_modus": "manuell",
            }
        )
    )
    collector.set_devices([], source="hems")
    collector.set_global_fields(
        (
            HEMSField(
                "globaler_puffer_w",
                "Globaler Puffer",
                "number",
                "input_number.ems_globaler_puffer_w",
                "W",
                "user_preference",
                True,
            ),
        )
    )

    await collector.collect_once(now=1.0)

    assert collector.global_values["globaler_puffer_w"]["value"] == 250.0


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


# -- Modus-Achse für die Anzeige (D-057) -----------------------------------


@pytest.mark.asyncio
async def test_snapshot_exposes_mode_and_control_source():
    """Der Collector spiegelt den Modus für die UI – das Gate liest davon unabhängig frisch."""
    collector = DeviceCollector(
        _FakeHAClient(
            {
                HA_GLOBAL_MODE: "manuell",
                "input_select.ems_heizstab_modus": "auto",
                "input_boolean.ems_heizstab_technische_freigabe": "on",
            }
        )
    )
    collector.set_devices([HEIZSTAB])

    await collector.collect_once(now=1.0)
    snap = collector.snapshot()[0]

    assert snap["mode"] == "auto"
    assert snap["global_mode"] == "manuell"
    assert snap["control_source"] == "ep"  # Gerät auto bei global manuell => KI
    assert snap["mode_entity_id"] == "input_select.ems_heizstab_modus"


@pytest.mark.asyncio
async def test_snapshot_control_source_blocked_without_ha_client():
    collector = DeviceCollector(None)
    collector.set_devices([HEIZSTAB])

    await collector.collect_once(now=1.0)

    assert collector.snapshot()[0]["control_source"] == "aus"


# -- Typgerechtes Lesen aller Domänen + Attribut-Erfassung (D-048) ----------


def test_parse_by_kind_variants():
    assert parse_by_kind("bool", "on") is True
    assert parse_by_kind("number", "3.5") == 3.5
    assert parse_by_kind("text", "Hallo") == "Hallo"
    assert parse_by_kind("datetime", "2026-07-02 08:00:00") == "2026-07-02 08:00:00"
    assert parse_by_kind("number", "keinezahl") is None
    # auto: Zahl wenn möglich, sonst Text
    assert parse_by_kind("auto", "42") == 42.0
    assert parse_by_kind("auto", "eco") == "eco"
    assert parse_text("unavailable") is None


@pytest.mark.asyncio
async def test_collect_reads_all_domains_with_attributes():
    ha = _FakeHAClientAttrs({
        "input_boolean.eco": {"state": "on", "attributes": {}},
        "input_text.hinweis": {"state": "Bitte sparen", "attributes": {}},
        "sensor.auto_soc": {"state": "42.0", "attributes": {"unit_of_measurement": "%"}},
        "input_number.min_soc": {"state": "20",
                                 "attributes": {"min": 0, "max": 100, "unit_of_measurement": "%"}},
        "input_datetime.abfahrt": {"state": "2026-07-02 08:00:00",
                                   "attributes": {"has_date": True, "has_time": True}},
    })
    extras = (
        DeviceExtra(read_entity_id="input_boolean.eco"),
        DeviceExtra(read_entity_id="input_text.hinweis"),
        DeviceExtra(read_entity_id="sensor.auto_soc"),
        DeviceExtra(read_entity_id="input_number.min_soc"),
        DeviceExtra(read_entity_id="input_datetime.abfahrt"),
    )
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, extras=extras)
    collector = DeviceCollector(ha)
    collector.set_devices([dev], source="hems")
    await collector.collect_once(now=1.0)
    vals = collector.last_values["wallbox"]

    assert vals["extra_eco"]["value"] is True
    assert vals["extra_hinweis"]["value"] == "Bitte sparen"
    assert vals["extra_auto_soc"]["value"] == 42.0  # auto -> Zahl
    assert vals["extra_min_soc"]["value"] == 20.0
    # input_number: min/max als Attribute erfasst (Grenzen für die KI, D-048)
    assert vals["extra_min_soc"]["attrs"] == {"min": 0, "max": 100, "unit_of_measurement": "%"}
    # input_datetime: has_date/has_time erfasst
    assert vals["extra_abfahrt"]["value"] == "2026-07-02 08:00:00"
    assert vals["extra_abfahrt"]["attrs"] == {"has_date": True, "has_time": True}


@pytest.mark.asyncio
async def test_collect_input_select_reads_value_and_options():
    # input_select (D-049): Zustand = gewählte Option; `options` als Auswahlpool erfasst.
    ha = _FakeHAClientAttrs({
        "input_select.lademodus": {
            "state": "PV-Überschuss",
            "attributes": {"options": ["Aus", "PV-Überschuss", "Schnell"]},
        },
    })
    ex = DeviceExtra(read_entity_id="input_select.lademodus", ai_suggestion=True)
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, extras=(ex,))
    collector = DeviceCollector(ha)
    collector.set_devices([dev], source="hems")
    await collector.collect_once(now=1.0)
    rec = collector.last_values["wallbox"]["extra_lademodus"]
    assert rec["value"] == "PV-Überschuss"
    assert rec["attrs"]["options"] == ["Aus", "PV-Überschuss", "Schnell"]
