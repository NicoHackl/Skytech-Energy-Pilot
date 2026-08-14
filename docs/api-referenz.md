# API-Referenz

## EP-HTTP-Endpunkte (`web/server.py`)

Alle State liegt auf `app[...]`-Keys (Config/DB/Ring-Puffer/Clients/Collector/Planner).

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Oberfläche (`frontend/dist/index.html`) |
| GET | `/assets/*` | Gebautes React-Bündel (JS/CSS) |
| GET | `/api/health` | Status/Version/Provider/Modell/`ha_configured` |
| GET | `/api/logs` | Ringpuffer, filterbar nach `level`/`limit` |
| GET | `/api/logs/export` | JSONL-Export (maschinenlesbar, Download) |
| GET | `/api/ha/test` | HA-Verbindungstest |
| GET | `/api/state` | aktueller Mess-Snapshot (Rollen) |
| GET | `/api/entities` | Rollen→Entity-Mapping (read-only Anzeige) |
| GET | `/api/devices` | entdeckte Geräte + `ems_*`-Werte + Zusatz-Entitäten |
| POST | `/api/devices/extras` | Zusatz-Entität anlegen/ändern |
| DELETE | `/api/devices/extras` | Zusatz-Entität löschen |
| POST | `/api/devices/prompt` | Pro-Gerät-KI-Beschreibung setzen/löschen |
| GET | `/api/forecast` | PV-Prognose-Snapshot |
| GET | `/api/weather` | Wetter-Snapshot (je nach Quelle) |
| GET | `/api/weather/test` | Live-Wetterabruf-Test |
| GET | `/api/hems/status` | HEMS-Status + Plan-Feedback (`?refresh=1` erzwingt Live-Poll) |
| GET | `/api/hems/test` | Live-HEMS-Statustest |
| POST | `/api/hems/rediscover` | manueller HEMS-Geräte-Re-Sync |
| GET | `/api/allowlist` | Allowlist-Register-Snapshot |
| GET | `/api/constraints` | abgeleitete harte Grenzen + Schreibvertrag je Gerät |
| GET | `/api/ziele` | user-definierte Ziele (D-055, ohne Gewicht) |
| POST | `/api/ziele` | Ziel anlegen/ändern (`{id?, name, beschreibung?, devices?}`) |
| DELETE | `/api/ziele` | Ziel löschen (`{id}`) |
| GET | `/api/plan/schema` | versioniertes Plan-JSON-Schema |
| GET | `/api/prompt` | aktueller/Default-Planungs-Prompt |
| POST | `/api/prompt` | Planungs-Prompt speichern/zurücksetzen |
| GET | `/api/classification-prompt` | aktueller/Default-Klassifizierungs-Prompt (D-055) |
| POST | `/api/classification-prompt` | Klassifizierungs-Prompt speichern/zurücksetzen |
| POST | `/api/classification/run` | Klassifizierungs-Aufruf isoliert auslösen (Testbutton, D-055) |
| POST | `/api/plan/run` | Planungslauf auslösen (**der einzige Weg, wie ein Plan entsteht**) |
| POST | `/api/plan/publish` | letzten gültigen Plan erneut nach HA schreiben |
| GET | `/api/plan` | letzter gespeicherter Plan + Validierungsergebnis |
| GET | `/api/ai/test` | KI-Provider-Verbindungstest |
| GET | `/api/diagnostics` | konsolidierter Diagnose-Snapshot |

**Wichtiges Muster:** `/api/plan/run`, `/api/plan/publish`, `/api/plan` fangen
**alles** ab und geben **immer HTTP 200** mit `ok:false` bei Fehlern zurück — nie
HTTP 500. Grund: eine HTML-Fehlerseite würde `response.json()` im Frontend brechen
(ausführlich dokumentiert im Handler `plan_run` in `web/server.py`). Beim Hinzufügen
neuer Endpunkte, die vom Frontend per `fetch` + `.json()` konsumiert werden, dieses
Muster übernehmen.

`_safe_dumps()` = `json.dumps(..., default=str)`-Sicherheitsnetz für nicht
serialisierbare Diagnosewerte (z. B. ein versehentliches `datetime`-Objekt im
Wetter-Kontext).

## Von EP genutzte HEMS-Endpunkte (`hems_client.py`)

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/device_controls_schema` | **einzige** Quelle für Geräte-Discovery (D-036/D-046) |
| GET | `/api/status` | letzter Regelzyklus: Pool, Defizit, Gerätezustände, Fehler |
| GET | `/api/controls` | Live-States aller `ems_*`-Helfer (Client-Methode existiert, aktuell sonst im Code ungenutzt) |

Kurzer Default-Timeout (`DEFAULT_TIMEOUT_S = 10.0`), damit EP nie an einem
langsamen/nicht erreichbaren HEMS hängen bleibt.

## Nicht (mehr) existierende / nie gebaute API-Ebene

Die ursprüngliche Spec sah eine **versionierte interne REST-API**
(`POST /api/v1/strategy-plans`, `GET /api/v1/strategy-plans/current`, `GET /api/v1/system-state`,
`GET /api/v1/device-constraints`, `POST /api/v1/strategy-plans/{plan_id}/cancel`) vor.
**Diese Ebene existiert nicht** — die tatsächlich implementierte API ist die
pragmatische `/api/*`-Liste oben. Bei zukünftiger Arbeit an einer versionierten API
zuerst `user-beispiele/` und aktuelle Anforderungen prüfen, nicht die alte Spec
blind nachbauen.
