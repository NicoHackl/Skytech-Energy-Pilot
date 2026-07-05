"""Tests für die Entity Allowlist (Register, Soft-Guard, Persistenz)."""

import io

from energy_pilot.allowlist import (
    SOURCE_DEVICE,
    SOURCE_FORECAST,
    SOURCE_MEASUREMENT,
    EntityAllowlist,
    collect_entity_ids,
)
from energy_pilot.database import init_db
from energy_pilot.devices import Device
from energy_pilot.entity_map import EntityMapping
from energy_pilot.forecast import PVOrientation
from energy_pilot.logging_setup import setup_logging


def test_collect_entity_ids_from_all_sources():
    mapping = {"pv_power": EntityMapping("pv_power", "sensor.pv")}
    orientations = [PVOrientation("Ost", {"current_hour": "sensor.ost"})]
    devices = [Device("heizstab", "Heizstab", "heizstab", "controllable")]

    result = collect_entity_ids(mapping=mapping, orientations=orientations, devices=devices)

    assert result["sensor.pv"] == SOURCE_MEASUREMENT
    assert result["sensor.ost"] == SOURCE_FORECAST
    # Geräte-IDs stammen aus dem zentralen Read-Schema (read_fields), nicht doppelt gepflegt.
    assert result["input_boolean.ems_heizstab_technische_freigabe"] == SOURCE_DEVICE
    assert result["input_number.ems_heizstab_max_technisch_w"] == SOURCE_DEVICE


def test_collect_entity_ids_skips_mapping_without_entity():
    # Keine HA-Entität gesetzt -> nichts freizugeben.
    mapping = {"pv_power": EntityMapping("pv_power", None)}
    assert collect_entity_ids(mapping=mapping) == {}


def test_rebuild_replaces_register_and_drops_stale_device_ids():
    # HEMS-Sync (D-046): rebuild ersetzt vollständig; ein umbenanntes Gerät verliert
    # seine alten ems_*-Entitäten, die neuen kommen rein (anders als das additive register_all).
    allow = EntityAllowlist()
    allow.register_all(
        collect_entity_ids(devices=[Device("heizstab", "Heizstab", "heizstab", "controllable")])
    )
    assert allow.is_allowed("input_boolean.ems_heizstab_technische_freigabe")

    allow.rebuild(
        collect_entity_ids(devices=[Device("heizstab", "Heizstab", "warmwasser", "controllable")])
    )
    assert not allow.is_allowed("input_boolean.ems_heizstab_technische_freigabe")
    assert allow.is_allowed("input_boolean.ems_warmwasser_technische_freigabe")


def test_is_allowed_after_register():
    allow = EntityAllowlist()
    allow.register_all({"sensor.pv": SOURCE_MEASUREMENT})
    assert allow.is_allowed("sensor.pv")
    assert not allow.is_allowed("sensor.unbekannt")


def test_check_allowed_has_no_side_effects():
    conn = init_db(":memory:")
    logger, _ = setup_logging("DEBUG", stream=io.StringIO())
    allow = EntityAllowlist(conn, logger)
    allow.register_all({"sensor.pv": SOURCE_MEASUREMENT})

    assert allow.check("sensor.pv") is True
    assert conn.execute("SELECT COUNT(*) AS n FROM audit").fetchone()["n"] == 0
    conn.close()


def test_check_violation_logs_and_audits_once():
    conn = init_db(":memory:")
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    allow = EntityAllowlist(conn, logger)

    assert allow.check("sensor.verboten") is False
    # Zweiter Aufruf darf nicht erneut auditieren/loggen (Drosselung).
    assert allow.check("sensor.verboten") is False

    rows = conn.execute(
        "SELECT subject FROM audit WHERE action = 'allowlist_violation'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["subject"] == "sensor.verboten"
    assert any(r["level"] == "WARNING" for r in ring.records())
    conn.close()


def test_persist_writes_rows_and_rebuild_audit():
    conn = init_db(":memory:")
    allow = EntityAllowlist(conn)
    allow.register_all({"sensor.pv": SOURCE_MEASUREMENT, "sensor.ost": SOURCE_FORECAST})

    allow.persist()

    rows = {
        r["entity_id"]: r["source"]
        for r in conn.execute("SELECT entity_id, source FROM allowlist")
    }
    assert rows == {"sensor.pv": SOURCE_MEASUREMENT, "sensor.ost": SOURCE_FORECAST}
    rebuilt = conn.execute(
        "SELECT COUNT(*) AS n FROM audit WHERE action = 'allowlist_rebuilt'"
    ).fetchone()["n"]
    assert rebuilt == 1
    conn.close()


def test_persist_replaces_previous_register():
    conn = init_db(":memory:")
    first = EntityAllowlist(conn)
    first.register_all({"sensor.alt": SOURCE_MEASUREMENT})
    first.persist()

    second = EntityAllowlist(conn)
    second.register_all({"sensor.neu": SOURCE_MEASUREMENT})
    second.persist()

    ids = {r["entity_id"] for r in conn.execute("SELECT entity_id FROM allowlist")}
    assert ids == {"sensor.neu"}
    conn.close()


def test_snapshot_shape_is_sorted_and_counted():
    allow = EntityAllowlist()
    allow.register_all({"sensor.pv": SOURCE_MEASUREMENT, "sensor.ost": SOURCE_FORECAST})

    snap = allow.snapshot()

    assert snap["count"] == 2
    assert snap["by_source"][SOURCE_MEASUREMENT] == 1
    assert snap["by_source"][SOURCE_FORECAST] == 1
    # Einträge alphabetisch sortiert (sensor.ost < sensor.pv).
    assert [e["entity_id"] for e in snap["entries"]] == ["sensor.ost", "sensor.pv"]


def test_persist_without_connection_is_noop():
    # Ohne DB-Verbindung darf persist nicht crashen (z.B. in Tests).
    EntityAllowlist().persist()
