# 03 — API-Schnittstelle & HEMS-Anbindung

## Zweck
Definiert den **versionierten** Vertrag zwischen EP und HEMS. Der Vertrag ist als versioniertes Datenschema unabhängig von einzelnen HA-Helfern (info.md §10).

## Grundprinzip
- EP erstellt Kandidatenplan → lokaler Validator → optionale Simulation → Übergabe an HEMS → HEMS prüft erneut → übernimmt nur erlaubte Parameter → meldet Annahme/Ablehnung/Status zurück.
- Wichtige Zustände zusätzlich als HA-Entitäten sichtbar (Vorschlagssensoren, siehe [01](01-homeassistant-integration.md)).
- HEMS ist Basis und letzte Instanz: **HEMS validiert jeden Plan ein zweites Mal**, harte Grenzen gelten lokal.

## EP-seitige Endpunkte (info.md §10)
```
POST /api/v1/strategy-plans               # neuen Plan einreichen
GET  /api/v1/strategy-plans/current       # aktuell gültigen Plan abrufen
GET  /api/v1/strategy-plans/{plan_id}     # bestimmten Plan abrufen
GET  /api/v1/system-state                 # aktueller Systemzustand (EP-Sicht)
GET  /api/v1/device-constraints           # bekannte Gerätegrenzen
POST /api/v1/strategy-plans/{plan_id}/cancel
```

## Vorhandene HEMS-Endpunkte (zur Integration nutzbar)
HEMS bietet bereits:
```
GET  /api/status                  # letzter Regelzyklus (pool, deficit, Gerätezustände, error)
GET  /api/controls                # alle ems_* Helfer
GET  /api/device_controls_schema  # dynamisches Schema aus Gerätekonfig
POST /api/set                     # {entity_id, value} setzen
```
Plus optionales **post-cycle-script** (HEMS triggert nach jedem Zyklus ein HA-Script).

## Integrationsstrategie (zwei Ebenen)
1. **Indirekt über HA-Helfer (Phase 3 Minimal):** EP schreibt Vorschlagswerte in `ems_*`/`ep_*`-Helfer bzw. via HEMS `/api/set`. Robust, da HEMS-nativ. Gut für ersten Durchstich.
2. **Direkt über versionierte Plan-API (Zielbild):** HEMS erhält einen `/api/v1/strategy-plans`-Endpunkt zur Aufnahme kompletter Pläne. Sauberer Vertrag, atomare Planübernahme, Statusrückmeldung.

> **Entschieden (D-002):** V1 = **Ebene 1** (nur HA-Helfer/`/api/set`, HEMS unverändert). **Danach** Ebene 2: versionierter Plan-Endpunkt **im SkytechHEMS-Repo**. Ich darf dann auch dort committen; der User richtet paralleles lokales Arbeiten in beiden Repos ein. Branch-Regel `claude/main` gilt sinngemäß auch im HEMS-Repo (in v2 final zu bestätigen).

## Planschema (versioniert)
- `schema_version` Pflichtfeld (Beispiel `"1.0"`, info.md §9).
- Inhalte: Metadaten (plan_id, created_at, valid_from, valid_until, strategy, confidence), `battery {...}`, `devices {...}`, `reasoning_summary[]`, Warnungen, erwartete Auswirkungen, Provider/Modell.
- Vollständiges Beispiel: [../info.md](../info.md) §9.
- Jeder Plan hat **Ablaufzeit**; abgelaufener Plan wird nie stillschweigend unbegrenzt weiterverwendet.

## Rückmeldung & Status
- HEMS meldet: Annahme / Ablehnung (mit Grund) / aktueller Ausführungsstatus.
- EP protokolliert beides im Audit-Log und spiegelt es in Status-Entitäten + UI.

## Externer Schreibzugriff vorbereiten (D-013)
Der User will aus dem internen Netz über ein **iOS-Backend (Java auf Linux-Server)** bestimmte Werte **setzen** (z.B. **E-Auto-Abfahrtszeit** für Mindestladung).
- **Bevorzugter Weg (V1):** Das externe Backend schreibt direkt in **HA-Helfer** (z.B. `input_datetime.ep_eauto_abfahrtszeit`); EP liest sie wie jede andere Eingabe. Kein zusätzlicher EP-Endpunkt nötig, nutzt HA-Auth.
- **Später:** optional ein authentifizierter EP-API-Schreibendpunkt. Architektur jetzt schon so halten, dass das nachrüstbar ist.

## Auth EP↔HEMS (D-013)
- Für HA-Addons übliche/beste Variante: interner Supervisor-Proxy + `SUPERVISOR_TOKEN`, interner Hostname im Addon-Netz.

## Spätere Option
- MQTT-Adapter als zusätzlicher Transport. Primärvertrag bleibt das versionierte JSON-Schema.

## Offene Punkte
- Konkrete Auth des **externen** iOS/Java-Backends gegenüber HA (Long-Lived Token?) → claude-fragen.
- Mapping EP-Planfelder ↔ konkrete HEMS-Helfer (`ems_<prefix>_*`).
