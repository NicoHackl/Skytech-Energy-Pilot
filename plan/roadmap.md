# Roadmap — Skytech Energy Pilot

Meilensteine entlang der Entwicklungsphasen aus [../info.md](../info.md) §21 und der Betriebsmodus-Einführung „Beobachten → Vorschlagen → Shadow Mode → Autopilot". Parallel dazu die Steuermodi-Achse Manuell/Hybrid/Automatisch ([12](12-steuermodi.md)). Querschnitt **Tests** und **Logging** laufen ab M0 durchgehend mit (user-regeln.md). Beantwortete Grundsatzentscheidungen: [entscheidungen.md](entscheidungen.md).

Legende: ☐ offen · ◐ in Arbeit · ☑ erledigt

---

## M0 — Fundament & Gerüst ☑ ERLEDIGT (16.06.2026, in HA verifiziert)
**Ziel:** lauffähiges, leeres Addon mit CI, Logging, DB.
- ☑ Addon-Skelett (Dockerfile, config.yaml, Slug `skytech_energy_pilot`, Ingress-Panel).
- ☑ aiohttp-Server + Ingress-SPA (Status/Logs).
- ☑ HA-Connector (REST + WebSocket) via `SUPERVISOR_TOKEN`, Verbindungstest (`/api/ha/test`).
- ☑ SQLite-Init + Migrations-Mechanismus ([05](05-daten-und-speicherung.md)).
- ☑ Strukturiertes JSON-Logging + UI-Logansicht + JSONL-Export ([10](10-logging-observability.md)).
- ☑ CI-Pipeline (Lint, pytest 92 % Coverage, Docker-Build) auf `claude/main` ([11](11-tests-ci.md)).

**Definition of Done:** ✅ Addon installiert, startet in HA, Ingress-Seite erreichbar, strukturierte Logs, lokal alle Tests grün + Docker-Build (auch gegen python:3.14-alpine) erfolgreich.

---

## M1 — Daten & Anzeige *(info.md Phase 1)* ☑ ERLEDIGT (Rest explizit M2)
**Ziel:** EP liest und zeigt Daten, keine Planung, keine HEMS-Übergabe.
- ☑ Konfigurierbare Entitätszuordnung + Fallback (in Addon-Config, D-027; UI zeigt sie lesend).
- ☑ HA-Helfer-YAML-Pakete (`<domain>_ep.yaml`) bereitstellen ([../claude-ha-config-dateien/](../claude-ha-config-dateien/), D-005).
- ☑ Entity Allowlist (D-038): zentrales Register der freigegebenen Lese-Entitäten aus den 3 Config-Quellen, **soft** durchgesetzt (Verstöße protokolliert/auditiert, nie blockiert), Config+DB, Transparenz unter `/api/allowlist` + Status-Tab. Module `allowlist.py`; Soft-Guard in `ha_client.py`.
- ☑ State Collector + History Aggregator inkl. **1/15/60-min-Mittelwerte** (D-001/D-003, [05](05-daten-und-speicherung.md)).
- ☑ **Geräte-Datenebene:** Discovery ausschließlich via HEMS `/api/device_controls_schema` (D-036/D-046: HEMS-only, Auto-Retry 5×30 s + manueller HEMS-Sync-Button); EP liest `ems_*`-Gerätewerte (technische Freigabe, Ist-Leistung, min/max technisch) + Heizstab-Temperaturgrenze (D-035). Module `hems_client.py`, `devices.py`, `device_collector.py`; Endpoint `/api/devices`; Geräte-Ansicht in der SPA.
- ☑ **PV-Prognose-Anbindung** (D-006/D-018/D-026): mehrere Ausrichtungen je in Addon-Config (`pv_forecast`), EP summiert je Wert (akt./nächste Stunde, Rest heute, morgen). Module `forecast.py`, `forecast_collector.py`; Endpoint `/api/forecast`; Prognose-Tab. Strompreis in V1 raus.
- ☑ **Wettervorhersage (OpenWeatherMap, D-042):** 5-Tage/3-Stunden-Prognose direkt im EP abgerufen; Koordinaten aus HA-Zone, Schlüssel/Parameter in Addon-Config (`weather`). Module `weather.py`, `weather_client.py`, `weather_collector.py`; Endpoint `/api/weather`; Wetter-Block im Prognose-Tab. V1: nur EP-intern (keine HA-Sensoren/HEMS, KI-Kontext offen → claude-fragen-v8).
- ☑ Dashboard + Geräte- + Prognoseanzeige (read-only).
- ☐ Status-Entitäten (`sensor.ep_*`) — kommt mit M2 (Vorschlagswerte).

**DoD:** Aktuelle + verdichtete Werte und Prognosen sind in der UI und als Entitäten sichtbar; Mittelwertbildung getestet. ✅ erfüllt (Status-Entitäten bewusst nach M2 verschoben).

---

## M2 — Vorschlagswerte *(info.md Phase 2 · Betriebsmodi „Beobachten"+„Vorschlagen")*
**Ziel:** KI liefert **Vorschlagswerte** (D-008) — sichtbar in UI/Sensoren/Logs, **keine Übernahme**.
- ☑ Device/Constraint-Model + User-Objective-Manager (harte Grenzen aus `ems_*`; Gewichte in Addon-Config `objective_weights`, init aus info.md §7 — D-011) ([07](07-planning-engine.md)). Module `constraints.py`/`objectives.py`; Transparenz `GET /api/constraints` + `/api/objectives`, Tab „Grenzen & Ziele". (D-040)
- ☑ KI-Provider-Interface; **Start Gemini** (Free, Rate-Limit-Drossel ~10/min), Provider/Modell in Addon-Config umschaltbar (D-007/D-041). REST/aiohttp (kein SDK), Single-Shot + `responseSchema`. Module `ai_provider.py`/`gemini_provider.py` ([04](04-ki-provider.md)).
- ☑ Planning Engine: Kandidatenplan (Erststufe: Batterie + Heizstab + Heizlüfter 1/2). Manuell ausgelöst via `POST /api/plan/run`; verdichteter Kontext (Datenminimum) → KI → lokaler Validator → DB. Module `plan_context.py`/`planner.py` (D-041).
- ☑ **Wetter im KI-Kontext + editierbarer Prompt (D-043):** Wetterprognose fließt in die Planung (Detailgrad `weather.llm_detail` `compact`/`full` in der Addon-Config). Planungs-Prompt in der EP-Oberfläche editierbar (`GET/POST /api/prompt`, persistiert in der `config`-Tabelle, kein Git-Push/Update nötig); Datenblock/Antwort-Schema/Validator bleiben fest. Modul `settings.py`.
- ☑ Plan-JSON-Schema (`schema_version`) + lokaler Validator ([08](08-validierung-sicherheit.md)). Module `plan_schema.py`/`validator.py` (Stufen 1–3: Schema, harte Grenzen klemmen/ablehnen, Zeitlogik; Stufen 4–6 später). `jsonschema`-Lib (D-039/D-040).
- ☑ **Vorschlagssensoren (Suffix `vorschlag`):** EP schreibt validierte Vorschlagswerte als `sensor.ep_<gerät>_<feld>_vorschlag` nach HA (V1-Schreibweg, reine Anzeige; **keine** HEMS-Übergabe → M3). Auslöser **auto + manuell**: Auto-Publish bei jedem gültigen Plan (Schalter `publish_suggestions`, Default an) + Button „Erneut nach HA schreiben"/`POST /api/plan/publish`. Module `suggestion_publisher.py`, `HAClient.set_state`; Audit `suggestions_published`.
- ◐ UI: Energieplan-Ansicht, Begründungen, KI-Konfig (Key, Limits, Testverbindung), Kosten-/API-Logging. „Plan"-Tab + Begründungen + geschriebene Sensoren + `GET /api/ai/test` + `ai_calls`-Logging vorhanden (D-041); KI-Konfig läuft über die Addon-Config, **automatische periodische Planung (Scheduler) → M4**.

**DoD:** EP erzeugt validen, begründeten Plan als Vorschlagswerte; sichtbar in UI/Sensoren/Logs; kein automatischer Eingriff. ✅ erfüllt (Auto-Scheduler bewusst nach M4).

---

## M3 — HEMS-Schnittstelle *(info.md Phase 3)*
**Ziel:** bestätigte Pläne gehen an HEMS, mit Statusrückmeldung und Fallback.
- ☐ **Ebene 1 (D-002):** Plan-Submission an HEMS über HA-Helfer/`/api/set` (HEMS unverändert).
- ☐ **Ebene 2 (D-002):** versionierter Plan-Endpunkt im **HEMS-Repo** + interne API ([03](03-api-schnittstelle-hems.md)).
- ☐ Steuermodi Manuell/Hybrid/Automatisch wirksam ([12](12-steuermodi.md), D-009); Hybrid-Fixierungen als harte Vorgaben ([08](08-validierung-sicherheit.md)).
- ☐ Externer Schreibzugriff (iOS/Java-Backend) über HA-Helfer vorbereiten (D-013).
- ◐ **Annahme/Ablehnung + Ausführungsstatus zurücklesen + in UI/Entitäten spiegeln.** *(Durchstich 1, v0.0.23):* EP pollt HEMS `/api/status`, leitet eine **beobachtete** Plan-Übereinstimmung ab (`plan_feedback.py`), spiegelt sie als `sensor.ep_plan_status`/`sensor.ep_hems_verbindung` + HEMS-Tab. Read-only, HEMS unverändert. Echte Accept/Reject (statt „beobachtet") kommt mit Ebene 2/B4.
- ☐ Planablauf + Fallback-Logik, HEMS-Doppelvalidierung.
- ☐ Delta-Limit zwischen Plänen.

**DoD:** Bestätigter Plan wird von HEMS angenommen/ausgeführt; Ablauf/Fallback nachweislich sicher.

---

## M4 — Shadow Mode *(info.md Phase 4)*
**Ziel:** automatische Planung + Simulation ohne Ausführung, Kennzahlen.
- ☐ Automatische periodische + ereignisbasierte Planung (Scheduler/Eventbus).
- ☐ Simulation Engine + Bewertung mehrerer Varianten.
- ☐ Monitoring/Feedback: Plan vs. Realität, Prognosefehler, Kennzahlen (info.md §22).
- ☐ Prognose-Optimierung aus gemessenen Fehlern.

**DoD:** EP plant autonom, vergleicht über Wochen Plan↔Realität; Kennzahlen in der UI; nichts wird ausgeführt.

---

## M5 — Autopilot *(info.md Phase 5)*
**Ziel:** validierte Pläne automatisch übernehmen, abgesichert.
- ☐ Auto-Submit gültiger Pläne mit konfigurierbarer Mindestkonfidenz.
- ☐ Vollständige ereignisbasierte Neuberechnung.
- ☐ Benachrichtigungen (HA) + umfassendes Audit-Log.
- ☐ Not-Aus / manueller Modus jederzeit.

**DoD:** Autopilot läuft sicher; Sicherheitsstufen + Audit vollständig; jederzeit abschaltbar.

---

## M6 — Lokale Optimierungsengine *(info.md Phase 6)*
**Ziel:** deterministische mathematische Fahrplanoptimierung; KI orchestriert/erklärt.
- ☐ Optimierungsmodell (Speicherverluste, Kosten/Eigenverbrauch, rollierende Planung).
- ☐ KI ruft Engine via `calculate_candidate_plan`, bewertet/erklärt Ergebnisse.
- ☐ Erweiterung Geräte: Wallbox/E-Auto, Wärmepumpe, dynamische Tarife/Netzladung, mehrere Speicher.

**DoD:** Engine liefert nachweislich bessere Kennzahlen als die reine KI-/reaktive Strategie.

---

## Querschnitt (durchgehend ab M0)
- **Tests/CI** ([11](11-tests-ci.md)) — jedes Feature mit Tests, CI grün auf `claude/main`; **HEMS↔EP-Zusammenspiel** ist Pflicht-Testfall (D-015).
- **Logging/Observability** ([10](10-logging-observability.md)) — UI-einsehbar + maschinenlesbarer Export.
- **Sicherheit** ([08](08-validierung-sicherheit.md)) — harte Grenzen, Validierung, Fallback in jeder Stufe aktiv.

## Abhängigkeiten / Reihenfolge
```
M0 → M1 → M2 → M3 → M4 → M5 → M6
                 (M3 setzt Abstimmung HEMS-Repo voraus, siehe claude-fragen)
```
