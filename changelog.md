# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jeder funktionalen oder
designtechnischen Code-Änderung um eine Patch-Stelle erhöht (Projektregel 2).

## [0.0.15] - 2026-06-19

### Geändert
- **Prioritäten als erzwungene Rangfolge (statt weicher Prompt-Bitte):** Der Validator
  normalisiert `prio_vorschlag` jetzt geräteübergreifend auf eine eindeutige, lückenlose
  10er-Rangfolge (10 = höchste, dann 20, 30 …). Die KI-Werte gelten nur als **relative
  Reihenfolge**; nicht-konforme Werte (Duplikate, Lücken, >100, Nicht-Vielfache) werden
  auf gültige Ränge geklemmt und als `clamped` protokolliert — der Plan wird dadurch nie
  abgelehnt (Iron Rule 6/8). Die Batterie bleibt außen vor (kein `prio_vorschlag`, D-037).
  Betroffen: [validator.py](app/energy_pilot/validator.py) (neue Normalisierung),
  [plan_schema.py](app/energy_pilot/plan_schema.py) (Prio bewusst nur strukturell),
  [plan_context.py](app/energy_pilot/plan_context.py) (Prompt entwidersprochen — Rangfolge
  gilt für alle Geräte außer der Batterie; Tippfehler bereinigt; `prio_vorschlag`-
  Beschreibung im Antwortschema). Regressionstests ergänzt.

## [0.0.14] - 2026-06-19

### Geändert
- **KI-Prompt – Prioritäten-Regel präzisiert:** Die Rangfolge muss bei 10 beginnen und
  in 10er-Schritten aufsteigen (10, 20, 30 …). Versionsnummer nachgezogen.

## [0.0.13] - 2026-06-19

### Hinzugefügt
- **KI-Prompt – Prioritäten-Regel:** Geräte-Prioritäten nur in 10er-Schritten von 10–100
  (10 = höchste, 100 = niedrigste). Zunächst nur als Prompt-Vorgabe — ab 0.0.15
  deterministisch im Validator erzwungen.

## [0.0.12] - 2026-06-19

### Behoben
- **„KI-Planung fehlgeschlagen" mit leerer Fehlermeldung (`"error": ""`):** Lief der
  Gemini-Aufruf in den Timeout (Default 30 s), warf aiohttp `asyncio.TimeoutError` —
  in Python 3.11 identisch mit `TimeoutError` und **kein** `aiohttp.ClientError`, also
  vom Provider nicht gefangen. Die Exception propagierte bis in den Planner; weil
  `str(TimeoutError())` leer ist, landete eine **leere** Meldung in Log, UI und
  `ai_calls`. Der Provider fängt den Timeout jetzt ab und meldet ihn klar als
  „Gemini-Zeitüberschreitung nach 30s" ([gemini_provider.py](app/energy_pilot/gemini_provider.py)).
  Zusätzlich liefert der Planner als Sicherheitsnetz nie mehr einen leeren Fehlertext,
  sondern fällt auf den Exception-Klassennamen zurück
  ([planner.py](app/energy_pilot/planner.py), Iron Rule 8). Regressionstests ergänzt.

## [0.0.11] - 2026-06-19

### Hinzugefügt
- **KI-Planung (Vorschlagswerte, M2):** EP erzeugt jetzt über Google Gemini einen
  validierten, begründeten Kandidatenplan. Austauschbares Provider-Interface
  (`AIProvider`) mit Gemini-Anbindung per REST/aiohttp (kein SDK), **Single-Shot**
  mit strukturiertem JSON (`responseSchema`) und Rate-Limit-Drossel (Default 10/min,
  Wartedrossel statt Fehlerflut). Der verdichtete Kontext (Zustand, PV-Prognose,
  harte Grenzen, Zielgewichte) geht als **Datenminimum** an die KI; diese liefert
  nur Geräte-Vorschläge, Konfidenz, Begründung und Warnungen — die Plan-Metadaten
  (ID, Gültigkeit, Provider/Modell) setzt EP selbst. Jeder Plan durchläuft das
  bestehende lokale Sicherheits-Gate (`validator.py`); es wird **nichts** an HEMS
  übergeben oder ausgeführt (D-008/D-041). Module `ai_provider.py`,
  `gemini_provider.py`, `plan_context.py`, `planner.py`.
- **Endpunkte & UI:** `POST /api/plan/run` (Lauf auslösen), `GET /api/plan`
  (letzter Plan), `GET /api/ai/test` (KI-Verbindungstest) und ein neuer „Plan"-Tab
  mit Geräte-Vorschlägen, Validierungsstatus, Begründung/Warnungen und einer
  aufklappbaren Ansicht der **an die KI gesendeten Daten** (Transparenz).
- **Protokollierung & Config:** KI-Aufrufe (Tokens) in `ai_calls`, Pläne in neuer
  Tabelle `plans` (DB-Migration v4), jede Entscheidung als `audit`-Eintrag
  (`plan_created`/`plan_rejected`). Neue Addon-Optionen `api_key` (maskiert,
  Schema-Typ `password`), `ai_request_timeout_s`, `ai_rate_limit_per_min`.

### Geändert
- Paket-Version (`app/energy_pilot/__init__.py`) auf den Stand der Addon-Version
  gebracht (war 0.0.9 → 0.0.11), damit Statusseite/Logs die korrekte Version zeigen.

## [0.0.10] - 2026-06-19

### Behoben
- **Grenzen & Ziele zeigten bei Binärgeräten Min./Max. Leistung:** Im Reiter
  „Grenzen & Ziele" wurden für Binärverbraucher fälschlich „Min. Leistung" und
  „Max. Leistung" angezeigt (und jedes Gerät als „(binär)" beschriftet) statt
  der festen Leistung. Ursache war ein Schlüssel-Mismatch im JSON-Vertrag:
  `/api/constraints` serialisierte die Geräteklasse über `asdict()` als
  `device_class`, während das UI (`loadConstraints`) sie unter `class` erwartet
  — wie es `/api/devices` bereits liefert. Dadurch war `d.class` im UI immer
  `undefined`, der Binär-Zweig griff nie. `/api/constraints` liefert die
  Geräteklasse nun als `class` (einheitlich mit `/api/devices`); Binärgeräte
  zeigen wieder nur „Technische Freigabe" + „Feste Leistung", Regelbare „Min./
  Max. Leistung". Der Lesepfad (EP liest `ems_*`) war nie betroffen.
