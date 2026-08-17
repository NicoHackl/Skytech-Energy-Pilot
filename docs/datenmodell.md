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
| ~~v9~~ | ~~`device_plan_state`~~ — mit Commit `e4d0706` zurückgebaut, Nummer bleibt **unbesetzt** |
| v10 | `ziele` (user-definierte Ziele, D-055) |
| v11 | `device_extras.rolle`-Spalte (`ist`/`grenze`/`sollwert`, D-061) + Backfill: Zusatzwerte mit KI-Vorschlag ⇒ `sollwert`, reine Lesewerte ⇒ `ist`, der namentlich bekannte Heizstab-Seed ⇒ `grenze` |
| v12 | `device_regeln` (Freitext-Betriebsregeln je Gerät, D-060; hausweite Regeln liegen als KV-Key `global_regeln` in `config`) |
| v13 | `plans.prompt`/`context_json`/`response_json`/`context_hash`/`publish_blocked` + `ai_calls.context_hash`/`sampling_dropped` (Nachvollziehbarkeit und Konfidenz-Gate, D-063/D-064) |

## Zentrale Tabellen (Zweck)

- **`config`** — generischer Key-Value-Store, genutzt für den editierbaren
  Planungs-Prompt, die **hausweiten Freitext-Regeln** (Key `global_regeln`, D-060) und den
  OneCall-Tagesbudget-Zähler ([settings.py](../app/energy_pilot/settings.py)).
- **`audit`** — jede sicherheitsrelevante Entscheidung/Änderung (Allowlist-Verstoß,
  Plan erstellt/verworfen, Vorschläge veröffentlicht, Budget erschöpft, …).
- **`errors`**, **`ai_calls`** — Fehler- bzw. KI-Aufruf-Historie. `ai_calls.context_hash`
  verknüpft einen Aufruf mit der Sachlage, `sampling_dropped` hält fest, dass der Anbieter
  `temperature`/`seed` verworfen hat (D-063).
- **`entity_map`** — größtenteils historisch; das aktuelle Rollen-Mapping kommt aus
  der `sensoren`-Config, nicht aus dieser Tabelle.
- **`allowlist`** — persistiertes Snapshot des erlaubten Lese-Entitäten-Registers.
- **`plans`** — jeder Planungslauf (Kandidat + Validierungsergebnis). Seit D-063 zusätzlich
  `prompt`, `context_json`, `response_json` und `context_hash` — ohne diese vier ist ein Lauf
  nachträglich nicht reproduzierbar und zwei Läufe sind nicht vergleichbar. `publish_blocked`
  hält den Grund, warum ein gültiger Plan nicht nach HA geschrieben wurde (D-064); ohne diese
  Spalte würde ein wiederverwendeter Plan das Gate umgehen.
- **`hems_feedback`** — Historie der Plan-vs-HEMS-Ist-Vergleiche (`plan_feedback.py`).
- **`device_extras`** — user-konfigurierte Zusatz-Entitäten je Gerät (D-047),
  inkl. `write_original`-Flag (D-052) und `rolle` (`ist`/`grenze`/`sollwert`, D-061).
- **`device_prompts`** — Pro-Gerät-KI-Beschreibung (D-051), `device_name` als PK.
- **`device_regeln`** — Pro-Gerät-Betriebsregeln als Freitext (D-060), `device_name` als PK.
  Abgrenzung zu `device_prompts`: dort steht, **was** ein Gerät ist, hier **was der User will**.
  Getrennt, weil der Prompt beides unterschiedlich adressiert und die KI ihre Entscheidung
  gegen die Regeln — nicht gegen die Beschreibung — begründen muss.
- **`ziele`** — user-definierte Ziele (D-055): `name`, `beschreibung`, `devices_json`
  (JSON-Array der Gerätenamen), `sort_order`. **Ohne** Gewicht — das leitet der
  Klassifizierungs-Aufruf je Planungslauf ab ([konfiguration.md](konfiguration.md#ziele-d-055-kein-addon-config-abschnitt-mehr)).

Bei neuen persistenten Feldern: **neue Migration anhängen**, nie eine bestehende
nachträglich ändern (SQLite-Migrationsketten sind additiv, existierende Installationen
haben bereits ältere Versionen angewendet). Aus demselben Grund wird die Lücke bei v9
**nicht** neu vergeben: Anlagen, die v9 damals angewendet haben, stehen bereits auf einer
höheren Version und würden eine neue v9 stillschweigend überspringen.
