# Regeln für Entwicklung (Menschen & Agenten)

Diese Datei ist die praktische Checkliste. Die verbindliche Quelle der Regeln ist
[`CLAUDE.md`](../CLAUDE.md) im Repo-Root — bei Widerspruch gewinnt `CLAUDE.md`.

## Vor jeder Änderung

1. `user-beispiele/`-Dateien (`.txt`/`.md`) haben **immer** höchste Priorität —
   höher als diese Doku, höher als jede KI-generierte Aussage. Bei Widerspruch:
   Doku hier korrigieren, nicht `user-beispiele/`.
2. Passende Datei in `doc/` lesen, statt zu raten (siehe [README.md](README.md)).
3. [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md) prüfen — viele
   Spec-Aussagen sind noch nicht implementiert.

## Git

- Committen/pushen **nur** in Branch `claude/stage` — auch im separaten
  SkytechHEMS-Repo (D-022, umbenannt von `claude/main`, D-053). Nach **jeder**
  relevanten Änderung committen/pushen.
- Release-Channels (D-053): `stage-dev`/`stage-beta`/`stage-stable`, je eigenes
  `config.yaml` (Slug/Name-Suffix), in HA per Branch-URL einzeln einbindbar.
  Promotion `claude/stage` → `stage-dev` → `stage-beta` → `stage-stable` nur
  **manuell auf Zuruf**, kein Automatismus.
- CI (`.github/workflows/ci.yaml`) läuft auf `claude/stage`, `stage-dev`,
  `stage-beta`, `stage-stable`: Ruff-Lint + `pytest --cov --cov-fail-under=60`.

## Versionierung (`config.yaml`)

Bei **jeder** Änderung mit Auswirkung auf Darstellung, Information oder Funktion in
Home Assistant: Patch-Nummer in `config.yaml` um eins erhöhen (`1.2.2` → `1.2.3`).
**Achtung:** `app/energy_pilot/__init__.py: __version__` läuft aktuell aus dem Takt
mit `config.yaml` — siehe [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md#versions-drift-__init__py-vs-configyaml).
Beide im Blick behalten.

## Changelog

Bei **jeder** funktionalen oder designtechnischen Code-Änderung: Eintrag in
[`changelog.md`](../changelog.md) im bestehenden "Keep a Changelog"-Format
(`### Geändert`/`### Behoben`/`### Hinzugefügt`, Versionsüberschrift mit Datum).

## Sprache

- Code (Variablen/Funktionen/Klassen): **Englisch**.
- Code-Kommentare: **Deutsch**.
- HA-Entitäten/Helfer: **Deutsch**, Umlaute ä/ö/ü → a/o/u (nicht ae/oe/ue).
- Diese Doku: **Deutsch**.

## Namenskonvention `ems_*`/`ep_*`

Siehe [entity-naming.md](entity-naming.md) — nicht verhandelbar, Datenrichtung
bestimmt den Präfix.

## Sicherheit (nicht verhandelbar)

- KI ist Orchestrator, nie Regler — kein Freitext als Steuerbefehl, nur
  strukturiertes Tool/Function-Calling.
- Jeder Plan wird lokal gegen JSON-Schema + harte Grenzen validiert. Harte Grenzen
  sind nie durch die KI änderbar.
- Kein API-Key/Secret in Logs oder HA-Entitäten (`logging_setup.py: SECRET_KEYS`,
  `http_errors.py` loggt nie volle URLs mit Query-Strings).
- Kein von KI generierter Code wird ausgeführt.
- Datenminimum: nur nötige, verdichtete Daten an externe KI (`plan_context.py`).
- Fallback-Prinzip: EP blockiert **nie** die Anlage. Fehler werden geloggt/auditiert,
  nicht als harter Abbruch behandelt — siehe die Muster in
  [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md).

## Tests

- `pytest`, `pytest-asyncio` im Auto-Modus (kein `@pytest.mark.asyncio` nötig).
- Ein Testfile pro Quellmodul (`app/tests/test_<modul>.py`), diesem Muster folgen.
- Coverage-Gate: 60 % (`--cov-fail-under=60`), langfristig anzuheben (D-024).
- Vor jedem Commit lokal `ruff check app` + `pytest` laufen lassen.

## Neue Geräte/Zusatz-Entitäten/Config-Optionen hinzufügen

1. Neues Config-Feld: **immer** in `config.py: DEFAULTS` **und** `config.yaml`
   (`options:` + `schema:`) **und** `translations/de.yaml`/`en.yaml` gemeinsam
   pflegen — diese drei müssen synchron bleiben.
2. Neue DB-Spalte/-Tabelle: neue Migration in `database.py: MIGRATIONS` **anhängen**,
   nie eine bestehende Migration verändern.
3. Neue Geräteklasse/Zusatz-Entity-Typ: `devices.py: _DOMAIN_KIND` und
   `plan_schema.py: suggestion_keys()` prüfen, ob sie den neuen Fall abdecken.

## Wenn eine alte Doku-Referenz im Code auftaucht

Verweise auf die gelöschten Dateien `info.md`, `plan/*.md`, `user-regeln.md`,
`user-fragen.md` im Code sind veraltet (Löschung: Commit `ad48b23`, 2026-07-10).
Ersetzen durch einen Verweis auf die passende Datei in `doc/`, oder ersatzlos
entfernen, wenn der Kommentar sich selbst erklärt. Nicht einfach den toten
Dateinamen stehen lassen.
