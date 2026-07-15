# Datenmodell

SQLite, `PRAGMA journal_mode=WAL`. Migrationen sind eine handgerollte, versionierte
Liste (`database.py: MIGRATIONS`), Tracking über Tabelle `schema_migrations`,
`migrate()` wendet ausstehende Migrationen idempotent an.

## Migrationshistorie

| Version | Fügt hinzu |
|---|---|
| v1 | `config` (KV-Store), `audit`, `errors`, `ai_calls` |
| v2 | `entity_map` |
| v3 | `allowlist` |
| v4 | `plans` |
| v5 | `hems_feedback` |
| v6 | `device_extras` |
| v7 | `device_prompts` |
| v8 | `device_extras.write_original`-Spalte (ALTER TABLE) |

## Zentrale Tabellen (Zweck)

- **`config`** — generischer Key-Value-Store, genutzt für den editierbaren
  Planungs-Prompt und den OneCall-Tagesbudget-Zähler ([settings.py](../app/energy_pilot/settings.py)).
- **`audit`** — jede sicherheitsrelevante Entscheidung/Änderung (Allowlist-Verstoß,
  Plan erstellt/verworfen, Vorschläge veröffentlicht, Budget erschöpft, …).
- **`errors`**, **`ai_calls`** — Fehler- bzw. KI-Aufruf-Historie.
- **`entity_map`** — größtenteils historisch; das aktuelle Rollen-Mapping kommt aus
  der `sensoren`-Config, nicht aus dieser Tabelle.
- **`allowlist`** — persistiertes Snapshot des erlaubten Lese-Entitäten-Registers.
- **`plans`** — jeder Planungslauf (Kandidat + Validierungsergebnis).
- **`hems_feedback`** — Historie der Plan-vs-HEMS-Ist-Vergleiche (`plan_feedback.py`).
- **`device_extras`** — user-konfigurierte Zusatz-Entitäten je Gerät (D-047),
  inkl. `write_original`-Flag (D-052).
- **`device_prompts`** — Pro-Gerät-KI-Beschreibung (D-051), `device_name` als PK.

Bei neuen persistenten Feldern: **neue Migration anhängen**, nie eine bestehende
nachträglich ändern (SQLite-Migrationsketten sind additiv, existierende Installationen
haben bereits ältere Versionen angewendet).
