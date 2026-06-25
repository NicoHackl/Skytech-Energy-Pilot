# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jeder funktionalen oder
designtechnischen Code-Änderung um eine Patch-Stelle erhöht (Projektregel 2).

## [0.0.18] - 2026-06-25

### Behoben
- **Start-Crash bei aktiver Wetterprognose:** Die HA-Zone wurde mit einer Liste statt
  des erwarteten `entity_id → source`-Mappings an `EntityAllowlist.register_all` übergeben
  (`AttributeError: 'list' object has no attribute 'items'`), wodurch das Add-on beim Start
  abbrach, sobald ein OpenWeatherMap-Schlüssel gesetzt war. Die Zone wird jetzt korrekt als
  `{zone_entity: "weather"}` registriert (neue Allowlist-Quelle `SOURCE_WEATHER`).

## [0.0.17] - 2026-06-25

### Hinzugefügt
- **Wettervorhersage über OpenWeatherMap (direkt im EP):** EP ruft die
  „5 day / 3 hour forecast"-API von OpenWeatherMap jetzt **direkt** ab (eigene externe
  Quelle, nicht über HA-Sensoren wie die PV-Prognose). Längen-/Breitengrad kommen aus
  einer **HA-Zone** (`zone.*`, Attribute `latitude`/`longitude`), der API-Schlüssel und
  alle Parameter werden in der Addon-Config gepflegt. Neue Module `weather.py`
  (Config-Parsing + normalisierte Dataclasses), `weather_client.py` (aiohttp-Client,
  Muster wie `gemini_provider.py`; `appid` als Query-Param, **nie geloggt**, Iron Rule 6)
  und `weather_collector.py` (löst die Zone in Koordinaten auf, drosselt OWM-Aufrufe
  selbst auf `refresh_min`). Die Zone wird als Lese-Entität in die Soft-Allowlist
  aufgenommen (D-038).
- **Neue Addon-Option-Gruppe `weather`** (`api_key`, `zone_entity` [Default `zone.home`],
  `units` [Default `metric`], `lang` [Default `de`], `refresh_min` [Default 30]). Ohne
  `api_key` bleibt der Wetterabruf inaktiv – EP blockiert nie (Iron Rule 8).
- **Endpunkt `GET /api/weather`** (read-only Momentaufnahme) und ein **Wetter-Block im
  Prognose-Tab** der UI (Temperatur, Bewölkung, Niederschlagswahrscheinlichkeit, Wind,
  Zustand je 3-Stunden-Schritt). Diagnose um `weather_enabled`/`weather_last_fetch_ts`/
  `weather_last_error` ergänzt.
- **Scope V1 (bewusst):** Die Wetterdaten werden **aktuell nur EP-intern** genutzt
  (UI/API). Sie werden **noch nicht** als HA-Sensoren bereitgestellt und **nicht** über
  die interne API an das HEMS übergeben. Ob/wie sie in den KI-Planungskontext einfließen,
  ist offen → [claude-fragen/claude-fragen-v8.md](claude-fragen/claude-fragen-v8.md).

## [0.0.16] - 2026-06-19

### Hinzugefügt
- **Vorschlagssensoren — KI-Vorschläge nach Home Assistant schreiben (Abschluss M2):**
  EP veröffentlicht die validierten Vorschlagswerte eines Plans jetzt als
  `sensor.ep_<gerät>_<feld>_vorschlag`-Entitäten in HA (V1-Schreibweg aus
  [variablen-zugriff.md](user-beispiele/variablen-zugriff.md)). Damit ist die M2-DoD
  „sichtbar in UI/**Sensoren**/Logs" vollständig erfüllt. Es sind **reine Anzeige-/
  Vorschlagssensoren** — sie steuern nichts und werden (noch) **nicht** an HEMS übergeben
  (das ist M3); der User verdrahtet sie testweise selbst in HA-Automationen. Geschrieben
  werden ausschließlich die je Gerät vertraglich erlaubten Felder (D-030/D-034/D-037/D-035).
  Booleans als `on`/`off`, Leistung/Temperatur mit `unit_of_measurement`. Neues Modul
  `suggestion_publisher.py` (reine Entity-Erzeugung + fehlertolerantes Schreiben, Iron Rule 8);
  HA-Schreibzugriff `HAClient.set_state` (POST `/api/states`, **ohne** Allowlist-Guard, da
  diese die Lese-Domäne ist, D-038). Jeder Schreibvorgang wird als `suggestions_published`
  auditiert.
- **Auslöser (Auto + manuell):** Nach jedem **gültigen** Plan schreibt EP automatisch
  (abgelehnte Pläne nie). Zusätzlich ein Button **„Erneut nach HA schreiben"** im Plan-Tab
  und der Endpunkt `POST /api/plan/publish`, der den zuletzt gültigen Plan erneut
  veröffentlicht. Die `POST /api/plan/run`-Antwort enthält jetzt das Schreibergebnis
  (`published`); der Plan-Tab zeigt die geschriebenen Entitäten.
- **Neue Addon-Option `publish_suggestions`** (Default `true`): auf `false` bleibt EP im
  reinen Beobachten-Modus (Plan in UI/DB, **kein** HA-Schreiben).

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
