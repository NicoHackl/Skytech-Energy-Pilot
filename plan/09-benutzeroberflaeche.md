# 09 · Benutzeroberfläche (Ingress Web UI)

> Eigene, in Home Assistant eingebettete Ingress-Oberfläche zur Anzeige und Steuerung des Energy Pilot.

**Status:** Entwurf · **info.md-Bezug:** §16

---

## Ziel & Abgrenzung

- Alle Informationen und Einstellungen an einem Ort, eingebettet in HA.
- **Nicht** hier: die zugrunde liegende Logik (jeweils eigene Pläne), nur deren Darstellung/Bedienung.

Modul: **Ingress Web UI**.

---

## Verwendete Services / Technologie

- **Ingress** bettet die UI direkt in die HA-Oberfläche ein (kein extra Login/Port → [01](01-ha-addon-docker.md)).
- Frontend kommuniziert mit dem App-Backend; Backend liefert Zustände/Pläne/Prognosen.
- Bedienelemente spiegeln sich teils als HA-Entitäten (Schalter/Select/Number → [02](02-home-assistant.md)).

---

## Views (info.md §16)

### Dashboard
Systemstatus · aktuelle Strategie · aktiver Plan · nächste Planung · wichtigste Sollwerte · erwartete PV-Erzeugung · erwarteter Hausverbrauch · erwarteter Netzbezug · Warnungen/Fehler · Status von Skytech HEMS.

### Energieplan
Zeitlicher Fahrplan · Batterieziele · Prioritäten · Leistungsgrenzen · Zeitfenster · Begründungen · verwendete Daten · Annahme/Ablehnung durch HEMS.

### Prognosen
PV-Prognose · Lastprognose · Wetter · Strompreise · Prognoseabweichungen · Qualität der Datenquellen. (→ [04](04-prognosen.md))

### Geräte
Freigegebene Geräte · technische Grenzen · aktuelle Verfügbarkeit · Planvorgaben · tatsächliche Ausführung durch HEMS.

### Ziele und Strategie
Harte Vorgaben · weiche Zielgewichtungen · Komfortziele · Ladeziele · Reservevorgaben · gewünschte Betriebsstrategie. (→ [08](08-sicherheit.md))

### KI-Konfiguration
Anbieter · Modell · API-Schlüssel · Timeout · max. API-Aufrufe · Kostenlimit · Datenfreigabe · Testverbindung. (→ [03](03-ki-api.md))

### Verlauf und Audit
Frühere Pläne · Planänderungen · Begründungen · Prognose gegen Realität · Fehler · API-Nutzung · angenommene/abgelehnte Pläne. (→ [07](07-datenmodell.md), [08](08-sicherheit.md))

---

## Bedienelemente / Aktionen

- Plan-Aktionen: **erstellen, simulieren, übergeben, abbrechen** (`create/simulate/submit/cancel_plan`).
- Betriebsmodus wählen (→ [10](10-betriebsmodi.md)); Autopilot/Auto-Submit-Schalter.
- Plan **bestätigen** im Vorschlagsmodus.
- Intervalle, Horizont, Mindestkonfidenz einstellen.
- **Testverbindung** zur KI; Kostenlimits.
- Entity-Allowlist pflegen (→ [02](02-home-assistant.md)).
- Not-Aus / manueller Modus (→ [08](08-sicherheit.md)).

---

## Offene Entscheidungen

- [ ] Frontend-Technologie: schlankes JS (z. B. Vue/Svelte/React) vs. servergerendert (z. B. FastAPI + HTMX/Jinja)
- [ ] Diagramm-Bibliothek für Fahrplan/Prognosekurven
- [ ] Backend-API zur UI: REST vs. WebSocket (Live-Updates)
- [ ] Dunkel-/Hell-Theme passend zu HA übernehmen?
- [ ] Mehrsprachigkeit (DE/EN) von Anfang an?
- [ ] Welche Einstellungen leben in der UI vs. in den Add-on-Optionen (→ [01](01-ha-addon-docker.md))?

---

## Aufgaben / Umsetzung

- [ ] Ingress-Grundgerüst + Routing der Views
- [ ] Backend-API für die UI (Zustände/Pläne/Prognosen/Konfig)
- [ ] Dashboard-View
- [ ] Energieplan-View (inkl. Begründungen + HEMS-Status)
- [ ] Prognosen-View
- [ ] Geräte-View
- [ ] Ziele-&-Strategie-View
- [ ] KI-Konfigurations-View (inkl. Testverbindung)
- [ ] Verlauf-&-Audit-View

---

## Bezug zu anderen Plänen

- Einbettung/Ingress → [01 · HA-Add-on / Docker](01-ha-addon-docker.md)
- Datenquellen der Views → [02](02-home-assistant.md), [04](04-prognosen.md), [05](05-planungs-engine.md), [07](07-datenmodell.md)
- KI-Einstellungen → [03 · KI / API](03-ki-api.md)
- Ziele/Grenzen/Audit → [08 · Sicherheit](08-sicherheit.md)
- Modusauswahl → [10 · Betriebsmodi](10-betriebsmodi.md)
