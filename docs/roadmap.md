# Roadmap — Meilensteine M0–M6

Reihenfolge aus der alten Doku (`plan/roadmap.md`), Status hier gegen den
**tatsächlichen Code** geprüft statt gegen die ursprüngliche Planung. ☑ fertig,
◐ teilweise, ☐ offen.

## M0 — Fundament & Gerüst — ☑ fertig

Addon-Grundgerüst, aiohttp+Ingress-SPA, HA-Connector (REST+WS) über
`SUPERVISOR_TOKEN`, SQLite-Init+Migrationen, strukturiertes JSON-Logging + UI-
Logansicht + JSONL-Export, CI (Lint, Pytest, Docker-Build) auf `claude/stage`
(D-053, umbenannt von `claude/main`).

## M1 — Daten & Anzeige — ☑ fertig

Konfigurierbares Entity-Mapping, HA-Helfer-YAML-Pakete, Entity-Allowlist (weich),
State-Collector + History-Aggregator (1/15/60-min), Geräte-Discovery ausschließlich
über HEMS (Auto-Retry + manueller Sync), PV-Prognose-Integration, OpenWeatherMap-
Wetter, read-only Dashboard/Geräte-/Prognose-Ansichten.

## M2 — Vorschlagswerte — ◐ größtenteils fertig, ein wichtiger Punkt offen

Geräte-/Constraint-Modell + Objective-Manager, Gemini-Provider-Integration,
Planungs-Engine, wetterhaltiger Kontext + editierbarer Prompt, Plan-JSON-Schema +
Validator (Stufen 1–4 und 6), Vorschlags-Sensoren automatisch bei jedem gültigen Plan
publiziert + manueller "Erneut nach HA schreiben"-Button. Seit 0.0.61 zusätzlich
Freitext-Regeln je Gerät mit Begründungspflicht, Temperatur-Mess-Rollen,
Wetter-Kennzahlen, Kontext-Quantisierung mit Plan-Wiederverwendung und ein
Konfidenz-Gate (D-060 – D-064). Seit 0.0.63 zusätzlich der Tages-Rückblick aus der
HA-Historie und die gerechneten Geräte-/Systemmerkmale (D-065/D-066) — damit ist die nie
gebaute Hälfte von `plan/longterm_plan.md` §3.2/§3.3 (dort B1/B5) umgesetzt.

**Offen:** automatische periodische Planung (Scheduler) — siehe
[bekannte-luecken.md](bekannte-luecken.md#kein-automatischer-scheduler).
Validator-Stufe 5 (Delta-Limit zum Vorplan) bleibt **bewusst** offen: nachgelagerte
Dämpfung der KI-Ausgabe ist als Ansatz verworfen (D-060).

## M3 — HEMS-Schnittstelle — ◐ nur ein Teilstück ("Durchstich 1")

**Fertig:** EP pollt HEMS `/api/status`, leitet eine **beobachtete**
Plan-Konformität ab (`plan_feedback.py`), spiegelt sie als
`sensor.ep_plan_status`/`sensor.ep_hems_verbindung` + HEMS-Tab. Read-only, HEMS
selbst unverändert.

**Offen:** Ebene 1 (HA-Helfer/`/api/set`-Übergabeweg, der tatsächlich etwas
bewirkt) und Ebene 2 (versionierter Plan-Endpunkt im HEMS-Repo) sind **nicht**
gebaut — Vorschläge landen zwar als Sensoren in HA, aber nichts wertet sie
automatisch aus. Steuermodi Manuell/Hybrid/Automatisch nicht wirksam
([steuermodi.md](steuermodi.md)). Externer Schreibzugriff (iOS/Java-Backend)
nicht umgesetzt. Plan-Ablauf+Fallback-Logik, HEMS-Doppelvalidierung, Delta-Limit
zwischen Plänen — alles offen.

## M4 — Shadow Mode — ☐ offen

Automatische periodische+ereignisbasierte Planung (Scheduler/Eventbus),
Simulations-Engine + Mehrvarianten-Bewertung, Monitoring/Feedback (Plan vs.
Realität, Prognosefehler, KPIs), Prognose-Optimierung aus gemessenen Fehlern.

## M5 — Autopilot — ☐ offen

Automatisches Absenden gültiger Pläne mit konfigurierbarer Mindestkonfidenz, volle
ereignisbasierte Neuberechnung, HA-Benachrichtigungen + umfassendes Audit-Log,
Notfall-Stopp/manueller Modus immer verfügbar.

## M6 — Lokale Optimierungsengine — ☐ offen

Deterministische mathematische Fahrplan-Optimierung (Speicherverluste, Kosten/
Eigenverbrauch, rollierende Planung), KI ruft die Engine auf und orchestriert/
erklärt die Ergebnisse, Geräte-Erweiterung (Wallbox/E-Auto, Wärmepumpe, dynamische
Tarife/Netzladen, mehrere Speicher).

## Querschnitt (durchgehend seit M0)

Tests/CI (jedes Feature getestet, CI grün auf `claude/stage`, HEMS↔EP-Zusammenspiel
laut D-015 verpflichtend — **aktuell keine dedizierte Contract-Test-Suite gegen ein
Mock-HEMS gefunden**, prüfen bevor man das als erledigt annimmt), Logging/
Observability (UI-sichtbar + maschinenlesbarer Export), Sicherheit (harte Grenzen/
Validierung/Fallback in jeder Stufe aktiv).

## Später/Zukunft (explizit außerhalb Phase 1)

Wallbox + E-Auto-Laden, Wärmepumpe, weitere flexible Verbraucher, dynamische
Stromtarife + Netzladen, mehrere Speichereinheiten, weitere Erzeugungsanlagen.
