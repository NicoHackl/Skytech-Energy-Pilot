# 00 — Übersicht & Projektaufteilung

Dieser Ordner zerlegt Skytech Energy Pilot (EP) in handhabbare Themenblöcke. Jede Datei beschreibt Zweck, Verantwortung, Schnittstellen und offene Punkte des jeweiligen Blocks. Vollständige Fachspezifikation: [../info.md](../info.md). Verbindliche Regeln: [../user-regeln.md](../user-regeln.md) (Vorrang vor info.md).

## Leitprinzip
**EP plant strategisch — HEMS regelt in Echtzeit.** EP steuert nie direkt Geräte. Jede reale Leistungsänderung läuft über HEMS. EP ist optionale KI-Erweiterung auf der Pflicht-Basis HEMS.

## Themenblöcke

| Datei | Block | Kern |
|-------|-------|------|
| [01-homeassistant-integration.md](01-homeassistant-integration.md) | HA-Integration | Entitäten, Helfer, Namensschema, Ingress, Konfig |
| [02-backend-architektur.md](02-backend-architektur.md) | Backend | Module, Datenfluss, Scheduler, State Collector |
| [03-api-schnittstelle-hems.md](03-api-schnittstelle-hems.md) | API / HEMS | Versionierte interne API, Planübergabe, Statusrückmeldung |
| [04-ki-provider.md](04-ki-provider.md) | KI | Provider-Interface, Tool-/Function-Calling, OpenAI/Gemini |
| [05-daten-und-speicherung.md](05-daten-und-speicherung.md) | Daten | SQLite-Schema, Aggregation, History, Mittelwertbildung |
| [06-prognosen.md](06-prognosen.md) | Prognosen | PV, Last, Wetter, Strompreis, Prognosefehler |
| [07-planning-engine.md](07-planning-engine.md) | Planung | Kandidatenplan, Simulation, Ziele/Gewichtung |
| [08-validierung-sicherheit.md](08-validierung-sicherheit.md) | Sicherheit | Schema-Validierung, harte Grenzen, Fallback, Audit |
| [09-ui-ingress.md](09-ui-ingress.md) | UI | Dashboard, Plan, Prognosen, Geräte, Ziele, KI-Konfig |
| [10-logging-observability.md](10-logging-observability.md) | Logging | UI-Logs, maschinenlesbarer Export für KI-Analyse |
| [11-tests-ci.md](11-tests-ci.md) | Tests/CI | Unit-, Integrations-, Schema-Tests, GitHub Actions |
| [12-steuermodi.md](12-steuermodi.md) | Steuermodi | Manuell/Hybrid/Automatisch + Betriebsmodi |
| [entscheidungen.md](entscheidungen.md) | Decision Log | alle beantworteten Entscheidungen (D-001…) |
| [roadmap.md](roadmap.md) | Roadmap | Meilensteine M0–M6 |

## Abhängigkeitsreihenfolge (grob)
```
01 HA-Integration ─┐
05 Daten/Storage ──┼─→ 02 Backend ─→ 06 Prognosen ─→ 07 Planung ─→ 04 KI
                   │                                      │
                   └────────────→ 08 Sicherheit ←─────────┘
                                       │
                          03 API/HEMS ─┴─→ 09 UI / 10 Logging
                          (11 Tests/CI durchgängig parallel)
```

## Statusprinzip
- Jeder Block hält eigene „Offene Punkte". Solche, die eine User-Entscheidung brauchen, wandern zusätzlich nach [../claude-fragen/](../claude-fragen/).
- Querschnittsthemen **Tests** und **Logging** sind ab M0 mitzubauen (user-regeln.md).
