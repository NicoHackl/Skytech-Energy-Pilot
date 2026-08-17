# Decision-Log (verdichtet, D-001 … D-059)

Verdichtete Fassung des alten `plan/entscheidungen.md` (gelöscht 10.07.2026, voller
Text weiterhin abrufbar via `git show ad48b23^:plan/entscheidungen.md`). Jede Zeile:
Entscheidung + Kernaussage. Für Details/Begründung den Volltext in der Git-Historie
nachschlagen oder die themenspezifischen Dateien in diesem Ordner ([namensschema.md](namensschema.md),
[geraete.md](geraete.md), [steuermodi.md](steuermodi.md), [planungs-engine.md](planungs-engine.md) …).

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
| D-025 | Default-Modell korrigiert auf `gemini-2.5-flash` — `gemini-3.5-flash` hing in der Praxis (siehe [bekannte-luecken.md](bekannte-luecken.md#gemini-35-flash-hang)) |
| D-026 | PV-Prognosewerte im Sensor-**State**, nicht als Attribut |
| D-027 | Sensor-Mapping in Addon-Config (`entity_<rolle>`), UI zeigt nur read-only an |
| D-028 | Docker-Build direkt auf `python:3.11-slim`, kein HA-Base-Image/s6 (siehe [bekannte-luecken.md](bekannte-luecken.md#s6-overlay-token-bug)) |
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
| D-050 | Stabile/vollständige KI-Vorschlagsfelder: 4-schichtige Determinismus-/Vollständigkeits-Absicherung (siehe [planungs-engine.md](planungs-engine.md)) |
| D-051 | Geräte-Tab als Einzelgerät-Dropdown + Pro-Gerät-KI-Beschreibungsfeld (`funktion`) |
| D-052 | Zusatz-Entitäten: optionales "In Original schreiben" über HA-Service-Calls, nur für echte Helfer-Domänen |
| D-053 | Arbeits-Branch `claude/main` → `claude/stage` umbenannt; 3 Release-Channel-Branches `stage/dev`/`stage/beta`/`stage/stable` (je eigenes `config.yaml`, in HA per Branch-URL als 3 separate Addons einbindbar), Promotion nur manuell auf Zuruf, CI auf allen 4 Branches. **Nachtrag:** angelegt wurden die Kanäle als `stage-dev`/`stage-beta`/`stage-stable` (Bindestrich); verbindlich sind diese real existierenden Namen, CI und Doku sind darauf gezogen |
| D-054 | Harte Regel „`technische_freigabe=false` blockiert `freigabe_vorschlag=true`" entfernt: sie ist nur der AKTUELLE Ist-Zustand, kein Verbot für den gesamten Planzeitraum. Betrifft Validator-Stufe 2 (kein Reject mehr) und Freigabe-Hysterese (kein Sofort-Override mehr); bleibt als Fallback-Startwert bei fehlendem KI-Feld |
| D-055 | Statische `objective_weights` (Addon-Config) entfernt: User definiert eigene Ziele (id/name/beschreibung/Geräte-Liste, KEIN Gewicht) im Tab "Grenzen und Ziele" (DB-Tabelle `ziele`). Vorgelagerter Klassifizierungs-LLM-Aufruf (gleiche Datenbasis wie der Plan-Aufruf) leitet die Gewichtung je Planungslauf ab; eigener editierbarer Klassifizierungs-Prompt im Plan-Tab. Migration ohne Seed-Daten (leer starten); scheitert Klassifizierung ODER Plan-Aufruf, gilt der gesamte Lauf als gescheitert |
| D-056 | Multi-Provider: 3 umschaltbare KI-Anbieter (Gemini/Claude/OpenAI). Top-Level-Radio `provider` + je Anbieter ein aufklappbares Untermenü `providers.<name>` (api_key/model/timeout_s/rate_limit_per_min); frühere flache Top-Level-Keys entfallen. Alle drei als schlanke aiohttp-REST-Clients (kein SDK, `AIProvider`-Abstraktion): `claude_provider.py` (Messages-API, `output_config.format`), `openai_provider.py` (Chat-Completions, `response_format`/Strict, temperature/seed-Retry für Reasoning-Modelle wie gpt-5). `schema_convert.to_json_schema` übersetzt das Gemini-Antwortschema in Standard-JSON-Schema. `ai_temperature`/`ai_seed` geteilt (Claude ohne Sampling). `resolve_active_provider` mit Legacy-Fallback (Gemini) für bestehende Installationen. Default-Modelle: `gemini-2.5-flash`/`claude-sonnet-5`/`gpt-5` |
| D-057 | Modus-Gate für den Original-Schreibweg (D-052): EP schreibt einen KI-Vorschlag nur dann in die Original-Entität, wenn die Modus-Achse für das Gerät die Quelle `ep` ergibt — im manuellen Modus bleibt der Nutzerwert stehen. Logik als Portierung von HEMS `Device.resolve_source` in `control_mode.py` (global `input_select.ems_regelmodus` + je Gerät `input_select.ems_<prefix>_modus`; `auto`=KI/EP, `manuell`=normale Regeln, `aus`=aus), inkl. HEMS-Asymmetrie: global `auto` überstimmt Gerät `manuell`, nur Gerät `aus` vetot global `auto`. Bewusst **nur** die Modus-Achse — `ems_pv_regelung_aktiv`/`hard_lockout`/`allowed_modes` werden nicht nachgebaut (Zusatz-Entitäten sind advisorisch/nicht HEMS-relevant, `hard_lockout` ist ein PV-Notabwurf, `allowed_modes` steht in der HEMS-Config). Gate sitzt in `publish_suggestions` (einziger gemeinsamer Nenner von `Planner.run()` und `publish_latest()`), Modus wird frisch zum Schreibzeitpunkt gelesen. Fail-safe: fehlender globaler Helfer/HA-Fehler ⇒ `aus` (kein Schreiben); fehlender Geräte-Helfer (404) ⇒ Durchfall wie im HEMS. `sensor.ep_*_vorschlag` bleibt ungegated (Vorschlag auch im manuellen Modus sichtbar); gesperrte Vorgänge stehen als `skipped` in Ergebnis/Audit/UI |

| D-058 | Regelwerk vereinheitlicht: **`AGENTS.md`** im Repo-Root ist die einzige Quelle der Projektregeln; `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` und `.cursor/rules/` sind reine Verweise ohne eigene Regeln. Doku von `doc/` nach **`docs/`** mit deutschen Dateinamen, ergänzt um `git-workflow.md`, `test-strategie.md`, `frontend.md`, `design-system.md` und `adr/`. Präzedenz: User-Anweisung > `user-beispiele/` > `AGENTS.md` > `docs/` |
| D-059 | **Oberfläche auf React 18 + TypeScript (`strict`) + Vite** umgestellt (löst die Preact/htm-SPA von 0.0.39 ab). Navigation als Sidebar nach Design-System, Designsprache fest `data-design="ha"` (Akzent `#18BCF2`), sichtbarer Hell/Dunkel-Schalter mit `localStorage`. Vier begründete Abweichungen vom Standardmuster, alle durch den HA-Ingress erzwungen: API-Pfade **ohne** führenden Slash, `HashRouter` statt `BrowserRouter`, `base: './'` in Vite, kein Auth-Provider. Das gebaute Bündel (`frontend/dist`) wird **mitcommittet**, damit im Addon-Image kein Node laufen muss; die CI baut gegen und schlägt bei Abweichung an. Ausführlich: [adr/D-059-frontend-react.md](adr/D-059-frontend-react.md) |
| D-060 | **Geräteregeln als Freitext statt typisiertem Regelwerk, dafür Begründungspflicht.** Der User pflegt je Gerät (`device_regeln`) und einmal hausweit (KV-Key `global_regeln`) in eigenen Worten, unter welchen Bedingungen ein Gerät laufen soll. Die Regeln gehen als eigener, im Prompt referenzierter Block in den Kontext und werden **nicht** nachträglich gegen die Modellantwort erzwungen. Gegenkontrolle ist die erzwungene Selbsterklärung je Gerät (`begruendung` + `angewandte_regeln` als Pflichtfelder im Antwortschema): eine Fehlentscheidung wird dadurch lesbar statt rätselhaft. Bewusst **verworfen**: eine typisierte Regel-Engine mit Override der KI-Felder sowie jede nachgelagerte Dämpfung (Freigabe-Hysterese, Mindesthaltezeit, Delta-Limit D-021) — Vorgabe des Users, die Ergebnisse der KI selbst müssen besser werden, nicht ihre Nachbearbeitung. Bleibt als dokumentierte Rückfallebene, falls Freitext nicht genügt. Ausführlich: [adr/D-060-freitext-regeln.md](adr/D-060-freitext-regeln.md) |
| D-061 | **Warmwasser- und Außentemperatur als eigene Mess-Rollen** (`hot_water_temp`, `outdoor_temp`) statt nur als Zusatzwert — **gemittelt** geführt, als bewusste Ausnahme zu D-003 (Temperaturen als Letztwert). Nicht der Absolutwert trägt die Information, sondern der Verlauf: eine steigende Speichertemperatur ohne Heizstableistung heißt „eine andere Wärmequelle (Solarthermie) lädt gerade". Zusätzlich bekommt jeder Zusatzwert eine typisierte `rolle` (`ist`/`grenze`/`sollwert`), weil ein als Messwert missverstandener Sollwert der belegte Auslöser eines Fehlvorschlags war (Obergrenze 85 °C gelesen als Ist-Temperatur, Vorschlag 80 °C bei real 76,1 °C im Speicher). Backfill ohne Raten: Zusatzwerte mit KI-Vorschlag sind per Definition Vorgaben (`sollwert`), reine Lesewerte `ist` |
| D-062 | **Instruktion in den System-Kanal, Grenzen ins Antwortschema.** Rolle, Regeln und Antwortvertrag gehen als `systemInstruction` (Gemini) / `system` (Claude) / `messages[role=system]` (OpenAI), die Daten bleiben User-Nachricht; vorher lagen Anweisung und ein mehrere Kilobyte großer JSON-Block in derselben User-Message. Zusätzlich reisen die harten Grenzen als `minimum`/`maximum` mit im Antwortschema (Prio 10–100, Schutzleistung im technischen Band, Zusatzwert-Grenzen) statt nur als Prosa, und die verdichteten Wetter-Kennzahlen (`weather.kennzahlen`: `temp_max_heute`, `temp_max_24h`, `temp_max_48h`, `pop_max_24h` …) schließen das Abendloch der Slot-Reihen (intraday endet 21 Uhr Ortszeit, die Tagesreihe überspringt heute) |
| D-063 | **Kontext quantisieren, Hash bilden, Plan wiederverwenden.** `valid_from`/`valid_until` liegen auf einem 15-Minuten-Raster, alle Zahlen im Kontext sind auf fachliche Stufen gerundet (Leistung 10 W, Prozent 1, Temperatur 0,5 °C) — erst dadurch ist der Prompt bei gleicher Sachlage derselbe String und ein fixer `seed` überhaupt wirksam. Über den quantisierten Kontext plus Instruktion und Modellname entsteht ein SHA-256-Hash; stimmt er mit dem letzten **gültigen, noch laufenden** Plan überein, wird dieser wiederverwendet und **kein** KI-Aufruf gemacht (beendet „fünfmal drücken, fünf Antworten"). `now` und `previous_plan` bleiben aus dem Hash heraus — das eine ändert sich zwangsläufig, das andere ist EPs eigene Ausgabe und keine neue Information. Prompt, Kontext, Roh-Antwort und Hash werden je Lauf persistiert (vorher war ein Lauf nicht reproduzierbar), der Sampling-Fallback von Reasoning-Modellen wird als WARNING geloggt und in `ai_calls` vermerkt (vorher stumm), und `ai_thinking_budget` macht den Denkaufwand explizit |
| D-064 | **Konfidenz als definierte Teilnoten mit Gegenrechnung, erst darauf das Gate.** `confidence` war ein freies INTEGER 0–100 ohne jede Definition — als Grundlage eines Veröffentlichungs-Gates wertlos. Das Modell liefert jetzt vier Pflicht-Teilnoten mit Rubrik im Schema (`datenlage`, `prognosesicherheit`, `regelklarheit`, `zielkonflikt`) plus `unsicherheiten` als Freitextliste. EP aggregiert in Code als **schwächstes Glied** (Minimum, nicht Mittelwert — sonst rechnete eine klare Regel schlechte Daten weg) und deckelt die `datenlage`-Note gegen die real gemessene Datenlage des Kontexts (`min(Modell, EP)`, Abweichung als Klemmung protokolliert). Grundlage dafür ist Validator-Stufe 4: jeder Kontextwert trägt `veraltet`, `datenlage.frische_prozent` zählt den belegten Anteil. Stufe 6 nutzt das Ergebnis: unter `min_confidence_percent` wird der Plan gespeichert und angezeigt, aber **nicht** nach HA geschrieben (`publish_blocked`) — er ist nicht ungültig, nur nicht wirksam |

## Noch offen (Stand letzter alter Doku-Fassung)

- Ampere-Suffix-Variante (`_a`) formal bestätigt (HEMS unterstützt sie nativ), aber
  kein eigener D-Eintrag.
- Hybrid-Modus: welche Felder pro Gerät fixierbar sind — ungeklärt, relevant erst ab M3.
- Gemeinsames Plan-JSON-Schema mit dem HEMS-Repo für den Ebene-2-Schreibweg — noch
  klärungsbedürftig bei der Suffix-Zuordnung (siehe [namensschema.md](namensschema.md)).
- OWM aktuelles Wetter (nicht Prognose), Mehrfach-Timeline-an-KI gleichzeitig,
  historische Wetterdaten — bewusst zurückgestellt.
