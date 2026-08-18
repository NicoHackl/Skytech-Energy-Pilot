"""SQLite-Initialisierung mit einfachem, versioniertem Migrations-Mechanismus.

Vollständiges Schema siehe docs/datenmodell.md. M0 legt nur die Kerntabellen plus die
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
    (
        11,
        # Semantische Rolle je Zusatzwert (D-061): ist | grenze | sollwert. Backfill ohne Raten:
        # liefert die KI für einen Zusatzwert einen Vorschlag, ist der Wert per Definition eine
        # Vorgabe und kein Messwert => `sollwert`; reine Lesewerte sind `ist`. Der frühere
        # Heizstab-Seed (D-035) ist namentlich bekannt und damit eindeutig eine `grenze`.
        """
        ALTER TABLE device_extras ADD COLUMN rolle TEXT NOT NULL DEFAULT 'ist';
        UPDATE device_extras SET rolle = 'sollwert' WHERE ai_suggestion = 1;
        UPDATE device_extras SET rolle = 'grenze'
            WHERE read_entity_id = 'input_number.ep_heizstab_max_temperatur';
        """,
    ),
    (
        12,
        # Freitext-Regeln je Gerät (D-060): die vom User formulierte Betriebsabsicht. Geht als
        # eigener, im Prompt referenzierter Block in den KI-Kontext — nicht als weiteres Feld im
        # Datenrauschen. Hausweite Regeln liegen im KV-Store (`config`), nicht hier.
        """
        CREATE TABLE IF NOT EXISTS device_regeln (
            device_name TEXT PRIMARY KEY,
            regeln TEXT NOT NULL DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        13,
        # Nachvollziehbarkeit eines Planungslaufs (D-063): ohne Prompt, Kontext und Roh-Antwort
        # ist ein Lauf nicht reproduzierbar und zwei Läufe sind nicht vergleichbar.
        # `context_hash` ist der Fingerabdruck des quantisierten Kontexts.
        """
        ALTER TABLE plans ADD COLUMN prompt TEXT;
        ALTER TABLE plans ADD COLUMN context_json TEXT;
        ALTER TABLE plans ADD COLUMN response_json TEXT;
        ALTER TABLE plans ADD COLUMN context_hash TEXT;
        ALTER TABLE plans ADD COLUMN publish_blocked TEXT;
        ALTER TABLE ai_calls ADD COLUMN context_hash TEXT;
        ALTER TABLE ai_calls ADD COLUMN sampling_dropped INTEGER NOT NULL DEFAULT 0;
        """,
    ),
    (
        14,
        # Tages-Rückblick je Messgröße (D-065). Löst das offene D-012 ein („Datenspeicherung von
        # Anfang an auf Aggregation ausgelegt"): der RollingAggregator reicht 60 Minuten weit und
        # ist nach einem Neustart leer, für eine Tagesbilanz braucht es Tage. Die Tabelle wird
        # aus der HA-Historie befüllt und wächst danach über die Recorder-Aufbewahrung hinaus.
        # `vollstaendig` markiert einen abgeschlossenen Kalendertag — nur unvollständige Tage
        # werden erneut aus HA geholt.
        """
        CREATE TABLE IF NOT EXISTS daily_history (
            tag TEXT NOT NULL,
            groesse TEXT NOT NULL,
            entity_id TEXT NOT NULL DEFAULT '',
            wert_min REAL,
            wert_max REAL,
            wert_mittel REAL,
            wert_delta REAL,
            energie_kwh REAL,
            proben INTEGER NOT NULL DEFAULT 0,
            vollstaendig INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (tag, groesse)
        );
        """,
    ),
    (
        15,
        # Wärmespeicher-Kennwerte je Gerät (D-066): Volumen in Liter plus Komfortminimum und
        # optionaler Zielwert in °C. Anlagendaten und eine Anforderung — **keine**
        # Entscheidungsregel: erst damit lässt sich der Speicherinhalt in kWh ausdrücken und
        # die Frage „reicht es die nächsten Tage?" rechnen statt schätzen.
        """
        CREATE TABLE IF NOT EXISTS device_speicher (
            device_name TEXT PRIMARY KEY,
            volumen_liter REAL,
            komfort_min_c REAL,
            ziel_c REAL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        16,
        # Aufräumen nach dem Wegfall der Mess-Rolle `grid_power` („Netzleistung"): `grid_import`
        # und `grid_export` tragen dieselbe Information richtungsrein. Der Rückblick filtert
        # entfernte Größen inzwischen selbst (history_collector), aber die alten Zeilen sollen
        # auch nicht als toter Ballast liegen bleiben.
        """
        DELETE FROM daily_history WHERE groesse = 'grid_power';
        DELETE FROM entity_map WHERE role = 'grid_power';
        """,
    ),
    (
        17,
        # Werte mit der semantischen Rolle `grenze` gehören ausschließlich dem User. Frühere
        # Versionen konnten dafür widersprüchlich KI- und Original-Schreibflags speichern.
        """
        UPDATE device_extras
        SET ai_suggestion = 0, write_original = 0, updated_at = datetime('now')
        WHERE rolle = 'grenze';
        INSERT OR IGNORE INTO device_extras (
            device_name, read_entity_id, ai_suggestion, ai_hint, label, unit,
            sort_order, updated_at, write_original, rolle
        )
        SELECT device_name, 'input_number.e3dc_heizstab_maxtemperatur', 0, ai_hint, label, unit,
               sort_order, datetime('now'), 0, 'grenze'
        FROM device_extras
        WHERE device_name = 'heizstab'
          AND read_entity_id = 'input_number.ep_heizstab_max_temperatur';
        DELETE FROM device_extras
        WHERE device_name = 'heizstab'
          AND read_entity_id = 'input_number.ep_heizstab_max_temperatur';
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
