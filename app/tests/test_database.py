"""Tests für SQLite-Initialisierung und Migrationen."""

from energy_pilot.database import current_version, init_db, migrate


def test_migrations_create_core_tables(tmp_path):
    conn = init_db(str(tmp_path / "ep.db"))
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    expected = {
        "config", "audit", "errors", "ai_calls", "entity_map", "allowlist", "plans",
        "hems_feedback", "device_extras", "schema_migrations",
    }
    assert expected <= tables
    assert current_version(conn) == 6
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
    assert current_version(conn) == 6
    conn.close()
