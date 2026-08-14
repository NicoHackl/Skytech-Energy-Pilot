# Architektur

## Projektzweck

**Skytech Energy Pilot (EP)** ist ein eigenständiges Home-Assistant-Addon für
KI-gestützte, vorausschauende **strategische** Energieplanung (Horizont 24–48 h).
EP **plant**, das separate **HEMS-Addon regelt**. EP steuert niemals Geräte direkt.

| | HEMS (Basis, Pflicht) | EP (optionale KI-Erweiterung) |
|---|---|---|
| Repo | [SkytechHEMS](https://github.com/NicoHackl/SkytechHEMS) | dieses Repo |
| Zyklus | Echtzeit, 1–2 s | 15–60 min (aktuell: nur manuell ausgelöst, siehe unten) |
| Aufgabe | PV-Überschussverteilung, tatsächliche Sollwerte, Geräte-Ansteuerung, Hysterese/Rampen/Mindestlaufzeiten | Priorität/Freigabe/Schutzleistung je Gerät als **Vorschlag** |
| Ohne das jeweils andere | voll funktionsfähig | sinnlos (EP ohne HEMS hat keine Wirkung) |

Warum getrennte Addons: der schnelle HEMS-Regelkreis bleibt unabhängig von
KI/Internet/Cloud; ein EP-Ausfall gefährdet nie die sichere Basisregelung; HEMS
funktioniert komplett eigenständig; der KI-Provider ist unabhängig vom HEMS
austauschbar; getrennte Repos/Logs/Versionierung.

## Tech-Stack

- Python 3.11, **aiohttp** (Webserver + Ingress), SQLite (WAL-Modus).
- Frontend: serverseitig gerenderte SPA, vanilla JS + Preact/htm (kein Build-Schritt),
  HA-Material-Theme nachgebildet, hell/dunkel via `prefers-color-scheme`.
- HA-Zugriff über den Supervisor-Core-API-Proxy (`http://supervisor/core/api`),
  Token via `SUPERVISOR_TOKEN`/`HASSIO_TOKEN`/`HA_TOKEN` (erster Treffer gewinnt).
- Docker-Basis-Image bewusst `python:3.11-slim` **statt** offizielles
  HA-Base-Image — siehe [bekannte-luecken.md](bekannte-luecken.md#s6-overlay-token-bug).

## Boot-Sequenz (`app/main.py: build()`)

1. `AddonConfig.load()` — `/data/options.json` über `DEFAULTS` gelegt.
2. `setup_logging()` — strukturiertes JSON-Logging, Secrets werden redaktiert.
3. `init_db()` — SQLite-Migrationen anwenden (siehe [datenmodell.md](datenmodell.md)).
4. `EntityAllowlist` aufbauen.
5. `HAClient` — nur falls `supervisor_token` vorhanden, sonst HA-Zugriff deaktiviert (Warnung).
6. `StateCollector` + Rollen-Mapping (`sensoren`-Config).
7. `HEMSClient` — nur falls `hems_base_url` gesetzt.
8. `DeviceCollector`, `ForecastCollector` (PV).
9. Wetter-Collector — `OneCallCollector` oder `WeatherCollector`, je nach `weather.source`.
10. KI-Provider — `resolve_active_provider()` löst `provider` + das Untermenü
    `providers.<name>` auf und baut genau einen von drei Clients (`GeminiProvider`/
    `ClaudeProvider`/`OpenAIProvider`, D-056); ohne `api_key` bleibt die Planung deaktiviert.
11. `Planner` — wird **immer** gebaut, auch ohne Provider (damit `/api/plan` Historie zeigen kann).
12. `HEMSStatusCollector` — nur falls HEMS konfiguriert.
13. `create_app(...)` — aiohttp-App inkl. aller `on_startup`/`on_cleanup`-Hooks.

`on_startup` löst zusätzlich aus: HA-Selbsttest, initiale Geräte-Discovery (mit
begrenztem Auto-Retry, siehe [geraete.md](geraete.md)), Start des Poller-Loops.

## Datenfluss (End-to-End)

```
HA-Sensoren/Zonen ─┐
HEMS /api/device_controls_schema ─┤
PV-/Wetter-Sensoren ─┴─► Collector-Loop (alle collect_interval_s) ──► SQLite (Aggregation 1/15/60 min)
                                                                          │
                                                     POST /api/plan/run (manuell ausgelöst!)
                                                                          ▼
                                          Constraints + Objectives + Kontext bauen (Datenminimum)
                                                                          ▼
                                                    KI-Provider (Gemini, strukturierte Ein-/Ausgabe)
                                                                          ▼
                                              Validator (Schema → Grenzen → Zeitlogik, siehe sicherheit-datenschutz.md)
                                                                          ▼
                                        gültiger/geklemmter Plan → SQLite + Audit-Log
                                                                          ▼
                                     sensor.ep_*_vorschlag nach HA schreiben (publish_suggestions)
                                                                          ▼
                     HEMSStatusCollector vergleicht Vorschlag mit HEMS-Ist (unabhängiger Poll-Takt)
                                                                          ▼
                                sensor.ep_plan_status / sensor.ep_hems_verbindung
```

**Wichtig:** Es gibt aktuell **keinen automatischen Planungs-Scheduler**. Ein Plan
entsteht nur durch manuellen Aufruf von `POST /api/plan/run` (Button im Plan-Tab).
`planning_interval_min` wird zwar gelesen, aber **nicht** als Takt: es bestimmt allein die
Plan-Gültigkeitsdauer (`valid_until = now + planning_interval_min`, `planner.py`).
`plan_update_interval_min` nutzt kein Code-Pfad. Details: [bekannte-luecken.md](bekannte-luecken.md#kein-automatischer-scheduler).

## Externer Zugriff im Hinterkopf behalten (D-013/D-023)

Der User will aus dem internen Netz über ein **iOS-Backend (Java auf einem Linux-Server)**
bestimmte Werte **lesen und setzen** — konkretes Beispiel: die Abfahrtszeit des E-Autos für eine
Mindestladung. Das ist noch nicht gebaut, wirkt aber auf jede Architekturentscheidung: der Weg nach
außen muss sauber möglich bleiben.

Vorgesehener Einstieg ist ein **HA Long-Lived Token**, mit dem das fremde Backend direkt
HA-Helfer schreibt (D-023) — EP liest sie ohnehin. Ein eigener EP-Endpunkt kommt erst, wenn das
nicht mehr reicht. Wer eine neue Datenquelle einführt, prüft deshalb: liegt der Wert in einer
HA-Entität, ist er von außen erreichbar; liegt er nur in der SQLite-Datei oder im Prozessspeicher,
ist er es nicht.

## Modulübersicht (`app/energy_pilot/*.py`)

| Modul | Verantwortung |
|---|---|
| `main.py` | Bootstrapping, Zusammenbau aller Komponenten |
| `config.py` | `AddonConfig` — lädt `/data/options.json` über `DEFAULTS` |
| `settings.py` | DB-gestützter Key-Value-Store (editierbarer Prompt, OneCall-Budgetzähler) |
| `database.py` | SQLite-Init + versionierte Migrationen |
| `logging_setup.py` | Strukturiertes JSON-Logging, Secret-Redaktion, Ringpuffer für UI/Export |
| `ha_client.py` | HA-Core-API-Client (lesen mit Allowlist-Guard, schreiben, Service-Calls) |
| `hems_client.py` | HEMS-Addon-Client (`/api/status`, `/api/controls`, `/api/device_controls_schema`) |
| `allowlist.py` | `EntityAllowlist` — weiche Durchsetzung erlaubter Lese-Entitäten (D-038) |
| `roles.py` | Feste Mess-Rollen (PV/Hausverbrauch/Netz/Batterie) |
| `entity_map.py` | Rollen→Entity-ID-Mapping aus `sensoren`-Config |
| `collector.py` | `StateCollector` — liest Mess-Rollen, füttert Aggregation |
| `aggregation.py` | `RollingAggregator` — 1/15/60-min-Mittelwerte (D-003) |
| `devices.py` | Gerätemodell (`Device`/`DeviceExtra`), HEMS-Discovery, Read-Feld-Ableitung |
| `device_collector.py` | Liest `ems_*` + Zusatz-Felder je Gerät (Letztwert, kein Mittel) |
| `device_extras.py` | Persistenz + Anwendung konfigurierbarer Zusatz-Entitäten |
| `device_prompts.py` | Persistenz der Pro-Gerät-KI-Beschreibung (`funktion`) |
| `constraints.py` | Leitet harte Gerätegrenzen aus `ems_*`-Werten ab |
| `control_mode.py` | HEMS-Modus-Achse: löst je Gerät die Steuerquelle `aus`/`user`/`ep` auf, Gate für den Original-Schreibweg (D-057) |
| `objectives.py` | User-definierte Ziele (`ziele`-Tabelle, D-055) + Gewichtung aus der Klassifizierungs-Antwort |
| `forecast.py` / `forecast_collector.py` | PV-Prognose-Modell + Sammlung/Summierung je Ausrichtung |
| `weather.py` / `weather_client.py` / `weather_collector.py` / `onecall_client.py` / `onecall_budget.py` | OpenWeatherMap-Anbindung (zwei Quellen: `forecast3h`/`onecall`) |
| `ai_provider.py` | Abstrakte Provider-Schnittstelle + `AsyncRateLimiter` (Wartedrossel) |
| `gemini_provider.py` | Google-Gemini-REST-Client |
| `claude_provider.py` | Anthropic-Claude-REST-Client (Messages-API, `output_config.format`, D-056) |
| `openai_provider.py` | OpenAI-GPT-REST-Client (Chat-Completions, `response_format`/Strict, D-056) |
| `schema_convert.py` | Übersetzt das Gemini-Antwortschema in Standard-JSON-Schema für Claude/OpenAI (D-056) |
| `plan_context.py` | Baut komprimierten KI-Kontext + Gemini-Response-Schema + Prompt |
| `plan_schema.py` | Versioniertes Plan-JSON-Schema (`jsonschema`), Schreibvertrag je Gerät |
| `validator.py` | Lokale Plan-Validierung (Struktur → Grenzen → Zeitlogik) |
| `planner.py` | `Planner.run()` — orchestriert einen vollständigen Planungslauf |
| `suggestion_publisher.py` | Schreibt `sensor.ep_*_vorschlag` (+ optional Original-Entität, D-052) |
| `plan_feedback.py` | Vergleicht Vorschlag mit HEMS-Ist (beobachtet, nicht bestätigt) |
| `status_publisher.py` | Schreibt `sensor.ep_plan_status` / `sensor.ep_hems_verbindung` |
| `hems_status_collector.py` | Pollt HEMS-Status unabhängig vom Haupt-Poll-Takt |
| `http_errors.py` | Gemeinsame HTTP-Fehlerbehandlung (Secrets nie in URLs/Logs) |
| `conversion.py` | `safe_float()` — robuste HA-State-Konvertierung |
| `web/server.py` | aiohttp-App-Factory, alle HTTP-Endpunkte (siehe [api-referenz.md](api-referenz.md)) |
| `web/static/app.js` | Frontend-SPA (9 Tabs) |
