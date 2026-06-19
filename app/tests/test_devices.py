"""Tests für Gerätemodell, Read-Schema-Ableitung und Discovery."""

import pytest

from energy_pilot.devices import (
    BINARY,
    CONTROLLABLE,
    Device,
    devices_from_config,
    discover,
    discover_from_hems_schema,
    read_fields,
)

# Repräsentatives HEMS-Schema (analog _ctrl_items_controllable/_ctrl_items_binary).
HEMS_SCHEMA = [
    {"label": "Global", "items": [{"entity": "input_boolean.ems_pv_regelung_aktiv"}]},
    {
        "label": "Heizstab",
        "items": [
            {"entity": "input_boolean.ems_heizstab_freigabe"},
            {"entity": "input_boolean.ems_heizstab_technische_freigabe"},
            {"entity": "input_number.ems_heizstab_prioritat"},
            {"entity": "input_number.ems_heizstab_geschutzte_mindestleistung_w"},
            {"entity": "input_number.ems_heizstab_min_technisch_w"},
            {"entity": "input_number.ems_heizstab_max_technisch_w"},
        ],
    },
    {
        "label": "Heizlüfter 1",
        "items": [
            {"entity": "input_boolean.ems_heizluefter_1_freigabe"},
            {"entity": "input_boolean.ems_heizluefter_1_technische_freigabe"},
            {"entity": "input_number.ems_heizluefter_1_prioritat"},
            {"entity": "input_number.ems_heizluefter_1_leistung_w"},
        ],
    },
    {
        "label": "Wallbox",
        "items": [
            {"entity": "input_boolean.ems_wallbox_technische_freigabe"},
            {"entity": "input_number.ems_wallbox_min_technisch_a"},
            {"entity": "input_number.ems_wallbox_max_technisch_a"},
        ],
    },
]


def _fields_by_key(device):
    return {f.key: f for f in read_fields(device)}


def test_read_fields_binary():
    dev = Device("heizluefter_1", "Heizlüfter 1", "heizluefter_1", BINARY)
    fields = _fields_by_key(dev)
    assert fields["leistung_w"].entity_id == "input_number.ems_heizluefter_1_leistung_w"
    assert fields["leistung_w"].kind == "number"
    freigabe_entity = fields["technische_freigabe"].entity_id
    assert freigabe_entity == "input_boolean.ems_heizluefter_1_technische_freigabe"
    assert fields["technische_freigabe"].kind == "bool"
    assert "min_technisch" not in fields


def test_read_fields_controllable_watt():
    dev = Device("batterie", "Batterie", "batterie", CONTROLLABLE)
    fields = _fields_by_key(dev)
    assert fields["min_technisch"].entity_id == "input_number.ems_batterie_min_technisch_w"
    assert fields["max_technisch"].entity_id == "input_number.ems_batterie_max_technisch_w"
    assert fields["max_technisch"].unit == "W"
    # Nur der Heizstab hat den Temperatur-Sonderfall.
    assert "ep_max_temperatur" not in fields


def test_read_fields_controllable_ampere():
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, output_unit="ampere")
    fields = _fields_by_key(dev)
    assert fields["min_technisch"].entity_id == "input_number.ems_wallbox_min_technisch_a"
    assert fields["max_technisch"].unit == "A"


def test_read_fields_heizstab_special_temperature():
    dev = Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE)
    fields = _fields_by_key(dev)
    assert fields["ep_max_temperatur"].entity_id == "input_number.ep_heizstab_max_temperatur"
    assert fields["ep_max_temperatur"].unit == "°C"


def test_discover_from_hems_schema_classes_and_units():
    devices = {d.name: d for d in discover_from_hems_schema(HEMS_SCHEMA)}
    assert set(devices) == {"heizstab", "heizluefter_1", "wallbox"}  # "Global" übersprungen
    assert devices["heizstab"].device_class == CONTROLLABLE
    assert devices["heizstab"].output_unit == "watt"
    assert devices["heizluefter_1"].device_class == BINARY
    assert devices["wallbox"].device_class == CONTROLLABLE
    assert devices["wallbox"].output_unit == "ampere"


def test_discover_from_hems_schema_skips_unidentifiable_group():
    schema = [{"label": "Komisch", "items": [{"entity": "input_number.ems_x_prioritat"}]}]
    assert discover_from_hems_schema(schema) == []


def test_devices_from_config_parses_and_validates():
    values = {
        "devices": [
            {"name": "heizstab", "class": "controllable"},
            {
                "name": "wallbox", "entity_prefix": "wb",
                "class": "controllable", "output_unit": "ampere",
            },
            {"name": "kaputt", "class": "unsinn"},  # ungültige Klasse -> übersprungen
            {"class": "binary"},  # ohne name -> übersprungen
        ]
    }
    devices = {d.name: d for d in devices_from_config(values)}
    assert set(devices) == {"heizstab", "wallbox"}
    assert devices["heizstab"].entity_prefix == "heizstab"
    assert devices["wallbox"].entity_prefix == "wb"
    assert devices["wallbox"].output_unit == "ampere"


class _FakeHEMS:
    def __init__(self, schema=None, error=False):
        self._schema = schema
        self._error = error

    async def device_schema(self):
        if self._error:
            raise RuntimeError("HEMS nicht erreichbar")
        return self._schema


@pytest.mark.asyncio
async def test_discover_prefers_hems():
    devices, source = await discover(_FakeHEMS(schema=HEMS_SCHEMA), {})
    assert source == "hems"
    assert {d.name for d in devices} == {"heizstab", "heizluefter_1", "wallbox"}


@pytest.mark.asyncio
async def test_discover_falls_back_to_config_when_hems_down():
    values = {"devices": [{"name": "heizstab", "class": "controllable"}]}
    devices, source = await discover(_FakeHEMS(error=True), values)
    assert source == "config"
    assert [d.name for d in devices] == ["heizstab"]


@pytest.mark.asyncio
async def test_discover_without_hems_uses_config():
    values = {"devices": [{"name": "heizstab", "class": "controllable"}]}
    devices, source = await discover(None, values)
    assert source == "config"


@pytest.mark.asyncio
async def test_discover_none_when_nothing_available():
    devices, source = await discover(None, {})
    assert source == "none"
    assert devices == []
