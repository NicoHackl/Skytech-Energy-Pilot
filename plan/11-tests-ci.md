# 11 — Tests & CI

> Verbindliche Vorgabe aus [../user-regeln.md](../user-regeln.md): von Anfang an umfangreiche und sinnvolle automatische CI-Tests.

## Grundsätze
- Tests wachsen mit jedem Modul mit (ab M0). Kein Modul gilt als fertig ohne Tests.
- Schnell, deterministisch, ohne echte HA-/Cloud-Abhängigkeit (Mocks/Fakes).
- Englische Test-Identifier, deutsche Kommentare (user-regeln.md §02).

## Testarten
- **Unit:** State Collector/Aggregator (Mittelwertfenster!), Constraint-Model, Objective-Manager, Validator, Provider-Adapter (gemockt).
- **Schema:** Plan-JSON gegen versioniertes Schema (gültige + bewusst ungültige Pläne). Sicherstellen, dass harte Grenzen Verletzungen abfangen.
- **Integration:** Planungs-Pipeline end-to-end mit gefakten HA-States, Prognosen und gemocktem KI-Provider → erwartet validen Plan oder saubere Ablehnung.
- **HEMS-Schnittstelle:** Vertragstests gegen das API-Schema (siehe [03](03-api-schnittstelle-hems.md)); Mock-HEMS für Annahme/Ablehnung/Status.
- **Sicherheits-/Regressionstests:** kein API-Key in Logs (Redaction), abgelaufene Pläne werden nie weiterverwendet, Delta-Limit greift, Fallback-Verhalten.

## Schwerpunkt-Testfälle (aus Spezifikation abgeleitet)
- Live-Wert → korrekter gleitender Mittelwert über konfiguriertes Fenster; SOC/Temperatur werden **nicht** gemittelt.
- Plan mit SOC über hartem Maximum → abgelehnt.
- Veraltete Messwerte → Plan abgelehnt, Warnung.
- KI-Ausfall/Timeout → Backend stabil, HEMS unbeeinflusst, lokaler/passiver Modus.
- Kostenlimit erreicht → Wechsel in passiven Modus.

## HEMS↔EP-Zusammenspiel zwingend testen (D-015)
- **Pflicht:** CI testet das Zusammenspiel HEMS↔EP. Da HEMS aktuell über HA-Helfer/`/api/set` angebunden ist (D-002), erfolgt das über **Vertragstests gegen ein Mock-HEMS** + Mock-HA-Helfer: EP schreibt Vorschlagswerte → Mock prüft Format/Wertebereiche → Annahme/Ablehnung/Status zurück.
- Sobald die versionierte Plan-API im HEMS-Repo existiert, wird der Vertrag gegen das gemeinsame JSON-Schema getestet (beide Repos).

## CI (GitHub Actions) — D-024
- **Trigger: nur Push/PR auf `claude/main`** (automatische Tests laufen ausschließlich für diesen Branch).
- Schritte: Lint (z.B. ruff) + Typecheck (mypy, optional) → `pytest` mit Coverage → Build des Addon-Docker-Image.
- **Coverage-Qualitätsgate: Start 60 %**, später anheben.
- Optional: JSON-Schema-Lint, Docker-Build-Smoke-Test.

## Offene Punkte
- — (Coverage-Start 60 % und Branch-Beschränkung auf `claude/main` sind festgelegt, D-024.)
