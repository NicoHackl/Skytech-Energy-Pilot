"""Tests für Gerätemodell, Read-Schema-Ableitung und Discovery."""

import pytest

from energy_pilot.devices import (
    BINARY,
    CONTROLLABLE,
    Device,
    DeviceExtra,
    discover,
    discover_from_hems_schema,
    read_fields,
)

# Repräsentatives HEMS-Schema (analog _ctrl_items_controllable/_ctrl_items_binary).
# Die Wallbox-Gruppe hat bewusst einen `name` ("wallbox_1"), der vom Entitätspräfix
# ("wallbox") und vom Anzeige-`label` ("Wallbox") abweicht – damit deckt der Test ab,
# dass die Geräteidentität am technischen `name` und nicht am Label/Präfix hängt.
HEMS_SCHEMA = [
    {"label": "Global", "items": [{"entity": "input_boolean.ems_pv_regelung_aktiv"}]},
    {
        "name": "heizstab",
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
        "name": "heizluefter_1",
        "label": "Heizlüfter 1",
        "items": [
            {"entity": "input_boolean.ems_heizluefter_1_freigabe"},
            {"entity": "input_boolean.ems_heizluefter_1_technische_freigabe"},
            {"entity": "input_number.ems_heizluefter_1_prioritat"},
            {"entity": "input_number.ems_heizluefter_1_leistung_w"},
        ],
    },
    {
        "name": "wallbox_1",
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
    # Ohne konfigurierte Zusatz-Entitäten (D-047) gibt es keine `extra_*`-Lesefelder.
    assert not any(k.startswith("extra_") for k in fields)


def test_read_fields_controllable_ampere():
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, output_unit="ampere")
    fields = _fields_by_key(dev)
    assert fields["min_technisch"].entity_id == "input_number.ems_wallbox_min_technisch_a"
    assert fields["max_technisch"].unit == "A"


def test_read_fields_include_configured_extras():
    # Zusatz-Entitäten (D-047, generalisiert D-035) erzeugen zusätzliche `extra_*`-Lesefelder.
    extra = DeviceExtra(
        read_entity_id="input_number.ep_heizstab_max_temperatur",
        ai_suggestion=True, label="Max. Wassertemperatur", unit="°C",
    )
    dev = Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, extras=(extra,))
    fields = _fields_by_key(dev)
    # Feldschlüssel = read_key (führendes `ep_` der object_id entfällt, kein `ep_ep_`).
    assert extra.read_key == "extra_heizstab_max_temperatur"
    assert fields["extra_heizstab_max_temperatur"].entity_id == (
        "input_number.ep_heizstab_max_temperatur"
    )
    assert fields["extra_heizstab_max_temperatur"].unit == "°C"
    # Namensschema der abgeleiteten Vorschlags-Sensorik bleibt zum Alt-Verhalten kompatibel.
    assert extra.plan_field == "extra_heizstab_max_temperatur_vorschlag"
    assert extra.suggestion_entity_id == "sensor.ep_heizstab_max_temperatur_vorschlag"


def test_device_extra_object_id_strips_domain_and_ep_prefix():
    # `input_number.min_soc_auto` -> object_id `min_soc_auto` -> sensor.ep_min_soc_auto_vorschlag
    ex = DeviceExtra(read_entity_id="input_number.min_soc_auto", ai_suggestion=True)
    assert ex.object_id == "min_soc_auto"
    assert ex.suggestion_entity_id == "sensor.ep_min_soc_auto_vorschlag"
    assert ex.plan_field == "extra_min_soc_auto_vorschlag"
    assert ex.display_label == "Min Soc Auto"


def test_device_extra_kind_and_capture_attrs_per_domain():
    # Datentyp + mitgelesene Attribute folgen der HA-Domäne (D-048).
    cases = {
        "input_number.x": ("number", ("min", "max", "step", "unit_of_measurement")),
        "input_boolean.x": ("bool", ()),
        "input_datetime.x": ("datetime", ("has_date", "has_time")),
        "input_text.x": ("text", ()),
        "input_select.x": ("select", ("options",)),
        "select.x": ("select", ("options",)),
        "sensor.x": ("auto", ("unit_of_measurement", "device_class")),
    }
    for entity, (kind, attrs) in cases.items():
        ex = DeviceExtra(read_entity_id=entity)
        assert ex.domain == entity.split(".")[0]
        assert ex.kind == kind
        assert ex.capture_attrs == attrs


def test_device_extra_writable_helper_domains():
    # D-052: nur echte Helfer-Domänen sind schreibbar; sensor/switch/light/binary_sensor nicht.
    writable = {
        "input_number.x", "number.x", "input_boolean.x", "input_datetime.x",
        "input_text.x", "text.x", "input_select.x", "select.x",
    }
    not_writable = {"sensor.x", "switch.x", "light.x", "binary_sensor.x"}
    for entity in writable:
        assert DeviceExtra(read_entity_id=entity).is_writable_helper is True
    for entity in not_writable:
        assert DeviceExtra(read_entity_id=entity).is_writable_helper is False


def test_device_extra_should_write_original_requires_all_three():
    # D-052: nur wirksam, wenn write_original + ai_suggestion + schreibbarer Helfer zusammenkommen.
    full = DeviceExtra(
        read_entity_id="input_number.x", ai_suggestion=True, write_original=True
    )
    assert full.should_write_original is True

    no_suggestion = DeviceExtra(
        read_entity_id="input_number.x", ai_suggestion=False, write_original=True
    )
    assert no_suggestion.should_write_original is False

    no_flag = DeviceExtra(
        read_entity_id="input_number.x", ai_suggestion=True, write_original=False
    )
    assert no_flag.should_write_original is False

    sensor_source = DeviceExtra(
        read_entity_id="sensor.x", ai_suggestion=True, write_original=True
    )
    assert sensor_source.is_writable_helper is False
    assert sensor_source.should_write_original is False


def test_read_fields_extra_kind_follows_domain():
    ex_bool = DeviceExtra(read_entity_id="input_boolean.eco_modus", ai_suggestion=True)
    dev = Device("wallbox", "Wallbox", "wallbox", CONTROLLABLE, extras=(ex_bool,))
    field = {f.key: f for f in read_fields(dev)}["extra_eco_modus"]
    assert field.kind == "bool"
    assert field.capture_attrs == ()


def test_discover_from_hems_schema_classes_and_units():
    devices = {d.name: d for d in discover_from_hems_schema(HEMS_SCHEMA)}
    assert set(devices) == {"heizstab", "heizluefter_1", "wallbox_1"}  # "Global" übersprungen
    assert devices["heizstab"].device_class == CONTROLLABLE
    assert devices["heizstab"].output_unit == "watt"
    assert devices["heizluefter_1"].device_class == BINARY
    assert devices["wallbox_1"].device_class == CONTROLLABLE
    assert devices["wallbox_1"].output_unit == "ampere"


def test_discover_from_hems_schema_identity_uses_name_not_label_or_prefix():
    """Identität = technischer `name`; `label` nur Anzeige, `entity_prefix` fürs Entity-Mapping."""
    wallbox = {d.name: d for d in discover_from_hems_schema(HEMS_SCHEMA)}["wallbox_1"]
    assert wallbox.name == "wallbox_1"        # technische ID (deckt sich mit HEMS-`/api/status`-id)
    assert wallbox.label == "Wallbox"          # reiner Anzeigename
    assert wallbox.entity_prefix == "wallbox"  # bleibt am Entitätspräfix -> ems_wallbox_*
    # Ein Label-Rename ändert die Identität NICHT.
    renamed = dict(HEMS_SCHEMA[3], label="Wallbox Test")
    wb2 = discover_from_hems_schema([renamed])[0]
    assert wb2.name == "wallbox_1" and wb2.entity_prefix == "wallbox"


def test_discover_from_hems_schema_falls_back_to_prefix_without_name():
    """Ältere HEMS-Versionen ohne `name` im Schema: Identität = Entitätspräfix."""
    group = {k: v for k, v in HEMS_SCHEMA[3].items() if k != "name"}
    dev = discover_from_hems_schema([group])[0]
    assert dev.name == "wallbox"
    assert dev.entity_prefix == "wallbox"


def test_discover_from_hems_schema_skips_unidentifiable_group():
    schema = [{"label": "Komisch", "items": [{"entity": "input_number.ems_x_prioritat"}]}]
    assert discover_from_hems_schema(schema) == []


class _FakeHEMS:
    def __init__(self, schema=None, error=False):
        self._schema = schema
        self._error = error

    async def device_schema(self):
        if self._error:
            raise RuntimeError("HEMS nicht erreichbar")
        return self._schema


@pytest.mark.asyncio
async def test_discover_uses_hems_schema():
    devices, source = await discover(_FakeHEMS(schema=HEMS_SCHEMA))
    assert source == "hems"
    assert {d.name for d in devices} == {"heizstab", "heizluefter_1", "wallbox_1"}


@pytest.mark.asyncio
async def test_discover_none_when_hems_errors():
    # Kein Config-Fallback mehr (D-046): HEMS-Fehler => keine Geräte.
    devices, source = await discover(_FakeHEMS(error=True))
    assert source == "none"
    assert devices == []


@pytest.mark.asyncio
async def test_discover_none_when_hems_schema_has_no_devices():
    schema = [{"label": "Global", "items": [{"entity": "input_boolean.ems_pv_regelung_aktiv"}]}]
    devices, source = await discover(_FakeHEMS(schema=schema))
    assert source == "none"
    assert devices == []


@pytest.mark.asyncio
async def test_discover_none_without_hems():
    devices, source = await discover(None)
    assert source == "none"
    assert devices == []
