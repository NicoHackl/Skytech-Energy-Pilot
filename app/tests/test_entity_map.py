"""Tests für das Laden/Speichern der Entitätszuordnung."""

from energy_pilot.database import init_db
from energy_pilot.entity_map import (
    EntityMapping,
    load_mapping,
    mapping_from_options,
    save_mapping,
)


def test_save_and_load_roundtrip():
    conn = init_db(":memory:")
    save_mapping(conn, EntityMapping("pv_power", "sensor.pv"))

    mapping = load_mapping(conn)
    assert mapping["pv_power"].entity_id == "sensor.pv"
    conn.close()


def test_upsert_updates_existing():
    conn = init_db(":memory:")
    save_mapping(conn, EntityMapping("battery_soc", "sensor.alt"))
    save_mapping(conn, EntityMapping("battery_soc", "sensor.neu"))

    mapping = load_mapping(conn)
    assert len(mapping) == 1
    assert mapping["battery_soc"].entity_id == "sensor.neu"
    conn.close()


def test_mapping_from_options_reads_entities():
    values = {
        "entity_pv_power": "sensor.pv",
        "entity_house_load": "  ",  # nur Leerzeichen -> ignorieren
        "entity_grid_power": "",  # leer -> ignorieren
    }
    mapping = mapping_from_options(values)

    assert mapping["pv_power"].entity_id == "sensor.pv"
    # leere/whitespace-Einträge erzeugen keine Zuordnung
    assert "house_load" not in mapping
    assert "grid_power" not in mapping


def test_mapping_from_options_reads_nested_group():
    # Sensoren liegen in der aufklappbaren Gruppe "sensoren"
    values = {"sensoren": {"entity_house_load": "sensor.e3dc_leistung_haus"}}
    mapping = mapping_from_options(values)
    assert mapping["house_load"].entity_id == "sensor.e3dc_leistung_haus"
