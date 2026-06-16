# 09 — Ingress-Web-UI

## Zweck
Eigene Ingress-Oberfläche in HA (info.md §16). Stil/Stack an HEMS angelehnt (SPA, aiohttp-served).

## Bereiche

### Dashboard
Systemstatus, aktuelle Strategie, aktiver Plan, nächste Planung, wichtigste Sollwerte, erwartete PV-Erzeugung/Hausverbrauch/Netzbezug, Warnungen/Fehler, **Status von HEMS**.

### Energieplan
Zeitlicher Fahrplan, Batterieziele, Prioritäten, Leistungsgrenzen, Zeitfenster, Begründungen, verwendete Daten, Annahme/Ablehnung durch HEMS.

### Prognosen
PV-, Lastprognose, Wetter, Strompreise, Prognoseabweichungen, Datenquellen-Qualität.

### Geräte
Freigegebene Geräte, technische Grenzen, aktuelle Verfügbarkeit, Planvorgaben, tatsächliche Ausführung durch HEMS.

### Ziele & Strategie
Harte Vorgaben, weiche Zielgewichtungen, Komfortziele, Ladeziele, Reservevorgaben, gewünschte Betriebsstrategie.

### KI-Konfiguration
Anbieter, Modell, **API-Schlüssel** (nie geloggt), Timeout, max. API-Aufrufe, Kostenlimit, Datenfreigabe, **Testverbindung**.

### Verlauf & Audit
Frühere Pläne, Planänderungen, Begründungen, Prognose vs. Realität, Fehler, API-Nutzung, angenommene/abgelehnte Pläne.

### Logging (siehe [10](10-logging-observability.md))
Live-Logansicht + maschinenlesbarer Export.

## Konfigurationsseite (Addon)
- Entitätszuordnung nach Namensschema + **Fallback** je Feld.
- Freie Entitätsnamen für Fremddaten (Strompreis/PV/Wetter).
- Intervalle (Planung/Neuplanung/Horizont), Mindestkonfidenz, Betriebsmodus, Strategie, Provider.

## Technik (D-010)
- **Start einfach/funktional:** aiohttp serviert SPA + JSON-API in **vanilla JS/CSS** (wie HEMS, konsistent). Ingress-Auth über HA.
- Daten aus EP-Backend (REST), Live-Updates ggf. via WebSocket/Polling.
- Später optional ein Framework für eine schönere Oberfläche.

## Offene Punkte
- Diagramme: eigene Visualisierung vs. Verweis auf HA-Energie-Dashboard?
