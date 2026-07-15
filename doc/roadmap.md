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
Validator (Stufen 1–3), Vorschlags-Sensoren automatisch bei jedem gültigen Plan
publiziert + manueller "Erneut nach HA schreiben"-Button.

**Offen:** automatische periodische Planung (Scheduler) — siehe
[known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md#kein-automatischer-scheduler).
Validator-Stufen 4–6 (Frische/Delta-Limit/Mindestkonfidenz) ebenfalls offen.

## M3 — HEMS-Schnittstelle — ◐ nur ein Teilstück ("Durchstich 1")

**Fertig:** EP pollt HEMS `/api/status`, leitet eine **beobachtete**
Plan-Konformität ab (`plan_feedback.py`), spiegelt sie als
`sensor.ep_plan_status`/`sensor.ep_hems_verbindung` + HEMS-Tab. Read-only, HEMS
selbst unverändert.

**Offen:** Ebene 1 (HA-Helfer/`/api/set`-Übergabeweg, der tatsächlich etwas
bewirkt) und Ebene 2 (versionierter Plan-Endpunkt im HEMS-Repo) sind **nicht**
gebaut — Vorschläge landen zwar als Sensoren in HA, aber nichts wertet sie
automatisch aus. Steuermodi Manuell/Hybrid/Automatisch nicht wirksam
([control-modes.md](control-modes.md)). Externer Schreibzugriff (iOS/Java-Backend)
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
