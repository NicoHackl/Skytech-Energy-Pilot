# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jeder funktionalen oder
designtechnischen Code-Änderung um eine Patch-Stelle erhöht (Projektregel 2).

## [0.0.23] - 2026-06-26

### Hinzugefügt
- **M3 Durchstich 1 — HEMS-Status-Rückkopplung (Read-Back-Loop):** EP liest den HEMS-Zustand
  zyklisch (`GET /api/status`, neuer Selbst-Drossel-Collector `hems_status_collector.py`,
  Intervall `hems_status_interval_s`, Default 60 s) und leitet daraus eine **beobachtete**
  Plan-Übereinstimmung ab (neues, reines Modul `plan_feedback.py`): je Gerät wird der KI-Vorschlag
  mit dem HEMS-Ist verglichen (`prio_vorschlag` ↔ `priority`, `geschutzte_mindestleistung_w_vorschlag`
  ↔ `schutz_w`, `freigabe_vorschlag` ↔ `eligible` weich) und ein Gesamtstatus gebildet
  (`beobachtet_konform` / `beobachtet_abweichend` / `unbekannt` / `kein_plan`) inkl.
  Gültigkeitsfenster-Prüfung. **Bewusst „beobachtend", nicht „bestätigt"** (D-032/D-033: der User
  verdrahtet die Vorschläge in V1 selbst). Das Feld-Mapping ist **read-only** (nicht der in B4 offene
  Schreibweg) und zentral gehalten für die spätere Ebene 2.
- **EP-Status-Sensoren (`status_publisher.py`):** Spiegelung nach HA als `sensor.ep_plan_status`
  (Gesamtstatus + Abweichungen je Gerät) und `sensor.ep_hems_verbindung` (online/offline, letzter
  Regelzyklus, Pool/Defizit, Modus). Schalter `publish_status` (Default an); fehlertolerant je Entität
  (Iron Rule 8). Audit `status_published`, Verlaufstabelle `hems_feedback` (DB-Migration 5).
- **HEMS-Tab in der UI** (`/api/hems/status`): Verbindung & Regelzyklus, Plan-Rückkopplung
  (Vorschlag vs. Ist je Gerät + Gesamt-Badge), HEMS-Gerätezustände; Button „Jetzt prüfen"
  (`/api/hems/test`, Live-Einzelabruf). Diagnose-Tab um `hems_configured`/`hems_online`/
  `hems_last_fetch_ts`/`hems_last_error` ergänzt.
- **HEMS-Client erweitert:** `HEMSClient.status()` + `controls()` (zusätzlich zu `device_schema()`).

### Hinweise
- HEMS bleibt **unverändert** — EP nutzt nur GET-Endpunkte; bei HEMS-Ausfall läuft EP weiter
  (`online=false`, kein Crash). Echte Plan-Übergabe (Ebene 2 / B4) und Steuermodi (B3) folgen in
  späteren M3-Slices.

## [0.0.22] - 2026-06-26

### Hinzugefügt
- **One Call API 4.0: paginierte Calls je Timeline + Pflicht-Tages-Call-Budget (D-045, beantwortet
  O2):** Je Timeline (15min/1h/1day) lassen sich jetzt **1–5 paginierte Seiten** je Refresh holen
  (`weather.onecall.pages_15min/1h/1day`, Default 1 = erste Seite; jede Seite folgt dem `next`-
  Cursor und ist ein eigener bezahlter Call → mehr Horizont gegen mehr Kosten). **GANZ WICHTIG:**
  ein **harter Tages-Call-Schutz** verhindert das Überschreiten des Kontingents
  (`weather.onecall.daily_call_budget`, Default **1000** = OWM-Freikontingent „One Call by Call").
  Das Budget gilt für **alle** bezahlten One-Call-Anfragen (Timelines **und** Alerts), wird in
  **UTC** gezählt (Reset um Mitternacht, deckt sich mit OWM) und über den persistenten KV-Speicher
  (`config`-Tabelle, `/data`) geführt — so kann auch ein **Neustart-Loop** das Limit nicht umgehen.
  Ist das Budget erschöpft, werden weitere Abrufe **übersprungen** (EP blockiert nie, Iron Rule 8),
  einmalig auditiert (`onecall_budget_exhausted`) und im Wetter-Tab angezeigt. Auch der Button
  „Wetter testen" prüft/bucht gegen dasselbe Budget. Neues Modul `onecall_budget.py`;
  `fetch_timeline` paginiert und liefert die verbrauchten Calls zurück.
- **One Call API 4.0: behördliche Unwetter-Warnungen (D-045, beantwortet O3):** EP ruft die
  Unwetter-Alerts der 4.0-API ab (`weather.onecall.enable_alerts`, **Default an**; eigener Refresh
  `refresh_alerts`, Default 30 min) und zeigt sie im Wetter-Tab (`/api/weather`). Neue Dataclass
  `OneCallAlert`, Client-Methode `fetch_alerts` + `parse_alerts` (tolerant gegenüber fehlenden
  Feldern). **Bewusst V1:** Die Alerts werden **nur mitgeführt/angezeigt** — noch **keine**
  Einspeisung in die Planung; der Zukunftsaspekt (z.B. Batterieladung bei drohendem Gewitter
  priorisieren) baut darauf auf. Schlüssel weiterhin nur als `appid`-Query-Param, nie geloggt
  (Iron Rule 6).

## [0.0.21] - 2026-06-26

### Hinzugefügt
- **OpenWeatherMap One Call API 4.0 als umschaltbare Wetterquelle (D-044, beantwortet W2):**
  Neuer Config-Schalter `weather.source` (`forecast3h` = bestehende 5-Tage/3-Stunden-API,
  **Default** — oder `onecall` = One Call API 4.0). Bei `onecall` werden die Timelines
  **15min**, **1h** und **1day** über getrennte Endpunkte (`/timeline/<res>`) abgerufen, **je
  einzeln aktivierbar** (`weather.onecall.enable_15min/1h/1day`) mit **eigenem Abruf-/Refresh-
  Intervall** (`refresh_15min/1h/1day`, Minuten). Welche Timeline in den KI-Kontext fließt, ist
  konfigurierbar (`weather.onecall.llm_timeline`, Default `1h`; 15min/1h werden auf
  `forecast_horizon_h` gekürzt, 1day vollständig). Es wird je Abruf bewusst **nur die erste
  Seite** geholt (1 bezahlter Call/Timeline/Refresh — Kosten-/Budget-Schutz). Neue Module
  `onecall_client.py` (`OneCallClient`) und `OneCallCollector` (per-Timeline-Drosselung, Fehler
  je Timeline isoliert, Iron Rule 8); neue Dataclasses `OneCallConfig`/`OneCallSlot`/
  `OneCallTimeline`. **Sicherheit:** Schlüssel geht nur als Query-Param `appid`, nie ins Log
  (Iron Rule 6, geteilter `raise_for_owm_status`-Helfer). Die UI (`/api/weather`, „Wetter
  testen") zeigt je aktivierter Timeline eine eigene Tabelle inkl. Stand/Refresh.
  **Hinweis:** One Call API 4.0 erfordert das kostenpflichtige Abo „One Call by Call"; der
  Default-Pfad `forecast3h` bleibt schlüssel-/abofrei.

### Geändert
- **forecast3h-Default-Refresh 30 → 60 min (W3, D-044):** Die 5-Tage/3-Stunden-Prognose ändert
  sich serverseitig nur alle paar Stunden; 60 min sparen Abrufe ohne Informationsverlust.

## [0.0.20] - 2026-06-25

### Hinzugefügt
- **Wetterprognose fließt in die KI-Planung (D-043, beantwortet W1):** Der Planungskontext
  enthält jetzt einen `weather`-Block. Der **Detailgrad ist in der Addon-Config umschaltbar**
  (`weather.llm_detail`): `compact` (Default) liefert je 3-Stunden-Schritt nur Temperatur,
  Bewölkung und Niederschlagswahrscheinlichkeit und kürzt auf den Planungshorizont
  (`forecast_horizon_h`) — Datenminimum (Iron Rule 7); `full` übergibt die komplette
  5-Tage-Prognose mit allen Feldern (mehr Tokens, mehr Kontext). Der Default-Prompt weist die
  KI an, Bewölkung/Regen (PV-Erwartung) und Temperatur (Heizbedarf) einzubeziehen.
- **Editierbarer Planungs-Prompt in der EP-Oberfläche (D-043):** Im Plan-Tab unter
  „Planungs-Prompt bearbeiten" lässt sich die KI-Instruktion direkt bearbeiten, speichern und
  auf den Standard zurücksetzen — **ohne Git-Push/Add-on-Update**. Der Prompt wird in der
  bestehenden `config`-Key/Value-Tabelle persistiert (übersteht Neustart **und** Add-on-Update,
  keine Migration). Neue Endpunkte `GET/POST /api/prompt`, neues Modul `settings.py`
  (generischer KV-Speicher). **Sicherheit:** Der Datenblock (`Daten:`) wird immer automatisch
  angehängt, das JSON-Antwort-Schema bleibt code-kontrolliert und der Validator erzwingt die
  harten Grenzen unabhängig vom Prompt (Iron Rules 5/6). Prompt-Änderungen werden auditiert
  (nur Länge, kein Volltext).

## [0.0.19] - 2026-06-25

### Geändert
- **OpenWeatherMap-Fehler zeigen jetzt den Originalgrund:** Bei HTTP 401/404/429 (und anderen
  4xx/5xx) reicht der Client die OWM-Meldung aus dem Antwort-Body durch (z.B. „Invalid API key.
  Please see …faq#error401"). Vorher wurde nur eine feste Meldung angezeigt, die den echten
  Grund verbarg. Der API-Schlüssel ist **nie** Teil des OWM-Fehler-Bodys, bleibt also unsichtbar
  (Iron Rule 6). Die 401-Meldung benennt zusätzlich explizit „… oder noch nicht aktiviert", da neue
  OWM-Schlüssel bis zu ~2 h Aktivierungszeit brauchen.

### Hinzugefügt
- **Diagnose-Button „Wetter testen" + Endpunkt `GET /api/weather/test`:** Führt einen
  Live-Einzelabruf durch (umgeht den `refresh_min`-Guard) und zeigt bei Erfolg Ort/Anzahl
  Zeitschritte, bei Fehler den OWM-Originalgrund **plus die maskierte Anfrage-URL**
  (`appid=***`) — so ist sofort prüfbar, dass der Aufruf korrekt aufgebaut ist und woran ein
  401 liegt. Neue Client-Methode `masked_request_url`, Collector-Methode `test_fetch`.

### Hinweis
- Der Wetter-Aufruf war bereits **korrekt** aufgebaut (entspricht exakt der OWM-Doku:
  `…/data/2.5/forecast?lat=…&lon=…&appid=…&units=metric&lang=de`). Ein HTTP **401** ist ein
  OWM-seitiges Schlüsselthema (meist: Key noch nicht aktiviert), **kein** Free-Plan-/Limit-Problem
  (das wäre HTTP 429; die 5-Tage/3-Stunden-Prognose ist im Free-Tier ohne Zahlungsmethode enthalten).

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
