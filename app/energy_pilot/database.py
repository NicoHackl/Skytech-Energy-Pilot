"""SQLite-Initialisierung mit einfachem, versioniertem Migrations-Mechanismus.

Vollständiges Schema siehe doc/data-model.md. M0 legt nur die Kerntabellen plus die
Migrationsverwaltung an; weitere Tabellen folgen versioniert.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Migrationen in aufsteigender Reihenfolge. Jede Version wird genau einmal angewendet.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            actor TEXT,
            action TEXT,
            subject TEXT,
            detail_json TEXT
        );
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            level TEXT,
            component TEXT,
            message TEXT,
            detail_json TEXT
        );
        CREATE TABLE IF NOT EXISTS ai_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            provider TEXT,
            model TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            est_cost REAL,
            ok INTEGER,
            error TEXT
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS entity_map (
            role TEXT PRIMARY KEY,
            ha_entity_id TEXT,
            fallback_value REAL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS allowlist (
            entity_id TEXT PRIMARY KEY,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        4,
        """
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            plan_id TEXT,
            valid_from TEXT,
            valid_until TEXT,
            ok INTEGER,
            provider TEXT,
            model TEXT,
            confidence INTEGER,
            plan_json TEXT,
            errors_json TEXT,
            clamped_json TEXT
        );
        """,
    ),
    (
        5,
        """
        CREATE TABLE IF NOT EXISTS hems_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            plan_id TEXT,
            hems_online INTEGER,
            plan_status TEXT,
            detail_json TEXT
        );
        """,
    ),
    (
        6,
        """
        CREATE TABLE IF NOT EXISTS device_extras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_name TEXT NOT NULL,
            read_entity_id TEXT NOT NULL,
            ai_suggestion INTEGER NOT NULL DEFAULT 0,
            ai_hint TEXT DEFAULT '',
            label TEXT DEFAULT '',
            unit TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(device_name, read_entity_id)
        );
        """,
    ),
    (
        7,
        """
        CREATE TABLE IF NOT EXISTS device_prompts (
            device_name TEXT PRIMARY KEY,
            prompt TEXT NOT NULL DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        8,
        """
        ALTER TABLE device_extras ADD COLUMN write_original INTEGER NOT NULL DEFAULT 0;
        """,
    ),
    # Lücke: Version 9 (`device_plan_state`, Anti-Flatter-Zustand aus dem Stabilitäts-Kern)
    # wurde mit Commit e4d0706 zurückgebaut. Die Nummer bleibt bewusst unbesetzt — die Kette ist
    # additiv, und Anlagen, die 9 bereits angewendet haben, stehen schon auf einer höheren
    # Version. Eine Neuvergabe würde bei genau diesen Anlagen still übersprungen.
    (
        10,
        # User-definierte Ziele (D-055): ersetzen die statischen `objective_weights` aus der
        # Addon-Config. Ein vorgelagerter Klassifizierungs-Aufruf leitet daraus je Planungslauf
        # die Gewichtung ab (siehe planner.py). `devices_json` = JSON-Array der Gerätenamen.
        """
        CREATE TABLE IF NOT EXISTS ziele (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            beschreibung TEXT NOT NULL DEFAULT '',
            devices_json TEXT NOT NULL DEFAULT '[]',
            sort_order INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """,
    ),
]


def connect(db_path: str) -> sqlite3.Connection:
    """Öffnet (und legt bei Bedarf an) die SQLite-Datenbank."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    """Liefert die zuletzt angewendete Migrationsversion (0, falls keine)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))"
    )
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] or 0


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Wendet alle ausstehenden Migrationen an und gibt deren Versionen zurück."""
    version = current_version(conn)
    applied: list[int] = []
    for migration_version, sql in MIGRATIONS:
        if migration_version > version:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (migration_version,)
            )
            applied.append(migration_version)
    conn.commit()
    return applied


def init_db(db_path: str) -> sqlite3.Connection:
    """Öffnet die Datenbank und bringt das Schema auf den aktuellen Stand."""
    conn = connect(db_path)
    migrate(conn)
    return conn
