# 10 — Logging & Observability

> Verbindliche Vorgabe aus [../user-regeln.md](../user-regeln.md): von Anfang an umfangreiches, übersichtliches, aus der EP-UI einsehbares Logging — **plus** maschinenlesbarer Export für KI-Analyse.

## Ziele
1. **UI-einsehbar:** Logs direkt in der EP-Oberfläche durchsuch-/filterbar (Zeit, Level, Komponente).
2. **Maschinenlesbar exportierbar:** Format, das eine KI/LLM (ChatGPT/Claude) analysieren kann, um Fehler zu finden und zu beheben.

## Log-Struktur
- **Strukturiertes JSON-Logging** (eine Zeile = ein Event, JSONL) mit Feldern:
  ```
  ts, level, component, event, message, plan_id?, provider?, model?,
  duration_ms?, error?, context{...}
  ```
- Konsistente `component`-Namen entlang der Module aus [02](02-backend-architektur.md).
- Korrelations-IDs: `plan_id`, optionale `run_id` je Planungslauf — macht einen kompletten Planungszyklus nachverfolgbar.

## Speicherung
- Laufende Logs in Datei (JSONL, rotierend) + sicherheitsrelevante Ereignisse zusätzlich in `audit`/`errors` (siehe [05](05-daten-und-speicherung.md)).
- **Kein API-Key, keine Secrets** in Logs (info.md §13). Redaction-Filter zwingend.
- Datenminimum: keine personenbezogenen HA-Inhalte unnötig loggen.

## Export für KI-Analyse
- UI-Button „Logs exportieren" → JSONL/JSON-Bundle (Zeitraum + Level wählbar).
- Bundle enthält optional: relevante Plan-Payloads, Prognose-Snapshots, Prognose-vs-Realität, API-Call-Statistik — so kann eine KI Ursache→Wirkung rekonstruieren.
- Self-contained und ohne Secrets, damit es direkt an ein externes LLM gegeben werden kann.

## Auto-Export bei Fehlern (D-014)
- Bei `ERROR`/`CRITICAL` wird **automatisch** ein KI-lesbares Log-Bundle erzeugt und der User benachrichtigt (HA-Notification), um die gemeinsame Fehlerbehandlung mit der KI zu erleichtern.
- Bundle wieder ohne Secrets; Inhalt = Fehlerkontext + zugehöriger `run_id`/`plan_id`.

## Levels
`DEBUG` (Diagnose, abschaltbar), `INFO` (normaler Ablauf), `WARNING` (Prognoselücke, niedrige Konfidenz, Limit nahe), `ERROR` (KI-Ausfall, Validierung fehlgeschlagen), `CRITICAL` (Sicherheits-/Submit-Probleme).

## UI-Integration (siehe [09](09-ui-ingress.md))
- Live-Tail, Filter nach Level/Komponente/Zeit, Suche, Export.
- Verknüpfung Plan ↔ zugehörige Logzeilen über `plan_id`/`run_id`.

## Offene Punkte
- Rotationsgröße/Aufbewahrung der Logdateien im Container.
