"""Tests für das Laden/Speichern der Entitätszuordnung."""

from energy_pilot.database import init_db
from energy_pilot.entity_map import EntityMapping, load_mapping, save_mapping


def test_save_and_load_roundtrip():
    conn = init_db(":memory:")
    save_mapping(conn, EntityMapping("pv_power", "sensor.pv", fallback_value=0.0))

    mapping = load_mapping(conn)
    assert mapping["pv_power"].entity_id == "sensor.pv"
    assert mapping["pv_power"].fallback_value == 0.0
    conn.close()


def test_upsert_updates_existing():
    conn = init_db(":memory:")
    save_mapping(conn, EntityMapping("battery_soc", "sensor.alt", 10.0))
    save_mapping(conn, EntityMapping("battery_soc", "sensor.neu", 20.0))

    mapping = load_mapping(conn)
    assert len(mapping) == 1
    assert mapping["battery_soc"].entity_id == "sensor.neu"
    assert mapping["battery_soc"].fallback_value == 20.0
    conn.close()
