# Decision-Log (verdichtet, D-001 … D-057)

Verdichtete Fassung des alten `plan/entscheidungen.md` (gelöscht 2026-07-10, voller
Text weiterhin abrufbar via `git show ad48b23^:plan/entscheidungen.md`). Jede Zeile:
Entscheidung + Kernaussage. Für Details/Begründung den Volltext in der Git-Historie
nachschlagen oder die themenspezifischen Dateien in diesem Ordner ([entity-naming.md](entity-naming.md),
[devices.md](devices.md), [control-modes.md](control-modes.md), [planning-engine.md](planning-engine.md) …).

Wo eine spätere Entscheidung eine frühere überholt hat, ist das vermerkt.

| # | Kernaussage |
|---|---|
| D-001 | Sensorwerte live übergeben, EP mittelt selbst über 1/15/60-min-Fenster (Leistungsgrößen); SOC/Temperaturen/Zeiten/Zustände als Letztwert |
| D-002 | HEMS-Anbindung gestaffelt: V1 nur HA-Helfer/`/api/set`, später versionierter Plan-Endpunkt im HEMS-Repo |
| D-003 | Mittelungsfenster fix 1/15/60 min, keine Ereigniskopplung, Langzeitprognose nutzt nur 60-min |
| D-004 | Entity-Namensschema an HEMS angelehnt (später von D-029/D-030 überholt) |
| D-005 | HA-Helfer nicht automatisch angelegt, fertige `<domain>_ep.yaml`-Pakete in `claude-ha-config-dateien/` |
| D-006 | PV-Prognose/Preis aus bestehenden HA-Sensoren, Namen in Addon-Config |
| D-007 | Start-KI-Provider Google Gemini, Provider/Modell in Addon-Config umschaltbar, Keys nie geloggt |
| D-008 | V1: KI liefert nur Vorschlagswerte, keine Übernahme |
| D-009 | Drei Steuermodi als Langzeitziel: Manuell/Hybrid/Automatisch, eigene Achse zu den Betriebsmodi |
| D-010 | UI startet einfach: serverseitige SPA, aiohttp, vanilla JS/CSS wie HEMS |
| D-011 | Weiche Zielgewichte in Addon-Config, Initialwerte aus info.md §7 |
| D-012 | Datenspeicherung von Anfang an auf 1/15/60-min-Aggregation ausgelegt |
| D-013 | EP↔HEMS-Auth über Supervisor-Proxy/Token; externer Zugriff (iOS/Java-Backend) muss architektonisch sauber möglich bleiben |
| D-014 | Auto-Export eines KI-lesbaren Log-Bundles bei ERROR/CRITICAL |
| D-015 | CI muss mindestens HEMS↔EP-Zusammenspiel testen |
| D-016 | Batterie (E3DC): immer Prio 1, immer freigegeben, kein SOC-Limit, keine Entladung, nur max. Ladeleistung relevant |
| D-017 | Heizlüfter 1&2: feste 1500 W, kein Leistungs-Helfer, nur Freigabe-Schalter |
| D-018 | Strompreis für V1 raus; PV-Prognose: mehrere Sensoren je Ausrichtung, EP summiert, 4 Werte je Sensor |
| D-019 | Gemini-Modell in Addon-Config wählbar (konkreter Default noch offen, siehe D-025) |
| D-020 | Steuermodus-Geltung: global=Hybrid → pro Gerät verfeinerbar; global=Manuell/Automatisch → gilt für alle |
| D-021 | Mindestkonfidenz 70 %, Delta-Limit ±20 % Leistung/±10 % SOC-Ziel — Claude-Vorschlagswerte, konfigurierbar |
| D-022 | Branch-Regel (Arbeits-Branch, seit D-053 `claude/stage`) gilt auch im SkytechHEMS-Repo |
| D-023 | Externer Zugriff startet über HA Long-Lived Token, eigener EP-Endpunkt evtl. später |
| D-024 | CI-Coverage-Gate startet bei 60 %, CI läuft auf `claude/stage` + den drei Release-Channel-Branches (seit D-053) |
| D-025 | Default-Modell korrigiert auf `gemini-2.5-flash` — `gemini-3.5-flash` hing in der Praxis (siehe [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md#gemini-35-flash-hang)) |
| D-026 | PV-Prognosewerte im Sensor-**State**, nicht als Attribut |
| D-027 | Sensor-Mapping in Addon-Config (`entity_<rolle>`), UI zeigt nur read-only an |
| D-028 | Docker-Build direkt auf `python:3.11-slim`, kein HA-Base-Image/s6 (siehe [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md#s6-overlay-token-bug)) |
| D-029 | **Zentral:** Namens-Domäne nach Datenrichtung — `ems_*` = HEMS-Domäne (EP liest), `ep_*` = EP-Domäne (EP schreibt) |
| D-030 | EP-Schreibvertrag Phase 1: `prio_vorschlag`, `geschutzte_mindestleistung_w/a_vorschlag`, `freigabe_vorschlag` |
| D-031 | Jeder binäre Verbraucher hat `ems_<name>_leistung_w` als Ist-Leistung |
| D-032 | Schreibweg gestaffelt: V1 nur HA-Helfer, später zusätzlich 1:1 direkt in HEMS-Variablen |
| D-033 | V1: Vorschläge nur nach HA geschrieben, User verdrahtet sie selbst über Automationen |
| D-034 | Regelbarer Verbraucher-Schreibvertrag = binär + `freigabe_vorschlag` |
| D-035 | Heizstab-Max-Wassertemperatur ist nicht HEMS-relevant — Ausnahme zu D-029 (`ep_*`-Wert, den EP nur liest); später generalisiert zu D-047 |
| D-036 | `ems_*`-Helfer sind HEMS-definiert, kein EP-Template — EP entdeckt Entity-IDs via `/api/device_controls_schema` |
| D-037 | Batterie schreibt nur `ep_batterie_geschutzte_mindestleistung_w_vorschlag` |
| D-038 | Entity-Allowlist vollständig aus drei Config-Quellen abgeleitet, Durchsetzung weich (loggt, blockiert nicht) |
| D-039 | Plan-Validierung: Struktur via `jsonschema`, Geschäftslogik im lokalen Validator |
| D-040 | M2 startet mit deterministischer, KI-freier Basis (Constraints/Objectives/Schema/Validator) vor der Gemini-Integration |
| D-041 | Gemini-Provider via REST/aiohttp, EP setzt Plan-Metadaten selbst, nie das Modell |
| D-042 | Wetterprognose direkt in EP über OpenWeatherMap, nicht über HA-Sensoren |
| D-043 | Wetter fließt in den KI-Kontext, Detailgrad umschaltbar (`compact`/`full`), Planungs-Prompt in UI editierbar |
| D-044 | OpenWeatherMap One Call API 4.0 als Opt-in-Alternative, Timelines einzeln aktivierbar |
| D-045 | One-Call-Paginierung konfigurierbar, harte Tagesbudget-Grenze (Default 1000), Unwetterwarnungen (nur Anzeige) |
| D-046 | Geräte-Discovery ausschließlich über HEMS, Addon-Config-Fallback ersatzlos entfernt, Auto-Retry + manueller Sync |
| D-047 | Konfigurierbare Zusatz-Entitäten je Gerät (löst Heizstab-Hardcode D-035 ab) |
| D-048 | Zusatz-Entitäten unterstützen alle HA-Domänen, Typ folgt Domäne, `min`/`max` als KI-Grenzen + Klemmung |
| D-049 | Zusatz-Entitäten unterstützen `input_select`/`select`, KI muss exakt eine Option wählen |
| D-050 | Stabile/vollständige KI-Vorschlagsfelder: 4-schichtige Determinismus-/Vollständigkeits-Absicherung (siehe [planning-engine.md](planning-engine.md)) |
| D-051 | Geräte-Tab als Einzelgerät-Dropdown + Pro-Gerät-KI-Beschreibungsfeld (`funktion`) |
| D-052 | Zusatz-Entitäten: optionales "In Original schreiben" über HA-Service-Calls, nur für echte Helfer-Domänen |
| D-053 | Arbeits-Branch `claude/main` → `claude/stage` umbenannt; 3 Release-Channel-Branches `stage/dev`/`stage/beta`/`stage/stable` (je eigenes `config.yaml`, in HA per Branch-URL als 3 separate Addons einbindbar), Promotion nur manuell auf Zuruf, CI auf allen 4 Branches. **Nachtrag:** angelegt wurden die Kanäle als `stage-dev`/`stage-beta`/`stage-stable` (Bindestrich); verbindlich sind diese real existierenden Namen, CI und Doku sind darauf gezogen |
| D-054 | Harte Regel „`technische_freigabe=false` blockiert `freigabe_vorschlag=true`" entfernt: sie ist nur der AKTUELLE Ist-Zustand, kein Verbot für den gesamten Planzeitraum. Betrifft Validator-Stufe 2 (kein Reject mehr) und Freigabe-Hysterese (kein Sofort-Override mehr); bleibt als Fallback-Startwert bei fehlendem KI-Feld |
| D-055 | Statische `objective_weights` (Addon-Config) entfernt: User definiert eigene Ziele (id/name/beschreibung/Geräte-Liste, KEIN Gewicht) im Tab "Grenzen und Ziele" (DB-Tabelle `ziele`). Vorgelagerter Klassifizierungs-LLM-Aufruf (gleiche Datenbasis wie der Plan-Aufruf) leitet die Gewichtung je Planungslauf ab; eigener editierbarer Klassifizierungs-Prompt im Plan-Tab. Migration ohne Seed-Daten (leer starten); scheitert Klassifizierung ODER Plan-Aufruf, gilt der gesamte Lauf als gescheitert |
| D-056 | Multi-Provider: 3 umschaltbare KI-Anbieter (Gemini/Claude/OpenAI). Top-Level-Radio `provider` + je Anbieter ein aufklappbares Untermenü `providers.<name>` (api_key/model/timeout_s/rate_limit_per_min); frühere flache Top-Level-Keys entfallen. Alle drei als schlanke aiohttp-REST-Clients (kein SDK, `AIProvider`-Abstraktion): `claude_provider.py` (Messages-API, `output_config.format`), `openai_provider.py` (Chat-Completions, `response_format`/Strict, temperature/seed-Retry für Reasoning-Modelle wie gpt-5). `schema_convert.to_json_schema` übersetzt das Gemini-Antwortschema in Standard-JSON-Schema. `ai_temperature`/`ai_seed` geteilt (Claude ohne Sampling). `resolve_active_provider` mit Legacy-Fallback (Gemini) für bestehende Installationen. Default-Modelle: `gemini-2.5-flash`/`claude-sonnet-5`/`gpt-5` |
| D-057 | Modus-Gate für den Original-Schreibweg (D-052): EP schreibt einen KI-Vorschlag nur dann in die Original-Entität, wenn die Modus-Achse für das Gerät die Quelle `ep` ergibt — im manuellen Modus bleibt der Nutzerwert stehen. Logik als Portierung von HEMS `Device.resolve_source` in `control_mode.py` (global `input_select.ems_regelmodus` + je Gerät `input_select.ems_<prefix>_modus`; `auto`=KI/EP, `manuell`=normale Regeln, `aus`=aus), inkl. HEMS-Asymmetrie: global `auto` überstimmt Gerät `manuell`, nur Gerät `aus` vetot global `auto`. Bewusst **nur** die Modus-Achse — `ems_pv_regelung_aktiv`/`hard_lockout`/`allowed_modes` werden nicht nachgebaut (Zusatz-Entitäten sind advisorisch/nicht HEMS-relevant, `hard_lockout` ist ein PV-Notabwurf, `allowed_modes` steht in der HEMS-Config). Gate sitzt in `publish_suggestions` (einziger gemeinsamer Nenner von `Planner.run()` und `publish_latest()`), Modus wird frisch zum Schreibzeitpunkt gelesen. Fail-safe: fehlender globaler Helfer/HA-Fehler ⇒ `aus` (kein Schreiben); fehlender Geräte-Helfer (404) ⇒ Durchfall wie im HEMS. `sensor.ep_*_vorschlag` bleibt ungegated (Vorschlag auch im manuellen Modus sichtbar); gesperrte Vorgänge stehen als `skipped` in Ergebnis/Audit/UI |

## Noch offen (Stand letzter alter Doku-Fassung)

- Ampere-Suffix-Variante (`_a`) formal bestätigt (HEMS unterstützt sie nativ), aber
  kein eigener D-Eintrag.
- Hybrid-Modus: welche Felder pro Gerät fixierbar sind — ungeklärt, relevant erst ab M3.
- Gemeinsames Plan-JSON-Schema mit dem HEMS-Repo für den Ebene-2-Schreibweg — noch
  klärungsbedürftig bei der Suffix-Zuordnung (siehe [entity-naming.md](entity-naming.md)).
- OWM aktuelles Wetter (nicht Prognose), Mehrfach-Timeline-an-KI gleichzeitig,
  historische Wetterdaten — bewusst zurückgestellt.
