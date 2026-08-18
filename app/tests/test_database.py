"""Tests für SQLite-Initialisierung und Migrationen."""

from energy_pilot.database import MIGRATIONS, connect, current_version, init_db, migrate


def test_migrations_create_core_tables(tmp_path):
    conn = init_db(str(tmp_path / "ep.db"))
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    expected = {
        "config", "audit", "errors", "ai_calls", "entity_map", "allowlist", "plans",
        "hems_feedback", "device_extras", "device_prompts", "device_regeln",
        "daily_history", "device_speicher",
        "ziele", "schema_migrations",
    }
    assert expected <= tables
    assert current_version(conn) == 17
    conn.close()


def test_migrations_are_idempotent(tmp_path):
    db_path = str(tmp_path / "ep.db")
    init_db(db_path).close()

    conn = init_db(db_path)
    # Zweiter Lauf wendet keine Migration erneut an
    assert migrate(conn) == []
    conn.close()


def test_in_memory_database_works():
    conn = init_db(":memory:")
    assert current_version(conn) == 17
    conn.close()


def test_migration_17_disables_limit_suggestions_and_moves_heater_limit():
    conn = connect(":memory:")
    current_version(conn)
    for version, sql in MIGRATIONS:
        if version >= 17:
            break
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
    conn.execute(
        "INSERT INTO device_extras "
        "(device_name, read_entity_id, ai_suggestion, write_original, rolle) "
        "VALUES ('heizstab', 'input_number.ep_heizstab_max_temperatur', 1, 1, 'grenze')"
    )
    conn.commit()

    assert migrate(conn) == [17]
    row = conn.execute(
        "SELECT * FROM device_extras WHERE device_name = 'heizstab'"
    ).fetchone()
    assert row["read_entity_id"] == "input_number.e3dc_heizstab_maxtemperatur"
    assert row["ai_suggestion"] == 0
    assert row["write_original"] == 0
