# Entwicklerrichtlinien

> Sprachregeln (Code englisch, Text deutsch), Secrets-Verbot, Changelog- und Doku-Pflicht stehen in
> [`AGENTS.md`](../AGENTS.md) und werden hier **nicht** wiederholt. Git-Ablauf:
> [git-workflow.md](git-workflow.md). Tests: [test-strategie.md](test-strategie.md).

## Vor jeder Änderung

1. `user-beispiele/`-Dateien (`.txt`/`.md`) haben **immer** höchste Priorität — höher als diese
   Doku, höher als jede KI-generierte Aussage. Bei Widerspruch: Doku hier korrigieren, nicht
   `user-beispiele/`.
2. Passende Datei in `docs/` lesen, statt zu raten (siehe [README.md](README.md)).
3. [bekannte-luecken.md](bekannte-luecken.md) prüfen — mehrere Spec-Aussagen sind noch nicht
   implementiert.

## Naming

| Element | Konvention | Beispiel |
|---|---|---|
| Variablen, Funktionen | `snake_case`, englisch | `build_constraints` |
| Klassen, Typen | `PascalCase` | `DeviceCollector` |
| Konstanten | `UPPER_SNAKE_CASE` | `DEFAULT_BINARY_POWER_W` |
| Dateien / Module | `snake_case.py` | `suggestion_publisher.py` |
| Booleans | Frage-Präfix `is_` / `has_` / `can_` / `should_` | `should_write_original` |
| Private Helfer | führender Unterstrich | `_clamp_field` |
| HA-Entitäten / Helfer | **deutsch**, Umlaute ä/ö/ü → a/o/u | `ems_heizstab_technische_freigabe` |

Für HA-Entitäten gilt zusätzlich das nicht verhandelbare Präfix-Schema `ems_*`/`ep_*` nach
Datenrichtung — siehe [namensschema.md](namensschema.md).

Abkürzungen nur, wenn sie in der Domäne etabliert sind (`ep`, `hems`, `soc`, `pv`).

## Projektstruktur

```text
Skytech-Energy-Pilot/
├── app/
│   ├── main.py                # Bootstrapping: baut alle Komponenten zusammen
│   ├── energy_pilot/          # Produktivcode, eine Datei = eine Verantwortlichkeit
│   │   └── web/server.py      # aiohttp-App-Factory + alle HTTP-Endpunkte
│   └── tests/                 # ein Testfile je Quellmodul
├── frontend/                  # React-Oberfläche (Vite), dist/ wird mitcommittet
├── docs/                      # diese Doku
├── translations/              # HA-Formularbeschriftungen de/en
├── claude-ha-config-dateien/  # fertige <domain>_ep.yaml-Helfer-Pakete für den User
└── user-beispiele/            # Vorlagen des Users — höchste Priorität
```

Eine Datei hat **eine** Verantwortlichkeit. Wächst sie über ~400 Zeilen, ist das ein Prüfanlass —
`web/server.py` ist die bewusst geduldete Ausnahme (Endpunkt-Sammelstelle).

## Kommentare

- Kommentare erklären das **Warum**, nicht das Was.
- Öffentliche Funktionen bekommen einen deutschen Docstring: Zweck, Besonderheiten, Fehlerfälle.
- Auskommentierter Code wird **gelöscht**. Dafür gibt es Git.
- `TODO` bekommt einen Verweis (`# TODO(D-021): …`). Ein namenloses `TODO` wird nie erledigt.
- Verweise auf Doku-Dateien immer als Pfad unter `docs/` — nie auf die 2026-07-10 gelöschten
  Dateien `info.md`, `plan/*.md`, `user-regeln.md`, `user-fragen.md` (Löschung: Commit `ad48b23`).
  Taucht so ein toter Verweis auf, wird er ersetzt oder entfernt, nicht stehen gelassen.

## Fehlerbehandlung

Leitprinzip des Projekts (eiserne Regel „Fallback"): **EP blockiert nie die Anlage.** Daraus folgt
ein Muster, das im Code durchgängig auftaucht und beim Erweitern beibehalten wird:

- DB-Schreibfehler werden gefangen (`except sqlite3.Error: pass` mit Kommentar), nie propagiert.
- Ein Allowlist-Verstoß wird geloggt und auditiert, aber **nicht** blockiert.
- Provider-Fehler fängt der `Planner` vollständig ab; ein fehlgeschlagener Lauf liefert
  `ok=false`, wirft aber nie an den Aufrufer.
- Externe Aufrufe (HA, HEMS, KI, OpenWeatherMap) haben ein explizites Timeout. `asyncio.TimeoutError`
  ist seit Python 3.11 identisch mit `TimeoutError` und **kein** `aiohttp.ClientError` — ein
  eigener `except TimeoutError`-Zweig mit sprechender Meldung ist Pflicht, sonst landet eine leere
  Fehlermeldung im Log.
- Kein leerer `except`-Block ohne Kommentar, der die Absicht benennt.

Fehlermeldungen für den User: deutsch, konkret, mit Handlungsanweisung. Technische Details ins Log,
nicht in die UI.

## Logging

Strukturiertes JSON über `logging_setup.py`, mit Ringpuffer für die UI und JSONL-Export.

| Level | Wofür |
|---|---|
| `DEBUG` | Entwicklungsdetails, im Normalbetrieb aus |
| `INFO` | Zustandsübergänge, Start/Stop, abgeschlossene Vorgänge |
| `WARNING` | Unerwartet, aber automatisch behandelt (z. B. HEMS nicht erreichbar) |
| `ERROR` | Vorgang fehlgeschlagen, Eingriff nötig |

Nie geloggt werden Schlüssel, Tokens und Zugangsdaten — `SECRET_KEYS` redigiert sie automatisch,
`http_errors.py` loggt nur Pfade statt vollständiger URLs mit Query-String. Siehe
[sicherheit-datenschutz.md](sicherheit-datenschutz.md).

## Abhängigkeiten

- Neue Abhängigkeit nur, wenn sie mehr Aufwand spart, als sie an Wartung kostet. Alle HTTP-Clients
  des Projekts (HA, HEMS, Gemini, Claude, OpenAI, OpenWeatherMap) sind bewusst schlanke
  aiohttp-Aufrufe **ohne** SDK.
- Versionen werden in `app/requirements.txt` bzw. `frontend/package.json` gepflegt.
- Eine neue Laufzeit-Abhängigkeit ist eine Design-Entscheidung → Eintrag in
  [design-entscheidungen.md](design-entscheidungen.md).

## Formatierung

`ruff check app` mit `line-length = 100` und den Regelgruppen `E`, `F`, `I`, `W`, `UP`, `B`
(`pyproject.toml`). Manuelles Abweichen vom Linter ist kein zulässiger Diff-Inhalt.

## Neue Geräte, Zusatz-Entitäten oder Config-Optionen hinzufügen

1. **Neues Config-Feld:** immer gemeinsam in `config.py: DEFAULTS`, `config.yaml` (`options:` **und**
   `schema:`) sowie `translations/de.yaml` **und** `translations/en.yaml` pflegen. Diese vier müssen
   deckungsgleich bleiben — `DEFAULTS` ist 1:1 identisch mit dem `options:`-Block.
2. **Neue DB-Spalte oder Tabelle:** neue Migration in `database.py: MIGRATIONS` **anhängen**, nie
   eine bestehende ändern und nie eine freigewordene Nummer neu vergeben
   ([datenmodell.md](datenmodell.md)).
3. **Neue Geräteklasse oder Zusatz-Entity-Typ:** prüfen, ob `devices.py: _DOMAIN_KIND` und
   `plan_schema.py: suggestion_keys()` den neuen Fall abdecken.
