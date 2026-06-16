# 02 · Home-Assistant-Integration

> Wie der Energy Pilot Daten **aus** Home Assistant liest und Zustände/Bedienelemente **nach** Home Assistant zurückgibt.

**Status:** Entwurf · **info.md-Bezug:** §6.1, §15, §24

---

## Ziel & Abgrenzung

- Lesen aktueller HA-Zustände über eine streng begrenzte **Allowlist**.
- Bereitstellen eigener Sensoren, Schalter, Auswahlfelder, Zahlen und Aktionen in HA.
- **Nicht** hier: Prognosequellen (→ [04](04-prognosen.md)), HEMS-Kommunikation (→ [06](06-hems-schnittstelle.md)).

Grundsatz: Der Pilot liest **nur explizit konfigurierte oder freigegebene Entitäten** – nie blind die gesamte HA-Datenbank.

---

## Verwendete Services / Technologie

- **HA-Core-REST-API** (Lesen von Zuständen, Aufrufen von Services) über den Supervisor-Proxy.
- **HA-WebSocket-API** für fortlaufende Zustandsänderungen (`subscribe_events` / `state_changed`).
- Module: **Home Assistant Connector**, **Entity Allowlist**, **State Collector**, **History Aggregator**.

---

## Datenfluss: von Home Assistant herein (Eingangsdaten)

Mögliche Eingangsentitäten (info.md §6.1) – jede einzeln über die Allowlist zuzuordnen:

| Gruppe | Werte |
|---|---|
| PV & Netz | aktuelle PV-Leistung, Leistung am Netzübergabepunkt, Netzbezug, Einspeisung |
| Haus | Hausverbrauch |
| Batterie | Batterieleistung, Batterie-SOC, max. Lade-/Entladeleistung |
| Verbraucher | Status steuerbarer Verbraucher, Soll-/Istleistungen, Geräteverfügbarkeit, Betriebsmodi |
| Warmwasser | Warmwassertemperatur |
| E-Auto / Wallbox | Wallbox-Status, Fahrzeug verbunden?, Fahrzeug-SOC, gewünschter SOC, geplante Abfahrtszeit |

**Historische Daten** werden lokal verdichtet (→ [04](04-prognosen.md), [07](07-datenmodell.md)), bevor sie ggf. an die KI gehen – nicht roh exportiert.

---

## Datenfluss: nach Home Assistant hinaus (Ausgabe-Entitäten)

Vorschlag aus info.md §15 (Namen final an HA-Konventionen anpassbar):

**Sensoren**
```text
sensor.skytech_energy_pilot_status
sensor.skytech_energy_pilot_current_strategy
sensor.skytech_energy_pilot_current_plan
sensor.skytech_energy_pilot_plan_valid_until
sensor.skytech_energy_pilot_last_planning
sensor.skytech_energy_pilot_next_planning
sensor.skytech_energy_pilot_confidence
sensor.skytech_energy_pilot_provider
sensor.skytech_energy_pilot_model
sensor.skytech_energy_pilot_expected_pv_energy
sensor.skytech_energy_pilot_expected_grid_import
sensor.skytech_energy_pilot_expected_grid_export
sensor.skytech_energy_pilot_expected_cost
sensor.skytech_energy_pilot_last_error
```

**Schalter**
```text
switch.skytech_energy_pilot_enabled
switch.skytech_energy_pilot_automatic_planning
switch.skytech_energy_pilot_event_replanning
switch.skytech_energy_pilot_auto_submit
```

**Auswahlfelder**
```text
select.skytech_energy_pilot_mode
select.skytech_energy_pilot_strategy
select.skytech_energy_pilot_provider
```

**Zahlenwerte**
```text
number.skytech_energy_pilot_planning_interval_min
number.skytech_energy_pilot_full_replanning_interval_min
number.skytech_energy_pilot_forecast_horizon_h
number.skytech_energy_pilot_minimum_confidence
```

**Aktionen / Services**
```text
skytech_energy_pilot.create_plan
skytech_energy_pilot.simulate_plan
skytech_energy_pilot.submit_plan
skytech_energy_pilot.cancel_plan
skytech_energy_pilot.recalculate_forecast
skytech_energy_pilot.reset_learning_data
```

---

## Möglichkeiten in der Oberfläche

- Auswahl/Zuordnung der freizugebenden Entitäten (Allowlist-Pflege) → [09](09-benutzeroberflaeche.md).
- Anzeige der zuletzt gelesenen Werte und ihrer Aktualität (Erkennung veralteter Messwerte → [08](08-sicherheit.md)).

---

## Wichtige offene Architekturfrage: Wie werden Entitäten veröffentlicht?

Ein Add-on kann nicht „einfach so" HA-Entitäten anlegen. Optionen:

- [ ] **MQTT Discovery** – Add-on publiziert Entitäten via MQTT (benötigt MQTT-Broker; bewährt für Add-ons). *Empfehlung als Startpunkt.*
- [ ] **Begleitende Custom-Integration** – kleines HACS-Custom-Component, das mit dem Add-on spricht und native Entitäten anlegt (mehr Aufwand, sauberste Integration).
- [ ] **REST-API `set state`** – einfach, aber Zustände sind nicht persistent/„echt" und gehen bei HA-Neustart verloren (nur als Notlösung).

---

## Offene Entscheidungen

- [ ] Veröffentlichungsweg der Entitäten (siehe oben) festlegen
- [ ] Endgültige Entity-IDs und `device`-Gruppierung in HA
- [ ] Polling (REST) vs. Push (WebSocket) je Datenart – Default?
- [ ] Umgang mit `unavailable`/`unknown`-Zuständen und Einheiten-Normalisierung (W/kW, Wh/kWh)
- [ ] Schwelle „veralteter Messwert" (max. Alter, ab dem ein Wert verworfen wird)

---

## Aufgaben / Umsetzung

- [ ] Home Assistant Connector (REST + WebSocket) implementieren
- [ ] Entity-Allowlist-Modell + Konfiguration
- [ ] State Collector (laufende Zustandsübernahme)
- [ ] History Aggregator (15-Min-Mittel, Tagesprofile → [04](04-prognosen.md))
- [ ] Veröffentlichungsweg der Ausgabe-Entitäten umsetzen
- [ ] Aktionen/Services registrieren und auf interne Funktionen mappen

---

## Bezug zu anderen Plänen

- Laufzeit/Proxy → [01 · HA-Add-on / Docker](01-ha-addon-docker.md)
- Prognosen & Verdichtung → [04 · Prognosen](04-prognosen.md)
- Datenminimierung & veraltete Werte → [08 · Sicherheit](08-sicherheit.md)
- Bedienelemente in der UI → [09 · Benutzeroberfläche](09-benutzeroberflaeche.md)
