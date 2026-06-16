# Roadmap — Skytech Energy Pilot

Meilensteine entlang der Entwicklungsphasen aus [../info.md](../info.md) §21 und der Betriebsmodus-Einführung „Beobachten → Vorschlagen → Shadow Mode → Autopilot". Parallel dazu die Steuermodi-Achse Manuell/Hybrid/Automatisch ([12](12-steuermodi.md)). Querschnitt **Tests** und **Logging** laufen ab M0 durchgehend mit (user-regeln.md). Beantwortete Grundsatzentscheidungen: [entscheidungen.md](entscheidungen.md).

Legende: ☐ offen · ◐ in Arbeit · ☑ erledigt

---

## M0 — Fundament & Gerüst
**Ziel:** lauffähiges, leeres Addon mit CI, Logging, DB.
- ☐ Addon-Skelett (Dockerfile, config.yaml, Slug `skytech_energy_pilot`, Ingress-Panel).
- ☐ aiohttp-Server + leere Ingress-SPA.
- ☐ HA-Connector (REST + WebSocket) via `SUPERVISOR_TOKEN`, Verbindungstest.
- ☐ SQLite-Init + Migrations-Mechanismus ([05](05-daten-und-speicherung.md)).
- ☐ Strukturiertes JSON-Logging + UI-Logansicht + Export-Stub ([10](10-logging-observability.md)).
- ☐ CI-Pipeline (Lint, pytest, Docker-Build) auf `claude/main` ([11](11-tests-ci.md)).

**Definition of Done:** Addon startet in HA, zeigt Ingress-Seite, schreibt strukturierte Logs, CI grün.

---

## M1 — Daten & Anzeige *(info.md Phase 1)*
**Ziel:** EP liest und zeigt Daten, keine Planung, keine HEMS-Übergabe.
- ☐ Konfigurierbare Entitätszuordnung + Fallback in der UI ([01](01-homeassistant-integration.md)).
- ☐ HA-Helfer-YAML-Pakete (`<domain>_ep.yaml`) bereitstellen ([../claude-ha-config-dateien/](../claude-ha-config-dateien/), D-005).
- ☐ Entity Allowlist.
- ☐ State Collector + History Aggregator inkl. **1/15/60-min-Mittelwerte** (D-001/D-003, [05](05-daten-und-speicherung.md)).
- ☐ Fremddaten-Anbindung (Strompreis/PV) über in Addon-Config gepflegte HA-Sensoren (D-006).
- ☐ Dashboard + Geräte- + Prognoseanzeige (read-only).
- ☐ Status-Entitäten (`sensor.ep_*`).

**DoD:** Aktuelle + verdichtete Werte und Prognosen sind in der UI und als Entitäten sichtbar; Mittelwertbildung getestet.

---

## M2 — Vorschlagswerte *(info.md Phase 2 · Betriebsmodi „Beobachten"+„Vorschlagen")*
**Ziel:** KI liefert **Vorschlagswerte** (D-008) — sichtbar in UI/Sensoren/Logs, **keine Übernahme**.
- ☐ Device/Constraint-Model + User-Objective-Manager (harte Grenzen; Gewichte in Addon-Config, init aus info.md §7 — D-011) ([07](07-planning-engine.md)).
- ☐ KI-Provider-Interface; **Start Gemini** (Free, Rate-Limit-Drossel ~10/min), Provider/Modell in Addon-Config umschaltbar (D-007) ([04](04-ki-provider.md)).
- ☐ Planning Engine: Kandidatenplan (Erststufe: Batterie + Heizstab + Heizlüfter 1/2).
- ☐ Plan-JSON-Schema (`schema_version`) + lokaler Validator ([08](08-validierung-sicherheit.md)).
- ☐ Vorschlagssensoren (Suffix `vorschlag`) + Planexport.
- ☐ UI: Energieplan-Ansicht, Begründungen, KI-Konfig (Key, Limits, Testverbindung), Kosten-/API-Logging.

**DoD:** EP erzeugt validen, begründeten Plan als Vorschlagswerte; sichtbar in UI/Sensoren/Logs; kein automatischer Eingriff.

---

## M3 — HEMS-Schnittstelle *(info.md Phase 3)*
**Ziel:** bestätigte Pläne gehen an HEMS, mit Statusrückmeldung und Fallback.
- ☐ **Ebene 1 (D-002):** Plan-Submission an HEMS über HA-Helfer/`/api/set` (HEMS unverändert).
- ☐ **Ebene 2 (D-002):** versionierter Plan-Endpunkt im **HEMS-Repo** + interne API ([03](03-api-schnittstelle-hems.md)).
- ☐ Steuermodi Manuell/Hybrid/Automatisch wirksam ([12](12-steuermodi.md), D-009); Hybrid-Fixierungen als harte Vorgaben ([08](08-validierung-sicherheit.md)).
- ☐ Externer Schreibzugriff (iOS/Java-Backend) über HA-Helfer vorbereiten (D-013).
- ☐ Annahme/Ablehnung + Ausführungsstatus zurücklesen + in UI/Entitäten spiegeln.
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
