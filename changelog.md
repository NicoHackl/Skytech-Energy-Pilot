# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jeder funktionalen oder
designtechnischen Code-Änderung um eine Patch-Stelle erhöht (Projektregel 2).

## [Unreleased]

### Hinzugefügt
- **Multi-Provider: Claude und OpenAI zusätzlich zu Gemini (D-056).** Der KI-Anbieter ist
  jetzt zwischen **Google Gemini**, **Anthropic Claude** und **OpenAI (GPT)** umschaltbar.
  In der Addon-Config wählt ein Radio/Dropdown (`provider`) den aktiven Anbieter; jeder
  Anbieter hat ein eigenes aufklappbares Untermenü `providers.<name>` mit Schlüssel, Modell,
  Zeitlimit und Ratenbegrenzung. Alle drei sind schlanke aiohttp-REST-Clients (kein SDK) über
  die gemeinsame `AIProvider`-Abstraktion; `schema_convert.py` übersetzt das
  Antwort-Schema für Claude (`output_config.format`) und OpenAI (`response_format`, Strict).
  Default-Modelle: Gemini `gemini-2.5-flash`, Claude `claude-sonnet-5`, OpenAI `gpt-5`.
  **Config-Migration:** Die früheren flachen Top-Level-Keys (`model`/`api_key`/
  `ai_request_timeout_s`/`ai_rate_limit_per_min`) sind entfernt. Bestehende Gemini-
  Installationen laufen dank Legacy-Fallback zunächst weiter; den Schlüssel nach dem Update
  bitte ins Gemini-Untermenü eintragen. `ai_temperature`/`ai_seed` bleiben geteilt (Claude
  ignoriert Sampling-Parameter).

### Geändert
- **"Klassifizierung erzeugen"-Button im Plan-Tab (D-055 Folge-Anpassung).** Neuer Button
  löst den Klassifizierungs-Aufruf isoliert aus (`POST /api/classification/run`,
  `Planner.run_classification()`), unabhängig vom eigentlichen Plan-Lauf – zum gezielten
  Testen von Zieldefinitionen/Klassifizierungs-Prompt. Zeigt analog zu "Plan erzeugen" die
  gesendeten Daten und das Ergebnis (Gewichtung je Ziel + Begründung).
- **User-definierte Ziele statt statischer Zielgewichte (D-055).** Die feste Addon-Config
  `objective_weights` (8 Ziele, Gewicht 0–100 %) ist entfernt. Im Tab "Grenzen und Ziele"
  definiert der User jetzt eigene Ziele (Name, Beschreibung, zugeordnete Geräte) OHNE
  Gewicht (`GET/POST/DELETE /api/ziele`, DB-Tabelle `ziele`). Ein vorgelagerter
  Klassifizierungs-LLM-Aufruf bekommt dieselbe Datenbasis wie der Plan-Aufruf plus die
  Zieldefinitionen und leitet daraus je Planungslauf die Gewichtung ab (eigener
  editierbarer Klassifizierungs-Prompt im Plan-Tab, `GET/POST /api/classification-prompt`).
  Scheitert die Klassifizierung oder der Plan-Aufruf, gilt der gesamte Lauf als
  gescheitert. Migration ohne Seed-Daten – bestehende Installationen starten mit einer
  leeren Ziele-Liste.
- **Harte Freigabe-Sperre entfernt (D-054).** `technische_freigabe=false` beschreibt nur
  den AKTUELLEN Ist-Zustand eines Geräts, kein Verbot für den gesamten Gültigkeitszeitraum
  des Plans (24–48 h). EP darf `freigabe_vorschlag=true` jetzt auch dann vorschlagen, wenn
  das Gerät aktuell technisch gesperrt ist. Entfernt: harter Reject in Validator-Stufe 2
  (`_check_device`) sowie der Sofort-Override in der Freigabe-Hysterese (`smooth_plan()`).
  Weiterhin: dient als sicherer Fallback-Startwert, wenn die KI `freigabe_vorschlag` auslässt.
- **Branch-Strategie: `claude/main` → `claude/stage` + 3 Release-Channels (D-053).**
  Arbeits-Branch umbenannt. Neu: `stage/dev`/`stage/beta`/`stage/stable`, je eigenes
  `config.yaml` (Slug-/Namens-Suffix), damit HA sie per Branch-URL als 3 separate
  Addon-Channels (Dev/Beta/Stable) anzeigt. Promotion zwischen den Branches nur
  manuell auf Zuruf, kein Automatismus. CI (`ci.yaml`) läuft ab sofort auf allen
  4 Branches statt nur auf `claude/main`.

## [0.0.51] - 2026-07-11

### Hinzugefügt
- **Stabilitäts-Kern aus `plan/longterm_plan_claude.md` (A2/A3/A4/B2).** Deterministische
  Ruhe über Läufe („Determinismus rahmt, KI füllt"):
  - **A2 – Anti-Flatter (Validator Stufe 5).** Neue reine `smooth_plan()` in `validator.py`:
    Delta-Limit der geschützten Mindestleistung je Lauf (±20 %, Batterie ±10 %, D-021),
    Freigabe-Hysterese (Wechsel erst nach N=2 konsistenten Läufen), Mindesthaltezeit
    (Default 15 min). **Sicherheit vor Stabilität:** eine technisch gesperrte Last wird nie
    auf „frei" gehalten. Der Planner lädt/speichert den Pro-Gerät-Zustand (neue Tabelle
    `device_plan_state`, Migration 9), glättet nur gültige Pläne und hängt die Glättungs-
    Notizen an das Klemm-Log.
  - **A3 – Eingangs-Quantisierung.** An die KI gegebene Werte werden gerundet (Leistung 50 W,
    SOC 1 %, Ampere 0,1 A, PV-Prognose 0,1 kWh; Zeitstempel auf die Minute). So verändert
    kleines Sensor-Rauschen den Prompt nicht mehr → gleicher Input → gleiche Antwort
    (nutzt `ai_temperature=0`/`ai_seed=42` endlich aus).
  - **A4 – Confidence-Gate (Validator Stufe 6).** `min_confidence_percent` (Default 70 %)
    wird endlich gelesen: unsichere Pläne werden abgelehnt und **nicht** nach HA geschrieben;
    der zuletzt gültige Sensorwert bleibt stehen.
  - **B2 – Trend-Features.** Je Messgröße ein `trend` (steigend/fallend/stabil) aus kurz-
    gegen langfristiges Mittel — die KI plant aus dem Verlauf statt aus einem Momentwert.
  - **C1 – Tests.** Neue `test_stability.py` plus Confidence-/Quantisierungs-/Trend- und
    Doppellauf-Hysterese-Tests (420 Tests grün).
  - Neue Addon-Config-Keys: `delta_limit_power_percent`, `delta_limit_battery_percent`,
    `freigabe_hysteresis_runs`, `min_hold_minutes`, `snap_power_w`, `snap_soc_percent`,
    `snap_amp_a`, `snap_forecast_kwh` (Leitprinzip „alles konfigurierbar").
- Bewusst zurückgestellt (Begründung in `plan/longterm_plan_claude.md`): A5 (Freshness,
  braucht Collector-Zeitstempel), A6 (Basisplan), B1 (Feedback-Rückführung), B3 (Urgency-
  Formel), B4 (Reason-Codes), B5 (Bilanz), C2/C3 (Shadow/KPI/Kritiker).

## [0.0.50] - 2026-07-11

### Hinzugefügt
- **A1 – Vorplan als Anker in die Planung (Stabilität über Aufrufe).** `Planner.run()`
  lädt vor dem KI-Aufruf den zuletzt gespeicherten Plan (`latest_plan()`) und reicht ihn
  verdichtet als `previous_plan` in den KI-Kontext (`plan_context.build_context()` neuer
  Parameter `previous_plan`). Übergeben werden nur Gerät-Vorschlagswerte (Name + gesetzte
  `*_vorschlag`-Felder) plus die frühere Konfidenz — kein Reasoning/Warnings/Zeitstempel
  (Datenminimum, Iron Rule 7). Der Default-Planungs-Prompt weist die KI an, ohne
  materiellen Grund nah am Vorplan zu bleiben und Prio/Freigabe nicht wegen kleiner
  Schwankungen zu ändern. Erster Lauf (kein Vorplan) hängt keinen Anker an. Grundlage für
  die spätere Anti-Flatter-Glättung (A2). Siehe `plan/longterm_plan_claude.md` Abschn. 3.

## [0.0.49] - 2026-07-10

### Geändert
- **Alte Doku ersetzt durch neuen Ordner `doc/`.** `info.md`, `plan/*.md`,
  `user-regeln.md` und `user-fragen.md` wurden vom User gelöscht (Commit `ad48b23`).
  Neu geschrieben, diesmal am **tatsächlichen Code** verifiziert statt an der
  ursprünglichen Planung: `doc/architecture.md`, `entity-naming.md`, `control-modes.md`,
  `devices.md`, `planning-engine.md`, `validation-safety.md`, `configuration.md`,
  `api-reference.md`, `data-model.md`, `known-gaps-and-pitfalls.md`, `decisions-log.md`
  (verdichtetes D-001…D-052), `roadmap.md`, `contributing.md`. `known-gaps-and-pitfalls.md`
  hält u. a. fest, dass es **keinen automatischen Planungs-Scheduler** gibt und die
  Validator-Stufen 4–6 (Frische/Delta-Limit/Mindestkonfidenz) fehlen — bislang nirgends
  schriftlich festgehalten. `CLAUDE.md` verweist jetzt auf `doc/` statt auf die
  gelöschten Dateien.
- **Tote Doku-Verweise im Code bereinigt.** Kommentare/Docstrings, die auf
  `info.md §…`, `plan/*.md` oder `user-regeln.md §…` verwiesen, zeigen jetzt auf die
  passende `doc/*.md`-Datei (`roles.py`, `ai_provider.py`, `config.py`, `database.py`,
  `constraints.py`, `objectives.py`, `allowlist.py`, `gemini_provider.py`,
  `logging_setup.py`). Der `hems_client.py`-Docstring behauptete zusätzlich fälschlich
  einen Addon-Config-Fallback bei der Geräte-Discovery, den es seit D-046 nicht mehr
  gibt — korrigiert.
- **Grenzen-&-Ziele-Tab:** Der Hinweistext zu den Zielgewichten verwies auf das
  gelöschte `info.md §7` — jetzt ohne toten Verweis.

## [0.0.48] - 2026-07-09

### Geändert
- **One Call 4.0: freie Kombination der Vorhersagemodelle statt Einzel-Auswahl für die KI.** Die
  drei Modelle **15min / 1h / 1day** sind in der Addon-Config je per **Schalter** (`enable_*`)
  aktivierbar; **jedes aktive Modell wird abgerufen UND fließt gemeinsam in den KI-Kontext**. Man
  muss sich also **nicht mehr für ein einzelnes Vorhersagemodell entscheiden** — jede gewünschte
  Kombination ist möglich.
  - Das bisherige Einzel-Select **`weather.onecall.llm_timeline` ist entfallen** (aus Optionen +
    Schema entfernt; ein evtl. noch gespeicherter Wert wird ignoriert).
  - Der KI-Kontext hat jetzt `weather.models` mit einem Eintrag je aktivem Modell: intraday
    (15min/1h) für **heute** ab jetzt (frühestens 6 Uhr) bis 21 Uhr Ortszeit, das Tagesmodell
    (1day) für die **nächsten 5 Tage ab morgen**. Jeder Eintrag nennt Auflösung + `zeitraum`.
  - Wetter-Tab: die Zeile zeigt statt „KI-Timeline: 1h" jetzt „KI nutzt: <aktive Modelle>"
    (`snapshot.ai_models`).

## [0.0.47] - 2026-07-09

### Geändert
- **Wetter an die KI (One Call): stündliche Reihe auf den heutigen Tag begrenzt + Tagesausblick
  der nächsten 5 Tage ergänzt (`upcoming_changes.md`).** Bislang floss **eine** One-Call-Timeline
  ungefenstert (auf den Planungshorizont gekürzt) in den Planungskontext. Jetzt bekommt die KI bei
  `weather.source: onecall` **zweierlei**:
  - **`hourly`** – die stündliche Reihe **nur für heute**, vom aktuellen Zeitpunkt (frühestens ab
    **6 Uhr**) bis **21 Uhr Ortszeit**. Beispiele: um 11:30 → 12:00–21:00; vor 6 Uhr → ab 6:00;
    nach 21 Uhr bleibt die Stundenreihe **leer**. Die Ortszeit kommt aus dem OWM-`timezone_offset`
    der Wetter-Zone.
  - **`daily`** – ein **Tagesausblick der nächsten 5 Tage ab morgen** (Temperatur inkl. Tages-Min/
    Max, Bewölkung, Regenwahrscheinlichkeit); der heutige Tag steckt bereits in der Stundenreihe.
  - `weather.onecall.llm_timeline` wählt nun die **Auflösung der Stundenreihe** (`15min`/`1h`); die
    Tagesreihe kommt fest aus der `1day`-Timeline. Der `OneCallCollector`-Snapshot trägt je Timeline
    zusätzlich den `timezone_offset_s` (fürs Ortszeit-Fenster). UI-Anzeige und HEMS-Weg unverändert.

## [0.0.46] - 2026-07-08

### Behoben
- **HEMS-Tab: „Geschützte Mindestleistung" zeigte gar keinen HEMS-Ist-Wert mehr.** Nach 0.0.45
  liest EP den rohen Sockel `geschuetzte_mindestleistung_w`/`_a` aus dem HEMS-Status – ältere
  HEMS-Stände liefern dieses Feld aber noch nicht, wodurch die Spalte leer blieb (Status
  „unbekannt"). EP trägt den Wert jetzt **hilfsweise** direkt aus dem HA-Helfer
  `input_number.ems_<gerät>_geschutzte_mindestleistung_<w|a>` nach, wenn das HEMS ihn nicht
  liefert. Sobald ein HEMS mit dem Feld läuft, hat dessen Wert Vorrang (kanonisch, wird nie
  überschrieben). Damit funktioniert die Anzeige unabhängig von der HEMS-Version.
- **HEMS-Tab: „Aktualisieren" holte die HEMS-Ist-Werte nicht neu ab.** Der Button spiegelte nur
  den gedrosselten Zwischenstand des Collectors (Abruf alle `interval_s`). Er erzwingt jetzt über
  `GET /api/hems/status?refresh=1` einen **Live-Abruf** des HEMS (`collect_once(force=True)`, umgeht
  die Drosselung); der reguläre Auto-Poll (alle 10 s) bleibt unverändert leichtgewichtig.

## [0.0.45] - 2026-07-08

### Behoben
- **Plan-Rückkopplung (HEMS-Tab): „Geschützte Mindestleistung" zeigte den effektiven Schutz statt
  des Rohwerts.** Die Spalte HEMS-Ist verglich den EP-Vorschlag gegen `schutz_w`/`schutz_a` des
  HEMS-Status – das ist aber der **effektive** Schutz (`geschützte Mindestleistung + reserve_w +
  global_puffer_w`, geklemmt), nicht der rohe Sockel. Folge: bei einem Helferwert von z.B. 600 W
  erschien 900 W, und der Vergleich meldete fälschlich „abweichend". EP vergleicht/zeigt jetzt den
  rohen HEMS-Wert `geschuetzte_mindestleistung_w`/`_a` (setzt den entsprechenden HEMS-Zusatz im
  Status voraus). Fehlt das Feld (älterer HEMS-Stand), bleibt der Status sicher „unbekannt" statt
  auf den falschen `schutz_w` zurückzufallen. Betrifft Watt **und** Ampere (Wallbox).

## [0.0.44] - 2026-07-05

### Geändert
- **Logging: Original-Fehlermeldungen der Backends werden jetzt mitgeloggt.** Bislang gingen bei
  HTTP-Fehlern (4XX/5XX) von Home Assistant und dem HEMS die eigentlichen Servergründe verloren,
  weil `resp.raise_for_status()` nur „HTTP 400" o.ä. meldete und den Antwort-Body verwarf. Jetzt
  wird der Body ausgelesen und der echte Grund (`{"message": …}` bzw. `{"error": {"message": …}}`)
  in die Fehlermeldung gehoben – z.B. `Home Assistant: HTTP 404 Not Found (/api/states/…) – Entity
  not found.` statt eines nichtssagenden „HTTP 404".
  - **Neu:** gemeinsamer Helfer `http_errors.raise_for_status`/`read_error_body` + Ausnahme
    `HTTPStatusError` (trägt Status, Reason, Servermeldung und Endpunkt-**Pfad** als strukturierte
    Felder). Genutzt von HA-Client, HEMS-Client und (Body-Leser) OWM-/Gemini-Client.
  - **Gemini:** 429- und 4XX/5XX-Fehler nehmen jetzt ebenfalls den Original-Grund aus dem Body
    mit (vorher nur roher Textausschnitt bzw. beim Rate-Limit gar keine Server-Info).
  - **Iron Rule 6 gewahrt:** es wird nur der Pfad ohne Query mitgeführt – kein als Query-Parameter
    übergebener Schlüssel (z.B. OWM `appid`) kann in ein Log geraten.
  - **Unerwartete Ausnahmen** im Sammellauf werden mit **Traceback** (`exc_info`) und dem Namen der
    fehlgeschlagenen Komponente geloggt → maschinenlesbar im JSONL-Export (KI-Fehleranalyse,
    user-regeln §02). `log()` akzeptiert dafür nun `exc_info`.

## [0.0.43] - 2026-07-05

### Behoben
- **One-Call-4.0-Unwetterwarnungen: falscher Endpunkt behoben (Wetter-Test-Fehler
  „OpenWeatherMap: Koordinaten nicht gefunden (HTTP 404): Internal error").** Die Alerts wurden
  über einen nicht existierenden Koordinaten-Endpunkt `…/onecall/alert?lat=&lon=` abgerufen → OWM
  antwortet mit HTTP 404. In der One Call API 4.0 gibt es **keinen** Koordinaten-Alert-Endpunkt:
  die aktiven Warnungen stehen als **Alert-IDs** in den Timeline-Antworten (`data[].alerts`) und
  werden je ID über den **Detail-Endpunkt** `…/onecall/alert/{id}` (nur `appid`/`lang`) aufgelöst.
  - `parse_timeline` sammelt jetzt die Alert-IDs je Timeline (`OneCallTimeline.alert_ids`,
    dedupliziert über alle Seiten).
  - Neuer Client-Aufruf `fetch_alert(alert_id)` + `parse_alert` (einzelnes Objekt statt Liste);
    `masked_alert_url` zeigt das ID-Muster ohne Koordinaten.
  - Der `OneCallCollector` löst die aus den Timelines bekannten IDs auf (je ID ein bezahlter
    Detail-Call gegen dasselbe Tagesbudget). **Ohne aktive Warnung** fällt kein Call an
    (`Alerts ✅ 0`); ohne aktive Timeline ein klarer Hinweis statt eines HTTP-Fehlers.

## [0.0.42] - 2026-07-05

### Geändert
- **Addon-Konfiguration vollständig deutsch beschriftet (HA-Formular).** Die
  `translations/de.yaml` (und `en.yaml`) waren unvollständig und veraltet, wodurch viele
  Felder im HA-Konfigurationsformular mit ihrem rohen technischen Schlüssel angezeigt wurden.
  Jetzt hat **jede** Option einen lesbaren Anzeigenamen + Beschreibung:
  - **Neu übersetzt (fehlten):** `api_key`, `ai_request_timeout_s`, `ai_rate_limit_per_min`,
    `hems_base_url`, `hems_status_interval_s`, `publish_status`, `pv_forecast_unit`.
  - **Verschachtelte Gruppen/Listen über `fields:`-Blöcke beschriftet** (HA-Mechanismus):
    `sensoren` (entity_*), `objective_weights` (Zielgewichte), `weather` inkl. `weather.onecall`,
    und die Listeneinträge von `pv_forecast`. So bekommt auch jedes Unterfeld einen deutschen
    Namen statt des technischen Schlüssels.
  - **Veraltete Einträge entfernt:** `fallback_*` (Feature in 0.0.40 entfernt) und
    `entity_water_temperature` (Warmwassertemperatur ist gerätespezifisch, Geräte-Tab). Die
    `entity_*`-Namen lagen zudem fälschlich top-level und greifen erst korrekt unter
    `sensoren.fields`.
  Der technische Schlüssel in `config.yaml`/`schema` bleibt unverändert – nur die Anzeige.

## [0.0.41] - 2026-07-05

### Geändert
- **Durchgängig lesbare deutsche Anzeigetexte (UI-Audit).** Verbliebene technische/englische
  Bezeichner in der Ingress-Oberfläche durch schön lesbare deutsche Namen ersetzt:
  - HEMS-Tab: Spaltenkopf `Eligible` → `Freigegeben`; Spalte „Typ" zeigt statt der rohen
    HEMS-Werte `binary`/`controllable` jetzt `binär`/`regelbar`.
  - Plan-Tab: Geräte-Überschrift zeigt den technischen Gerätenamen (z. B. `heizstab`) jetzt
    als lesbare Überschrift (`Heizstab`) statt in snake_case.
  - Status-Tab: Karte „Systemstatus" beschriftet die Roh-Schlüssel jetzt deutsch
    (`provider` → „KI-Anbieter", `model` → „Modell", `ha_configured` → „HA verbunden" …) und
    zeigt Bool-Werte als Ja/Nein statt `true`/`false`; Diagnose-Zeilen ebenso (Ja/Nein).
  - Spalten „Quelle" (Daten/Geräte/Prognose/Allowlist): technische Herkunftstoken lesbar
    übersetzt (`live` → „Live", `none` → „keine", `weather` → „Wetter", `measurement`
    → „Messwert", `device` → „Gerät", `forecast` → „Prognose"). CSS-Klassen unverändert.
  - HEMS-Tab: „Globaler Modus" zeigt den Regelmodus-Wert lesbar (`nur_heizen` → „Nur Heizen"
    usw.) statt in snake_case.
- **HA-Helfer-Vorlage `input_select_ep.yaml`:** Auswahloptionen von technischem snake_case auf
  lesbares Deutsch umgestellt (`eigenverbrauch_maximieren` → `Eigenverbrauch maximieren`,
  `manuell` → `Manuell` usw.). Bei `input_select` ist der Options-Text zugleich der gespeicherte
  Wert; die Optionen werden derzeit von keinem Code gelesen, daher rein anzeigeseitig.

## [0.0.40] - 2026-07-05

### Entfernt
- **Sensor-Fallback-Werte komplett entfernt.** In der Addon-Konfiguration (Gruppe „Sensoren")
  hatte jeder Sensor ein Feld `fallback_<rolle>`; fachlich sinnlos (ein statischer Ersatzwert
  für eine Live-Messgröße). Felder aus `options`/`schema` in `config.yaml` entfernt, die
  Fallback-Logik aus `entity_map.py` (Feld `EntityMapping.fallback_value`, DB-Spalte wird nicht
  mehr gelesen/geschrieben), `collector.py` (Quelle `fallback` entfällt → nur noch `live`/`none`)
  und der Anzeige-Spalte im Einstellungen-Tab (`app.js`, `web/server.py`) gezogen.
- **Systemweite Warmwassertemperatur entfernt.** `entity_water_temperature`/`fallback_water_temperature`
  gehörten nicht in die systemweite Sensor-Zuordnung, da die Warmwassertemperatur **gerätespezifisch**
  ist. Rolle `water_temperature` aus `roles.py` und die Felder aus `config.yaml` entfernt; die
  Konfiguration erfolgt künftig pro Gerät im Geräte-Tab (vgl. Zusatz-Entität „Max. Wassertemperatur", D-047).

## [0.0.39] - 2026-07-04

### Geändert
- **Frontend-Architektur auf Preact + htm umgestellt (kein Build-Schritt).** Die Ingress-SPA wird
  nicht mehr per Hand über `innerHTML`-Strings aufgebaut, sondern als Preact-Komponenten
  (htm-Templates; Preact/htm vendored unter `web/static/vendor/`, keine externe CDN, kein Node-Build).
  Löst die frühere Vanilla-JS-SPA ab (D-010: „später optional Framework, sobald die UI ausgebaut ist").
  Reaktiver Komponenten-Zustand ersetzt die manuellen DOM-Hacks (Fokus-Erhalt beim Tippen,
  Dropdown-Auswahl, Auto-Refresh nur des aktiven Tabs).
  - **Verhalten/Endpunkte unverändert:** identische API-Pfade, Payloads, Tabs und Funktionen; das
    HA-Design (Klassennamen/CSS) und die responsive Darstellung (0.0.38) bleiben erhalten.
  - Neue aiohttp-`/static`-Route liefert die vendored Assets + `app.js` aus (Ingress-relativer Pfad
    `static/…`, wie im HEMS-Addon).
  - Verifiziert: `ruff`, 37 Web-Tests (inkl. neuem Static-Route-Test) sowie ein Headless-Render
    (jsdom) aller neun Tabs mit leeren **und** realistischen Daten – ohne Render-Fehler.

## [0.0.38] - 2026-07-04

### Hinzugefügt
- **Responsive Darstellung (Handy/Tablet).** Die Ingress-Oberfläche passt sich an kleine
  Bildschirme an – **kein horizontales Scrollen mehr, nur vertikal**: breite Tabellen werden
  am Handy (≤480 px) zu gestapelten Karten mit Spaltenbeschriftung, die Tab-Leiste bricht um
  statt seitlich zu scrollen, das Zusatz-Entitäten-Formular wird einspaltig, lange Code-/JSON-
  Blöcke brechen um. Tablet-Breakpoint (≤900 px) mit reduzierten Abständen; größere Touch-Ziele
  auf Finger-Geräten.
  - **Rein visuell/additiv:** Tabellenzellen erhalten ihre Spaltenüberschrift per
    MutationObserver als `data-label` (fürs Karten-Layout). Alle Tabs, API-Aufrufe, IDs und
    Event-Handler bleiben unverändert.

## [0.0.37] - 2026-07-04

### Geändert
- **Weboberfläche im Home-Assistant-Design neu gestaltet.** Layout, Farben und Aufbau der
  Ingress-Oberfläche sind jetzt stark an das HA-Standardtheme (Material Design) angelehnt:
  blaue App-Bar (Primärfarbe `#03a9f4`) mit View-Tabs und Unterstrich-Indikator, abgerundete
  `ha-card`-Karten (12 px, weiche Schatten), HA-typische Datentabellen, `mwc-button`-Anmutung
  für Schaltflächen, HA-Textfelder für Eingaben sowie helles **und** dunkles Theme über
  `prefers-color-scheme`. Der bisherige minimalistische Systemschrift-Look wurde ersetzt.
  - **Rein visuell – keine funktionale Änderung:** sämtliche Tabs (Status, Daten, Geräte,
    Prognose, Grenzen & Ziele, Plan, HEMS, Einstellungen, Logs), alle API-Aufrufe, IDs,
    Event-Handler und das gesamte Frontend-`<script>` bleiben unverändert. Betrifft nur den
    `<style>`-Block und die statische Markup-Struktur in `web/templates/index.html` (Kopfleiste,
    Tab-Navigation, Karten-Wrapper); die per JavaScript erzeugten Inhalte werden über die
    bestehenden Klassennamen HA-konform gestylt.

## [0.0.36] - 2026-07-03

### Hinzugefügt
- **„In Original schreiben" für Zusatz-Entitäten (D-052).** Zusätzlich zur Checkbox „KI liefert
  Vorschlagswert" gibt es je Zusatz-Entität nun eine zweite Checkbox „In Original schreiben"
  (nur wählbar, wenn der KI-Vorschlag aktiv ist). Ist sie gesetzt, schreibt EP den Vorschlag
  **zusätzlich** zum bestehenden `sensor.ep_<obj>_vorschlag` per HA-Service direkt in die
  Original-Entität zurück (`input_number.set_value`, `input_select.select_option`,
  `input_datetime.set_datetime`, `input_text.set_value`, `input_boolean.turn_on`/`turn_off` –
  je nach Typ). Gilt **nur** für echte, schreibbare Helfer (`input_number`/`number`,
  `input_boolean`, `input_datetime`, `input_text`/`text`, `input_select`/`select`); bei
  `sensor.*`-Quellen (immer read-only) entsteht unverändert nur der `_vorschlag`-Sensor, die
  Checkbox bleibt dort wirkungslos.
  - Betrifft `devices.py` (`DeviceExtra.write_original`, `is_writable_helper`,
    `should_write_original`), `database.py` (Migration 8, Spalte `write_original`),
    `device_extras.py` (Persistenz), `ha_client.py` (neu: `call_service`),
    `suggestion_publisher.py` (`build_original_writes`, `OriginalWrite`, Schreibweg in
    `publish_suggestions`), `server.py` (`device_extra_post`-Validierung + `_extras_payload`),
    `index.html` (Checkbox, an KI-Vorschlag gekoppelt, Anzeige des effektiven Zustands).

## [0.0.35] - 2026-07-03

### Geändert
- **Geräte-Tab übersichtlicher: nur noch EIN Gerät auf einmal (Dropdown-Auswahl).** Statt alle
  Geräte gestapelt anzuzeigen, wählt der User oben ein Gerät aus einem Dropdown; darunter
  erscheinen genau dessen `ems_*`-Werte, Zusatz-Entitäten und (neu) die KI-Beschreibung. Die
  Auswahl bleibt über die 10-Sekunden-Auto-Aktualisierung erhalten. Reine Frontend-Änderung
  (`index.html`); der `/api/devices`-Vertrag ist unverändert (nur um `ai_prompt` je Gerät ergänzt).

### Hinzugefügt
- **Custom-Prompt je Gerät für die KI (D-051).** Im Geräte-Tab kann pro Gerät ein Freitext
  hinterlegt werden, der der KI die **Funktion/Besonderheiten** des Geräts erklärt (z. B.
  „versorgt die Fußbodenheizung, träge, darf bevorzugt mittags laufen“). Der Text ist rein
  **advisorisch**: er geht als Kontext-Feld `funktion` je Gerät in den Planungs-Prompt ein
  (nur bei gesetztem Text, Datenminimum Iron Rule 7) und wird **nie** ans HEMS übergeben. Leerer
  Text löscht die Beschreibung. Persistent über Neustart/Update (neue Tabelle `device_prompts`,
  Migration 7). Änderungen wirken sofort beim nächsten Plan (kein HEMS-Reload).
  - Betrifft `database.py` (Migration 7), neues Modul `device_prompts.py`, `devices.py`
    (`Device.ai_prompt`), `device_extras.py` (`apply_extras` mergt Prompts), `constraints.py`
    (`DeviceConstraint.ai_prompt`), `plan_context.py` (Kontext-Feld `funktion` + Prompt-Regel),
    `device_collector.py` (Snapshot-Feld `ai_prompt`), `server.py` (neuer Endpoint
    `POST /api/devices/prompt`), `index.html`.

## [0.0.34] - 2026-07-03

### Behoben
- **Schwankende KI-Vorschlagsfelder stabilisiert – EP liefert jetzt IMMER alle geforderten
  Werte (D-050).** Bisher hing es vom Modell/Lauf ab, welche Felder kamen (mal nur die
  Priorität, mal alles, die Max-Wassertemperatur des Heizstabs fehlte gelegentlich), weil das
  Gemini-Antwort-Schema **alle** Geräte-Felder optional ließ und kein Determinismus gesetzt
  war. Behoben durch vier ineinandergreifende Schichten (Defense in Depth):
  - **Antwort-Schema erzwingt Felder:** `devices` ist jetzt ein Objekt je Gerätename statt eines
    Arrays; jedes Gerät trägt ein eigenes `required` = exakt sein Schreibvertrag (`suggestion_keys`)
    plus `propertyOrdering`. Das Modell darf kein gefordertes Feld mehr weglassen.
  - **Determinismus:** `temperature` (Default 0) + fixer `seed` (Default 42) in der
    `generationConfig` – gleicher Kontext ⇒ stabil dieselben Felder.
  - **Validator-Vollständigkeit (unabhängig vom Modell):** fehlt ein Gerät oder ein Pflichtfeld,
    ergänzt/füllt EP es deterministisch aus dem Ist-Zustand (Freigabe ← aktuelle technische
    Freigabe, geschützte Mindestleistung ← technische Mindestleistung/0, Zusatzwert ← aktueller
    Lesewert; fehlende Priorität wird ans Ende der 10er-Rangfolge gereiht) und protokolliert das.
  - **Gezielte Nachforderung:** bei Lücken fordert EP die fehlenden Felder einmalig gezielt nach,
    bevor die deterministische Füllung greift; scheitert der Aufruf, blockiert EP nie (Iron Rule 8).
  - Betrifft `gemini_provider.py`, `plan_context.py`, `validator.py`, `planner.py`, `config.py`,
    `config.yaml`. Neue Addon-Optionen `ai_temperature`, `ai_seed`, `ai_repair_missing`.

## [0.0.33] - 2026-07-03

### Behoben
- **Ursache des „Plan erzeugen"-Fehlers gefunden: das Default-Modell `gemini-3.5-flash`.**
  Diese Modell-ID lieferte in der Praxis keinen brauchbaren Lauf – der Aufruf hing „ewig",
  bis der HA-Ingress den Request mit einer HTML-Fehlerseite abbrach (im Frontend als
  `SyntaxError: Unexpected token '<', "<html> <h"...`). Der Default ist auf
  **`gemini-2.5-flash`** umgestellt (vom User als funktionierend verifiziert). Modell bleibt
  in der Addon-Config frei wählbar. Betrifft `config.yaml`, `config.py`, `gemini_provider.py`,
  Übersetzungen sowie die Doku (D-025 korrigiert).

### Geändert
- **Timeout-Obergrenze je KI-Aufruf von 120 s auf 600 s angehoben** (`ai_request_timeout_s`,
  Schema `int(5,600)`), damit auch langsamere Modelle mehr Zeit bekommen. **Hinweis:** Ein
  über die HA-Ingress-Zeitgrenze hinaus wartender Aufruf wird weiterhin vom Ingress als
  HTML-Seite abgebrochen – ein *schnelles* Modell (z.B. `gemini-2.5-flash`) ist die
  zuverlässige Lösung, nicht allein ein höheres Timeout. Default bleibt 30 s.
- **Plan-Tab verkraftet Nicht-JSON-Antworten sauber.** Die Fetches (`/api/plan/run`,
  `/api/plan`, `/api/plan/publish`) parsen die Antwort jetzt defensiv: liefert der Server
  bzw. der HA-Ingress ausnahmsweise eine HTML-Fehlerseite (z.B. Ingress-Timeout/502, den das
  Backend nicht abfangen kann), erscheint eine lesbare Meldung mit Hinweis aufs Addon-Log –
  nie wieder das kryptische „SyntaxError: Unexpected token '<'".

## [0.0.32] - 2026-07-03

### Behoben
- **„Plan erzeugen" scheiterte trotz 0.0.31 weiter mit „SyntaxError: Unexpected token '<',
  \"<html> <h\"... is not valid JSON".** Der Guard aus 0.0.31 umschloss nur den Lauf
  (`planner.run()`), **nicht** die abschließende JSON-Serialisierung der Antwort. Der zu
  Transparenzzwecken zurückgegebene `context` enthält beliebige gelesene Werte; ein einziger
  nicht-JSON-fähiger Wert darin (z.B. ein `datetime`) ließ `web.json_response(payload)`
  **außerhalb** des try werfen → aiohttp/Ingress lieferte eine **HTML-500-Seite** → im
  Frontend brach `response.json()` erneut ab. Fix: Der komplette Handler (Lauf **und**
  Serialisierung) liegt jetzt im try, und ein `_safe_dumps` (JSON mit `default=str`)
  entschärft unbekannte Typen im Diagnose-`context` zu ihrem String, statt die ganze Antwort
  zu blockieren (Iron Rule 8). Der Plan selbst besteht aus validierten Primitivwerten und ist
  unverändert JSON-sicher. Dieselbe Absicherung greift jetzt auch für `POST /api/plan/publish`
  und `GET /api/plan` (Serialisierung ebenfalls in den Guard gezogen).

## [0.0.31] - 2026-07-03

### Behoben
- **„Plan erzeugen" scheiterte mit „SyntaxError: The string did not match the expected
  pattern" statt einer lesbaren Ursache.** Trat im Lauf (`planner.run()`) ein **unerwarteter**
  Fehler auf, entwich er ungefangen aus dem Endpunkt `POST /api/plan/run`; aiohttp
  beantwortete den Request dann mit einer **HTML-500-Seite**. Im Frontend brach daraufhin
  `response.json()` mit der kryptischen JS-Meldung „SyntaxError: The string did not match the
  expected pattern" ab — der User sah nie die eigentliche Fehlerursache (Verstoß gegen Iron
  Rule 8: „die App blockiert nie, kontrollierte lesbare Fehler"). `plan_run` fängt unerwartete
  Fehler jetzt ab und liefert eine **strukturierte JSON-Antwort** (`ok=false` + Fehlertext, den
  der Plan-Tab anzeigt) samt geloggtem Traceback (EP-Logs/Fehler-Export). Der bereits
  vorhandene Lesepfad `GET /api/plan` (Öffnen des Plan-Tabs) wurde gegen denselben
  Ausfall (z.B. beschädigtes `plan_json` in der DB) abgesichert. **Hinweis:** Der
  Heizstab-`max_temperatur`-Vorschlag (früherer Hardcode D-035) ist vollständig auf die
  generischen Zusatz-Entitäten (D-047) migriert und war **nicht** die Ursache.
- **Paket-Version (`app/energy_pilot/__init__.py`) auf den Stand der Add-on-Version gebracht**
  (war 0.0.23 → 0.0.31), damit Statusseite/Logs die korrekte Version zeigen.

## [0.0.30] - 2026-07-02

### Hinzugefügt
- **Zusatz-Entitäten unterstützen jetzt auch `input_select`/`select` (D-049).** Die im Select
  verfügbaren Optionen (`options`-Attribut) werden der KI als **Wertepool** übergeben. Ist für die
  Entität ein Vorschlagswert gefordert, **muss** die KI **genau eine** dieser Optionen wählen: das
  Antwort-Schema erzwingt das per `enum`, und der lokale Validator verwirft einen Vorschlag
  außerhalb des Pools (advisorisch → der Sensor wird dann nicht geschrieben, der Plan bleibt gültig).
  Der Geräte-Tab zeigt die verfügbaren Optionen je Select-Zusatzentität an.

## [0.0.29] - 2026-07-02

### Geändert
- **Zusatz-Entitäten unterstützen jetzt alle HA-Domänen, nicht nur `input_number` (D-048).**
  Als Quell-Entität sind beliebige Domänen erlaubt (v.a. `sensor`, `input_number`,
  `input_boolean`, `input_datetime`, `input_text`). EP liest den Wert **typgerecht** und die KI
  liefert einen **typgerechten** Vorschlag (`sensor.ep_<obj>_vorschlag`):
  - `input_number` → Zahl; die **`min`/`max`-Attribute** der Quelle gehen als Ober-/Untergrenze
    an die KI und klemmen den Vorschlag.
  - `input_boolean` (+ switch/binary_sensor) → Ja/Nein.
  - `input_datetime` → Datum/Uhrzeit als String; die **`has_date`/`has_time`-Attribute** bestimmen
    das erwartete Format (`YYYY-MM-DD HH:MM:SS` / nur Datum / nur Uhrzeit), das der KI mitgegeben wird.
  - `input_text` → Text.
  - `sensor` u.a. → **auto**: Zahl, wenn der Zustand numerisch ist, sonst Text.
  Der Geräte-Tab zeigt je Zusatz-Entität den erkannten Typ samt Grenzen/Format; das Antwort-Schema
  der KI bekommt den passenden Typ (NUMBER/BOOLEAN/STRING).

## [0.0.28] - 2026-07-02

### Hinzugefügt
- **Konfigurierbare Zusatz-Entitäten je Gerät (D-047).** Im **Geräte-Tab** kann der User jetzt
  zu jedem vom HEMS importierten Gerät beliebige weitere Entitäten hinterlegen (z.B.
  `input_number.min_soc_auto`), die EP **zusätzlich** zu den `ems_*`-Werten liest. Pro Eintrag:
  - **Checkbox „KI liefert Vorschlagswert"** – ist sie aktiv, erzeugt die KI zusätzlich einen
    Sensor nach dem Schema `sensor.ep_<entität>_vorschlag` (Beispiel:
    `input_number.min_soc_auto` → `sensor.ep_min_soc_auto_vorschlag`).
  - **Freitextfeld** – erklärt der KI Bedeutung und Verwendung/Interpretation des Werts; geht als
    Feldbeschreibung und als `zusatzwerte`-Hinweis in den KI-Kontext ein.
  - **Optionaler Anzeigename + Einheit** für den HA-Sensor.
  Diese Vorschläge sind **advisorisch**: sie werden **nur als HA-Sensor** bereitgestellt und
  **nicht an das HEMS** übergeben (das HEMS kennt sie nicht). Auch ohne aktivierten KI-Vorschlag
  wird der Wert gelesen und der KI als Kontext übergeben. Persistenz in der neuen Tabelle
  `device_extras` (Migration 6); neue Endpunkte `POST`/`DELETE /api/devices/extras`.

### Geändert
- **Heizstab-Max.-Wassertemperatur ist nicht mehr hardcodiert (löst D-035 durch D-047 ab).** Der
  frühere Sonderfall (`input_number.ep_heizstab_max_temperatur` → `sensor.ep_heizstab_max_temperatur_vorschlag`)
  wird beim ersten HEMS-Sync **einmalig als editierbare Zusatz-Entität geseedet** – Namensschema
  und Verhalten bleiben identisch, sind aber jetzt frei umkonfigurier-/löschbar. Da Zusatz-Vorschläge
  advisorisch sind, klemmt der Validator die Wassertemperatur nicht mehr gegen eine harte Grenze;
  der Freitext steuert die KI.

## [0.0.27] - 2026-07-02

### Behoben
- **Plan-Rückkopplung: geschützte Mindestleistung wird jetzt auch für Ampere-Geräte (Wallbox)
  gegen den HEMS-Ist-Wert verglichen.** Bisher behandelte `plan_feedback._compare` nur die
  Watt-Variante (`geschutzte_mindestleistung_w_vorschlag` ↔ HEMS `schutz_w`); der Ampere-Vorschlag
  (`geschutzte_mindestleistung_a_vorschlag`) fiel auf „kein HEMS-Pendant" → Status „unbekannt",
  Ist „–". Watt-Geräte zeigten den Vergleich, Ampere-Geräte (Wallbox) nicht. **Fix:** EP
  vergleicht den Ampere-Vorschlag gegen das neue HEMS-Statusfeld `schutz_a` (HEMS rechnet
  `schutz_w` über Phasen × Spannung nach Ampere um) mit eigener Ampere-Toleranz (±0.1 A). Setzt
  HEMS mit `schutz_a` im `/api/status` voraus.

## [0.0.26] - 2026-07-02

### Geändert
- **Geräte-Discovery ausschließlich über das HEMS** (D-046). Sind HEMS und Energy Pilot
  verbunden und im HEMS Geräte eingerichtet, zieht EP die komplette Geräteliste vom HEMS
  (`/api/device_controls_schema`) – die Namenskonvention (`name`/`entity_prefix`) wird 1:1
  übernommen, EP-eigene Entitäten bleiben `ep_*`. Der bisherige Geräte-Fallback in der
  Addon-Config brachte bei HEMS-Ausfall ohnehin nichts, weil das HEMS die EP-Vorschläge bei
  eigener Nichtverfügbarkeit gar nicht verarbeiten kann (Leitsatz „EP ohne HEMS sinnlos").

### Hinzugefügt
- **Auto-Retry der Geräte-Discovery beim Start** (D-046): Ist das HEMS zum EP-Start noch nicht
  erreichbar (Home Assistant garantiert keine Addon-Startreihenfolge), wiederholt EP die
  Discovery **bis zu 5×** im Abstand von **30 s** und erholt sich ohne Neustart, sobald das
  HEMS oben ist.
- **Manueller „Geräte von HEMS neu laden"-Button** im HEMS-Tab der EP-Oberfläche: synchronisiert
  die Geräteliste jederzeit neu vom HEMS (Endpoint `POST /api/hems/rediscover`) und baut dabei
  die Lese-Allowlist neu auf, sodass Entitäten umbenannter/entfernter Geräte verschwinden.

### Entfernt
- Addon-Config-Option `devices` (Fallback-Geräteliste) inkl. `config.yaml`-Schema – ersatzlos,
  da die Geräte nun vollständig vom HEMS kommen.

## [0.0.25] - 2026-07-01

### Behoben
- **Geräte-Identität hängt jetzt am technischen `name`, nicht mehr am Anzeige-`label`.**
  Wurde in der HEMS-Geräteverwaltung nur das **Label** geändert (z.B. „Wallbox" → „Wallbox
  Test"), konnte die Zuordnung im HEMS-Tab kippen bzw. das Gerät als „unbekannt – nicht im
  HEMS gefunden" erscheinen. Ursache: EP kannte den technischen HEMS-`name`/`id` gar nicht –
  das Kontrollschema (`/api/device_controls_schema`) lieferte nur `label` + Entitäten, sodass
  EP die Identität aus dem `entity_prefix` rekonstruierte und die HEMS-Korrelation faktisch am
  Label hing. Die 0.0.24-Slug-Faltung milderte das nur, behob es aber nicht.
- **Fix:** HEMS liefert im Schema nun zusätzlich das Feld `name` (technischer Bezeichner,
  deckt sich mit der `id` in `/api/status`). `devices.discover_from_hems_schema` nutzt dieses
  `name` als Geräte-`name` (Identität), `label` bleibt reiner Anzeigename und `entity_prefix`
  weiterhin das Entitätspräfix für die `ems_*`-Reads. Fehlt `name` (ältere HEMS-Version), wird
  wie bisher auf das Präfix zurückgefallen. Ein Label-Rename ändert die Zuordnung damit nicht
  mehr. Setzt HEMS ≥ 1.0.26 voraus, ist aber abwärtskompatibel.

## [0.0.24] - 2026-06-28

### Behoben
- **HEMS-Tab: Geräte-Matching slug-tolerant (Umlaut/Trenner/Groß-Klein).** Binäre Geräte
  (z.B. Heizlüfter 1/2) wurden im HEMS-Tab als „unbekannt – nicht im HEMS gefunden" angezeigt,
  obwohl in HEMS **und** EP angelegt. Ursache: `plan_feedback._match_hems_device` verglich
  EP-Label/-Name gegen HEMS-`label`/`id` nur mit `casefold` — ohne Faltung von `ü`↔`u`,
  `_`↔Leerzeichen. EP entdeckt das Label aus dem Schema-Endpoint (title-case), matcht aber gegen
  den Status-Endpoint (Rohname) → Divergenz speziell bei Namen mit Underscore/Umlaut. Neuer
  `_slug()` (casefold + HA-Umlaut-Faltung + nur Alphanumerik); Match prüft jetzt beide EP-Achsen
  gegen beide HEMS-Achsen slug-gefaltet. Einwortige kleingeschriebene Geräte (Batterie, Heizstab)
  waren nie betroffen.

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
