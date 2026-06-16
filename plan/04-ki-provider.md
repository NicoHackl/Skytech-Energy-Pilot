# 04 — KI-Provider & Tool-Schnittstelle

## Zweck
Austauschbares Provider-Interface für externe KI-Dienste. Die KI ist **Orchestrator/Energie-Manager**, nicht der mathematische Regler (info.md §12).

## Provider (V1) — Start mit Gemini (D-007, D-025)
- **Start: Google Gemini**, Default-Modell **`gemini-3.5-flash`** (vorhandener **Gratis-Key**, ~**10 Anfragen/min**).
- **OpenAI** (GPT, Function Calling + Structured Outputs) als zweiter Provider, austauschbar.
- **Provider + Modell in der Addon-Config umschaltbar** (zukunftssicher).
- Später: Ollama (lokal), OpenAI-kompatible APIs, vollständig lokale Planung ohne LLM.

> **Rate-Limit beachten:** Bei Gemini-Free ~10 req/min → Aufruf-Drossel/Queue + Budget-Logik, damit Planungs- und Event-Trigger das Limit nicht reißen. Bei Limit → Wartedrossel statt Fehlerflut.

> Hinweis: Für die KI-Anbindung gibt es eine projekteigene, **eng begrenzte** Tool-Schnittstelle (bewusst nicht die generische HA-LLM-API, info.md §24).

## Provider-Interface (abstrakt)
Einheitliche Schnittstelle, damit Provider austauschbar sind:
```
AIProvider.plan(context, tools, objectives) -> CandidatePlan
```
- Strukturierte Ein- und Ausgaben (JSON-Schema). **Freitext nie als Steuerbefehl.**
- Modell stellt nur strukturierte Funktionsaufrufe; EP prüft und führt aus.
- Modell bekommt **keinen** direkten Zugriff auf Geräte oder interne APIs.

## Tools des KI-Agenten (info.md §5)
```
get_current_energy_state()
get_recent_energy_history()
get_energy_forecast()
get_device_constraints()
get_user_objectives()
get_current_plan()
calculate_candidate_plan()   # ruft lokale Optimierungslogik
simulate_candidate_plan()
validate_candidate_plan()
submit_energy_plan()
explain_energy_plan()
```
- Tools liefern nur verdichtete, freigegebene Daten (Datenminimum).
- `submit_energy_plan` triggert NICHT direkt HEMS, sondern den EP-internen Pfad (Validierung → ggf. User-Bestätigung → Submission).

## Geeignete KI-Aufgaben
Ziele interpretieren, Zielkonflikte bewerten, Daten/Werkzeuge wählen, Planvarianten vergleichen, auf Ausnahmen reagieren, strukturierten Plan erzeugen, Entscheidungen begründen, fehlende/widersprüchliche Daten erkennen, lokale Optimierungsengine aufrufen, Simulationsergebnisse interpretieren.

## Nicht erlaubt
Direkte Gerätesteuerung, sekundenschnelle Regelung, Umgehung technischer Grenzen, Erzeugung/Ausführung freien Codes, Änderung von Sicherheitsparametern, unkontrollierter Zugriff auf alle HA-Entitäten, Ersatz für lokale Schutz-/Fallback-Logik.

## Sicherheit & Kosten (info.md §13, §19)
- API-Schlüssel nur in Addon-Config/Secret-Speicher, **nie** in Logs/Plänen/Entitäten.
- Pro Anfrage protokollieren: Anbieter, Modell, Zeitpunkt, geschätzter Verbrauch/Kosten.
- Konfigurierbare Tages-/Monatslimits; bei Limit → lokaler/passiver Modus.
- Timeout, max. API-Aufrufe, Kostenlimit, Datenfreigabe, Testverbindung in der UI (siehe [09](09-ui-ingress.md)).
- User kann einsehen, welche Daten an den KI-Anbieter gingen.

## Offene Punkte
- Prompt-/Tool-Schema-Versionierung.

> Geklärt (D-025): Default `gemini-3.5-flash`, in Addon-Config änderbar. Exakte Modell-ID bei Implementierung gegen aktuelle Gemini-API prüfen.

> Geklärt: V1 = KI erzeugt Plan direkt (Vorschlagswerte, D-008); lokale Optimierungsengine erst später (Phase 6).
