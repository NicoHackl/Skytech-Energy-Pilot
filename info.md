# Skytech Energy Pilot

> KI-gestützte, vorausschauende Energieplanung für Home Assistant und Skytech HEMS

**Projektname:** Skytech Energy Pilot  
**Kurzbezeichnung:** Energy Pilot  
**Repository:** `Skytech-Energy-Pilot`  
**Home-Assistant-App-Slug:** `skytech_energy_pilot`  
**Containername:** `skytech-energy-pilot`  
**Dokumentstand:** 16.06.2026

---

## 1. Projektidee

Skytech Energy Pilot ist eine eigenständige Home-Assistant-App für die intelligente, vorausschauende Steuerung einer privaten oder kleinen gewerblichen Energieanlage.

Die App verbindet Home-Assistant-Daten mit externen Prognosen und einem auswählbaren KI-Dienst wie OpenAI GPT oder Google Gemini. Daraus erstellt sie in regelmäßigen Abständen einen strategischen Energieplan.

Der Energy Pilot entscheidet nicht im Sekundenbereich über die konkrete Geräteleistung. Er legt stattdessen die übergeordneten Rahmenbedingungen fest, innerhalb derer Skytech HEMS die Anlage schnell, lokal und sicher regelt.

Typische Entscheidungen des Energy Pilot sind:

- Welche Geräte aktuell freigegeben werden
- Welche Priorität ein Gerät erhält
- Welche minimale und maximale Leistung verwendet werden darf
- Wann ein Verbraucher bevorzugt betrieben werden soll
- Wie stark der Batteriespeicher geladen oder entladen werden darf
- Welcher Batterie-SOC zu einem bestimmten Zeitpunkt erreicht werden soll
- Welche Energiemenge für das E-Auto reserviert werden muss
- Ob Netzladung erlaubt ist
- Welche Reserve für spätere Verbraucher oder den Abend zurückgehalten wird

---

## 2. Abgrenzung zu Skytech HEMS

Skytech Energy Pilot und Skytech HEMS sind zwei eigenständige Home-Assistant-Apps mit klar getrennten Verantwortlichkeiten.

### Skytech Energy Pilot

Der Energy Pilot übernimmt die strategische und vorausschauende Planung:

- Auswertung aktueller Energie- und Gerätezustände
- Verarbeitung von PV-, Wetter-, Last- und Preisprognosen
- Planung über einen Horizont von etwa 24 bis 48 Stunden
- Festlegung dynamischer Prioritäten
- Vorgabe von Leistungsgrenzen und Zeitfenstern
- Festlegung von Batterie- und Ladezielen
- Erstellung und Begründung eines Energieplans
- regelmäßige Aktualisierung des Plans
- Simulation und Bewertung von Planvarianten
- Protokollierung von Entscheidungen und Prognoseabweichungen

### Skytech HEMS

Skytech HEMS bleibt für die lokale Echtzeitregelung und Geräteansteuerung zuständig:

- schnelle Ausregelung am Netzübergabepunkt
- Verteilung des tatsächlich verfügbaren PV-Überschusses
- Berechnung konkreter Sollleistungen
- Ansteuerung von Speicher, Heizstab, Heizlüftern und Wallbox
- Einhaltung technischer Grenzen
- Berücksichtigung von Hysterese, Rampen und Reserven
- Mindestlaufzeiten und Mindestauszeiten
- sichere Weiterarbeit bei Ausfall des Energy Pilot oder eines Cloud-Dienstes
- lokale Fallback-Strategie

### Grundprinzip

```text
Prognosen, Ziele und Home-Assistant-Daten
                  │
                  ▼
       Skytech Energy Pilot
      strategische Planung
       alle 15–60 Minuten
                  │
                  ▼
           gültiger Plan
                  │
                  ▼
           Skytech HEMS
    lokale Regelung alle 1–2 Sekunden
                  │
                  ▼
 Speicher, Heizstab, Heizlüfter, Wallbox
```

Der Energy Pilot darf keine Geräte direkt per Modbus, MQTT oder herstellerspezifischer API ansteuern. Jede reale Leistungsänderung erfolgt über Skytech HEMS.

---

## 3. Warum eine eigenständige Home-Assistant-App?

Die Trennung bietet mehrere Vorteile:

- Die schnelle HEMS-Regelung bleibt unabhängig von KI, Internet und Cloud.
- Ein Fehler im Energy Pilot beeinträchtigt nicht die sichere Grundregelung.
- Skytech HEMS kann auch ohne Energy Pilot verwendet werden.
- Der KI-Anbieter kann unabhängig vom HEMS ausgetauscht werden.
- Prognose-, KI- und Optimierungsfunktionen können separat entwickelt und aktualisiert werden.
- Beide Projekte erhalten klar abgegrenzte GitHub-Repositories.
- Der Energy Pilot kann später theoretisch auch andere Energiemanagementsysteme über Adapter anbinden.
- Fehler, Logs und Versionsstände lassen sich den jeweiligen Komponenten eindeutig zuordnen.

Vorgesehene Repository-Struktur:

```text
Skytech-HEMS
Skytech-Energy-Pilot
```

---

## 4. Planungsintervalle

Der Energy Pilot arbeitet nicht im Sekundenbereich. Er erstellt und aktualisiert einen strategischen Plan in einem konfigurierbaren Intervall.

### Vollständige Neuplanung

Empfohlener Standard: **alle 60 Minuten**

Dabei werden alle verfügbaren Daten und Prognosen neu bewertet und ein vollständiger Plan für die nächsten 24 bis 48 Stunden erstellt.

### Planaktualisierung

Empfohlener Standard: **alle 15 Minuten**

Dabei wird geprüft, ob der bestehende Plan aufgrund neuer Messwerte oder Prognoseabweichungen angepasst werden muss.

### Ereignisbasierte Neuberechnung

Eine außerplanmäßige Neuberechnung soll möglich sein, wenn ein wichtiges Ereignis eintritt, zum Beispiel:

- Das E-Auto wird angesteckt oder getrennt.
- Die gewünschte Abfahrtszeit ändert sich.
- Der gewünschte Fahrzeug-SOC wird geändert.
- Die reale PV-Erzeugung weicht deutlich von der Prognose ab.
- Der Hausverbrauch verändert sich unerwartet stark.
- Ein steuerbares Gerät wird verfügbar oder fällt aus.
- Der Batteriespeicher erreicht eine kritische Grenze.
- Neue Strompreise stehen zur Verfügung.
- Der Benutzer ändert Strategie, Betriebsmodus oder Zielgewichtung.
- Ein aktueller Plan wird ungültig oder läuft ab.

Alle Zeitintervalle müssen in der Benutzeroberfläche konfigurierbar sein. Der zulässige Bereich für eine reguläre Planung soll zunächst zwischen 15 und 60 Minuten liegen.

---

## 5. Unterstützte KI-Dienste

Der Energy Pilot soll eine austauschbare Provider-Schnittstelle besitzen.

Für die erste Version sind vorgesehen:

- OpenAI API mit GPT-Modellen
- Google Gemini API

Später mögliche Erweiterungen:

- lokale Modelle über Ollama
- OpenAI-kompatible APIs
- weitere Cloud-Anbieter
- vollständig lokale Planungslogik ohne externes Sprachmodell

API-Schlüssel werden ausschließlich in der App-Konfiguration oder einem geeigneten Secret-Speicher abgelegt und niemals in Logs, Plänen oder Home-Assistant-Entitäten ausgegeben.

Das Sprachmodell soll nur über klar definierte Funktionen und strukturierte Daten arbeiten. Freie Textausgaben dürfen niemals direkt als Steuerbefehl verwendet werden.

Beispielhafte Tools des KI-Agenten:

```text
get_current_energy_state()
get_recent_energy_history()
get_energy_forecast()
get_device_constraints()
get_user_objectives()
get_current_plan()
calculate_candidate_plan()
simulate_candidate_plan()
validate_candidate_plan()
submit_energy_plan()
explain_energy_plan()
```

---

## 6. Datenquellen

### 6.1 Aktuelle Home-Assistant-Daten

Der Energy Pilot liest nur explizit konfigurierte oder freigegebene Entitäten.

Mögliche Eingangsdaten:

- aktuelle PV-Leistung
- Hausverbrauch
- Leistung am Netzübergabepunkt
- Netzbezug und Einspeisung
- Batterieleistung
- Batterie-SOC
- maximal verfügbare Lade- und Entladeleistung
- Status der steuerbaren Verbraucher
- aktuelle Soll- und Istleistungen
- Warmwassertemperatur
- Status der Wallbox
- Fahrzeug verbunden oder nicht verbunden
- Fahrzeug-SOC
- gewünschter Fahrzeug-SOC
- geplante Abfahrtszeit
- Geräteverfügbarkeit
- aktuelle Betriebsmodi

### 6.2 Historische Daten

Historische Daten sollen vor der Übergabe an einen externen KI-Dienst lokal verdichtet werden.

Beispiele:

- 15-Minuten-Mittelwerte
- Verbrauch der letzten 24 Stunden
- typische Lastprofile nach Wochentag und Uhrzeit
- PV-Ertrag vergleichbarer Tage
- bisherige Prognosefehler
- Speicher-SOC-Verlauf
- Laufzeiten flexibler Verbraucher
- tatsächlich benötigte Energiemengen
- erreichte und verfehlte Ladeziele

Es soll nicht standardmäßig die vollständige Home-Assistant-Datenbank an einen externen Dienst übertragen werden.

### 6.3 Externe Prognosen

Mögliche externe Daten:

- PV-Erzeugungsprognose
- Wettervorhersage
- Bewölkung
- Außentemperatur
- stündliche Strompreise
- Netzentgelte und Tarifbestandteile
- optionale Einspeiseprognosen
- Sonnenaufgang und Sonnenuntergang

Externe Daten werden möglichst durch die App oder vorhandene Home-Assistant-Integrationen strukturiert abgerufen. Das Sprachmodell soll Werte nicht selbst unkontrolliert im Internet recherchieren.

### 6.4 Benutzerziele

Beispiele für Benutzerziele:

- Eigenverbrauch maximieren
- Netzbezug minimieren
- Stromkosten minimieren
- Einspeisung reduzieren
- Batteriespeicher schonen
- Auto bevorzugt mit PV laden
- Warmwasser bevorzugt mit PV erzeugen
- Mindestreserve für den Abend halten
- Fahrzeug bis zu einem Termin auf einen Mindest-SOC laden
- Komfort vor maximaler Wirtschaftlichkeit priorisieren

---

## 7. Harte Grenzen und weiche Ziele

### Harte Grenzen

Harte Grenzen dürfen niemals durch die KI verändert oder verletzt werden.

Beispiele:

- minimaler und maximaler Batterie-SOC
- maximale Ladeleistung des Speichers
- maximale Entladeleistung des Speichers
- maximale Wallboxleistung
- minimale technisch mögliche Ladeleistung
- zulässige Stromstärke je Phase
- maximale Warmwassertemperatur
- Mindestlaufzeiten
- Mindestauszeiten
- maximale Änderung pro Regelschritt
- zulässige Netzanschlussleistung
- verbindliches Fahrzeug-Ladeziel
- Geräteverfügbarkeit
- Benutzer- oder Sicherheitsfreigaben

Die harten Grenzen werden lokal gespeichert und durch Skytech HEMS beziehungsweise einen lokalen Validator garantiert.

### Weiche Ziele

Weiche Ziele können gegeneinander abgewogen werden.

Beispiele:

- möglichst wenig Netzbezug
- möglichst geringer Strompreis
- möglichst hoher PV-Eigenverbrauch
- möglichst geringe Batteriebelastung
- möglichst wenig Einspeisung
- Warmwasser bevorzugt aus PV
- E-Auto bevorzugt aus PV
- Reserve für den Abend
- Komfortorientierung

Für weiche Ziele können Gewichtungen verwendet werden.

Beispiel:

```text
Versorgungssicherheit             100 %
E-Auto-Ladeziel                   100 %
Warmwasserkomfort                 100 %
Netzbezug minimieren               90 %
Stromkosten minimieren             85 %
Eigenverbrauch maximieren          80 %
Einspeisung reduzieren             70 %
Batterieschonung                   50 %
```

---

## 8. Ausgabe des Energy Pilot

Der Energy Pilot erzeugt ausschließlich einen strukturierten, zeitlich begrenzten Energieplan.

Mögliche Planinhalte:

### Batteriespeicher

- minimal zulässiger SOC
- gewünschter Ziel-SOC
- Zeitpunkt des Ziel-SOC
- minimale Ladeleistung
- maximale Ladeleistung
- maximale Entladeleistung
- Netzladung erlaubt oder verboten
- reservierte Energie für einen späteren Zeitraum
- gewünschte Lade- oder Entladestrategie

### Flexible Verbraucher

Für jedes Gerät:

- Freigabe
- Betriebsmodus
- Priorität
- minimale Leistung
- maximale Leistung
- geschützte Mindestleistung
- Leistungsreserve
- frühester Start
- spätestes Ende
- benötigte Energiemenge
- Zielzeitpunkt
- Netzbezug erlaubt oder verboten

### Metadaten

- Plan-ID
- Erstellungszeitpunkt
- Gültigkeitsbeginn
- Ablaufzeitpunkt
- verwendete Prognosen
- verwendeter KI-Provider und Modellname
- Konfidenzwert
- Begründung
- Warnungen
- erwartete Auswirkungen
- Versionsnummer des Planformats

---

## 9. Beispiel eines Energieplans

```json
{
  "schema_version": "1.0",
  "plan_id": "2026-06-16T14:00:00+02:00",
  "created_at": "2026-06-16T14:00:00+02:00",
  "valid_from": "2026-06-16T14:00:00+02:00",
  "valid_until": "2026-06-16T15:00:00+02:00",
  "strategy": "pv_self_consumption",
  "confidence": 0.86,

  "battery": {
    "minimum_soc_percent": 25,
    "target_soc_percent": 75,
    "target_time": "2026-06-16T17:00:00+02:00",
    "minimum_charge_power_w": 0,
    "maximum_charge_power_w": 3500,
    "maximum_discharge_power_w": 2500,
    "grid_charging_allowed": false,
    "reserve_for_evening_wh": 3200
  },

  "devices": {
    "wallbox": {
      "enabled": true,
      "mode": "surplus",
      "priority": 1,
      "minimum_power_w": 1380,
      "maximum_power_w": 4200,
      "target_energy_wh": 9000,
      "deadline": "2026-06-17T06:30:00+02:00",
      "grid_power_allowed": false
    },

    "heizstab": {
      "enabled": true,
      "mode": "surplus",
      "priority": 2,
      "minimum_power_w": 0,
      "maximum_power_w": 1800,
      "protected_minimum_power_w": 0,
      "start_not_before": "2026-06-16T14:30:00+02:00",
      "stop_not_after": "2026-06-16T17:00:00+02:00"
    },

    "heizlufter_1": {
      "enabled": false,
      "priority": 4
    }
  },

  "reasoning_summary": [
    "Hohe PV-Erzeugung wird bis 16:30 Uhr erwartet.",
    "Das E-Auto benötigt bis morgen früh 9 kWh.",
    "Die Warmwassertemperatur ist bereits ausreichend.",
    "Ein Teil der Speicherkapazität soll für die Abendlast reserviert werden."
  ]
}
```

Der Plan ist nur eine strategische Vorgabe. Skytech HEMS berechnet daraus weiterhin die tatsächlich anzufordernde Leistung im Sekundenbereich.

---

## 10. Schnittstelle zwischen Energy Pilot und Skytech HEMS

Empfohlen wird eine klar versionierte interne Schnittstelle.

### Bevorzugte Architektur

1. Der Energy Pilot liest Home-Assistant-Zustände über die interne REST- und WebSocket-Anbindung.
2. Der Energy Pilot erstellt einen Kandidatenplan.
3. Ein lokaler Validator prüft Struktur, Wertebereiche und Zeitangaben.
4. Der Plan wird optional simuliert.
5. Der gültige Plan wird über eine interne, versionierte API an Skytech HEMS übertragen.
6. Skytech HEMS prüft den Plan erneut.
7. Skytech HEMS übernimmt nur erlaubte Parameter.
8. Skytech HEMS meldet Annahme, Ablehnung und aktuellen Ausführungsstatus zurück.
9. Wichtige Zustände werden zusätzlich als Home-Assistant-Entitäten sichtbar gemacht.

Beispielhafte interne Endpunkte:

```text
POST /api/v1/strategy-plans
GET  /api/v1/strategy-plans/current
GET  /api/v1/strategy-plans/{plan_id}
GET  /api/v1/system-state
GET  /api/v1/device-constraints
POST /api/v1/strategy-plans/{plan_id}/cancel
```

Eine alternative Kommunikation über MQTT kann später als zusätzlicher Adapter vorgesehen werden. Der primäre Vertrag zwischen beiden Apps soll jedoch unabhängig von einzelnen Home-Assistant-Helfern und als versioniertes Datenschema definiert sein.

---

## 11. Ablauf einer Planung

```text
1. Aktuelle Home-Assistant-Daten erfassen
2. Historische Werte lokal verdichten
3. Externe Prognosen aktualisieren
4. Gerätegrenzen und Benutzerziele laden
5. Bestehenden Plan und Abweichungen analysieren
6. Kandidatenplan durch Optimierungslogik und KI erzeugen
7. Kandidatenplan lokal validieren
8. Plan simulieren und bewerten
9. Ungültigen Plan verwerfen oder korrigieren
10. Gültigen Plan an Skytech HEMS übertragen
11. Annahme oder Ablehnung protokollieren
12. Ausführung überwachen
13. Prognose und Realität vergleichen
14. Erkenntnisse für die nächste Planung speichern
```

---

## 12. Rolle der KI

Die KI ist Energie-Manager und Orchestrator, aber nicht der alleinige mathematische Regler.

Geeignete Aufgaben:

- Benutzerziele interpretieren
- Zielkonflikte bewerten
- relevante Daten und Werkzeuge auswählen
- mehrere Planvarianten vergleichen
- auf außergewöhnliche Situationen reagieren
- einen strukturierten Plan erstellen
- Entscheidungen verständlich begründen
- fehlende oder widersprüchliche Daten erkennen
- eine lokale Optimierungsengine gezielt aufrufen
- Simulationsergebnisse interpretieren

Nicht geeignete Aufgaben:

- direkte Gerätesteuerung
- sekundenschnelle Netzregelung
- Umgehung technischer Grenzen
- Erzeugung und Ausführung freien Programmcodes
- selbstständige Änderung von Sicherheitsparametern
- unkontrollierter Zugriff auf alle Home-Assistant-Entitäten
- Ersatz für lokale Schutz- und Fallback-Logik

Langfristig soll die eigentliche Leistungs- und Fahrplanoptimierung möglichst durch eine lokale, deterministische Optimierungsengine unterstützt werden. Die KI koordiniert, bewertet und erklärt deren Ergebnisse.

---

## 13. Sicherheitskonzept

Folgende Regeln sind verbindlich:

- Zugriff nur auf freigegebene Entitäten und Funktionen
- keine direkte Ansteuerung von Modbus, MQTT oder Geräte-APIs durch das Sprachmodell
- strukturierte Ein- und Ausgaben
- JSON-Schema-Validierung jedes Plans
- Prüfung aller technischen Grenzen
- Ablaufzeit für jeden Plan
- Ablehnung veralteter Messwerte
- Erkennung fehlender Daten
- maximale Änderung zwischen zwei Plänen
- optional notwendige Benutzerfreigabe
- vollständiges Audit-Log
- Not-Aus und manueller Modus
- lokaler Betrieb von Skytech HEMS bei Cloud-Ausfall
- keine Ausführung von durch die KI erzeugtem Code
- kein API-Schlüssel in Logs oder Entitäten
- konfigurierbares Datenminimum für externe KI-Dienste

### Verhalten bei Ausfall

1. Skytech HEMS verwendet den letzten gültigen Plan bis zu dessen Ablauf.
2. Nach Ablauf wechselt Skytech HEMS auf eine lokale Standardstrategie.
3. Kritische harte Grenzen bleiben immer aktiv.
4. Der Benutzer wird in Home Assistant über den Ausfall informiert.
5. Nach Wiederherstellung erstellt der Energy Pilot einen vollständig neuen Plan.
6. Ein abgelaufener Plan darf niemals stillschweigend unbegrenzt weiterverwendet werden.

---

## 14. Betriebsmodi

### Beobachten

- Daten werden analysiert.
- Es werden keine Pläne an Skytech HEMS übertragen.
- Die App zeigt Prognosen, mögliche Entscheidungen und Begründungen.

### Vorschlagen

- Der Energy Pilot erstellt einen konkreten Plan.
- Der Benutzer muss ihn manuell bestätigen.
- Erst danach wird der Plan an Skytech HEMS übergeben.

### Shadow Mode

- Der Energy Pilot erstellt automatisch Pläne.
- Die Pläne werden nicht ausgeführt.
- Die theoretischen Ergebnisse werden mit der realen Anlagenentwicklung verglichen.

### Autopilot

- Validierte Pläne werden automatisch an Skytech HEMS übertragen.
- Harte Grenzen und lokale Sicherheitsprüfungen bleiben aktiv.
- Der Benutzer kann jederzeit in einen manuellen Modus wechseln.

Empfohlene Einführung:

```text
Beobachten → Vorschlagen → Shadow Mode → Autopilot
```

---

## 15. Home-Assistant-Entitäten

Mögliche Entitäten der App:

### Sensoren

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

### Schalter

```text
switch.skytech_energy_pilot_enabled
switch.skytech_energy_pilot_automatic_planning
switch.skytech_energy_pilot_event_replanning
switch.skytech_energy_pilot_auto_submit
```

### Auswahlfelder

```text
select.skytech_energy_pilot_mode
select.skytech_energy_pilot_strategy
select.skytech_energy_pilot_provider
```

### Zahlenwerte

```text
number.skytech_energy_pilot_planning_interval_min
number.skytech_energy_pilot_full_replanning_interval_min
number.skytech_energy_pilot_forecast_horizon_h
number.skytech_energy_pilot_minimum_confidence
```

### Aktionen

```text
skytech_energy_pilot.create_plan
skytech_energy_pilot.simulate_plan
skytech_energy_pilot.submit_plan
skytech_energy_pilot.cancel_plan
skytech_energy_pilot.recalculate_forecast
skytech_energy_pilot.reset_learning_data
```

Die endgültigen Entitätsnamen können bei der Implementierung an die Home-Assistant-Konventionen angepasst werden.

---

## 16. Benutzeroberfläche

Die App erhält eine eigene Ingress-Oberfläche innerhalb von Home Assistant.

### Dashboard

- aktueller Systemstatus
- aktuelle Strategie
- aktiver Plan
- nächste Planung
- wichtigste Sollwerte
- erwartete PV-Erzeugung
- erwarteter Hausverbrauch
- erwarteter Netzbezug
- Warnungen und Fehler
- Status von Skytech HEMS

### Energieplan

- zeitlicher Fahrplan
- Batterieziele
- Prioritäten
- Leistungsgrenzen
- Zeitfenster
- Begründungen
- verwendete Daten
- Annahme oder Ablehnung durch HEMS

### Prognosen

- PV-Prognose
- Lastprognose
- Wetter
- Strompreise
- Prognoseabweichungen
- Qualität der Datenquellen

### Geräte

- freigegebene Geräte
- technische Grenzen
- aktuelle Verfügbarkeit
- Planvorgaben
- tatsächliche Ausführung durch HEMS

### Ziele und Strategie

- harte Vorgaben
- weiche Zielgewichtungen
- Komfortziele
- Ladeziele
- Reservevorgaben
- gewünschte Betriebsstrategie

### KI-Konfiguration

- Anbieter
- Modell
- API-Schlüssel
- Timeout
- maximale API-Aufrufe
- Kostenlimit
- Datenfreigabe
- Testverbindung

### Verlauf und Audit

- frühere Pläne
- Planänderungen
- Begründungen
- Prognose gegen Realität
- Fehler
- API-Nutzung
- angenommene und abgelehnte Pläne

---

## 17. Interne Module

```text
Skytech Energy Pilot
├── Home Assistant Connector
├── Skytech HEMS Connector
├── Entity Allowlist
├── State Collector
├── History Aggregator
├── Forecast Manager
│   ├── PV Forecast
│   ├── Load Forecast
│   ├── Weather Forecast
│   └── Electricity Price Forecast
├── Device and Constraint Model
├── User Objective Manager
├── AI Provider Interface
│   ├── OpenAI Provider
│   └── Gemini Provider
├── Planning Engine
├── Simulation Engine
├── Plan Validator
├── Plan Submission
├── Monitoring and Feedback
├── Audit Log
├── Database
└── Ingress Web UI
```

---

## 18. Lokale Datenhaltung

Die App benötigt eine eigene Datenhaltung, beispielsweise SQLite für die erste Version.

Zu speichern sind:

- Konfiguration
- Entitätszuordnungen
- technische Grenzen
- Zielgewichtungen
- verdichtete historische Werte
- Prognosen
- Energiepläne
- Simulationsergebnisse
- Planannahmen und Ablehnungen
- reale Ergebnisse
- Prognoseabweichungen
- Fehlermeldungen
- API-Nutzungsstatistik
- Audit-Ereignisse

Eine spätere Unterstützung externer Datenbanken wie PostgreSQL kann vorgesehen werden.

---

## 19. Datenschutz und Kostenkontrolle

- Externe KI-Dienste erhalten nur die für die Planung notwendigen Daten.
- Persönliche Namen und unnötige Home-Assistant-Entitäten werden nicht übertragen.
- Historische Daten werden vor der Übertragung verdichtet.
- API-Schlüssel werden geschützt gespeichert.
- Jede Anfrage wird mit Anbieter, Modell, Zeitpunkt und geschätztem Verbrauch protokolliert.
- Tages- und Monatslimits sollen konfigurierbar sein.
- Bei Erreichen eines Limits wechselt die App in einen lokalen oder passiven Modus.
- Der Benutzer kann einsehen, welche Daten an den KI-Anbieter übermittelt wurden.
- Die App muss auch ohne externen KI-Dienst eine sichere Deaktivierung oder einfache lokale Strategie unterstützen.

---

## 20. Erste Ausbaustufe

Die erste Version konzentriert sich auf wenige, klar definierte Ausgaben.

### Batteriespeicher

- Mindest-SOC
- Ziel-SOC
- Zielzeit
- maximale Ladeleistung
- maximale Entladeleistung
- Netzladung erlaubt oder verboten

### Flexible Verbraucher

- Freigabe
- Priorität
- minimale Leistung
- maximale Leistung
- geschützte Mindestleistung
- Reserve
- optionales Zeitfenster

### Unterstützte Geräte

Initial:

- Batteriespeicher
- Heizstab
- Heizlüfter 1
- Heizlüfter 2

Später:

- Wallbox und E-Auto
- Wärmepumpe
- weitere flexible Verbraucher
- dynamische Tarife und Netzladung
- mehrere Speicher
- weitere Erzeugungsanlagen

---

## 21. Empfohlene Entwicklungsphasen

### Phase 1 – Daten und Anzeige

- eigenständige Home-Assistant-App
- Ingress-Weboberfläche
- Verbindung zu Home Assistant
- konfigurierbare Entitätszuordnung
- Anzeige aktueller Werte
- Abruf und Anzeige von Prognosen
- keine Übergabe an Skytech HEMS

### Phase 2 – Vorschlagsmodus

- OpenAI- und Gemini-Provider
- strukturierte Planausgabe
- lokale Validierung
- verständliche Begründung
- manuelle Bestätigung
- Planexport
- noch keine automatische Steuerung

### Phase 3 – HEMS-Schnittstelle

- versionierte interne API
- Übergabe bestätigter Pläne
- Annahme oder Ablehnung durch Skytech HEMS
- Statusrückmeldung
- Planablauf und Fallback

### Phase 4 – Shadow Mode

- automatische Planerstellung
- Simulation
- Vergleich von Plan und Realität
- Kennzahlen und Fehleranalyse
- Optimierung der Prognosen

### Phase 5 – Autopilot

- automatische Übernahme gültiger Pläne
- ereignisbasierte Neuberechnung
- konfigurierbare Vertrauensschwelle
- Benachrichtigungen
- umfassendes Audit-Log

### Phase 6 – Lokale Optimierungsengine

- mathematische Fahrplanoptimierung
- Modellierung von Speicherverlusten
- Kosten- und Eigenverbrauchsoptimierung
- rollierende Planung
- KI zur Orchestrierung, Bewertung und Erklärung

---

## 22. Erfolgskriterien

Der Energy Pilot ist erfolgreich, wenn er gegenüber einer festen oder rein reaktiven Strategie messbare Vorteile erzielt.

Mögliche Kennzahlen:

- geringerer Netzbezug
- geringere Stromkosten
- höherer PV-Eigenverbrauch
- weniger unnötige Einspeisung
- weniger verfehlte Fahrzeug-Ladeziele
- ausreichende Warmwasserverfügbarkeit
- geringere Batteriebelastung
- bessere Nutzung dynamischer Strompreise
- geringe Zahl manueller Eingriffe
- nachvollziehbare Entscheidungen
- sichere Weiterarbeit bei KI- oder Internetausfall

Der Shadow Mode soll diese Werte vor Aktivierung des Autopiloten über mehrere Wochen vergleichen.

---

## 23. Nicht-Ziele der ersten Version

Die erste Version soll ausdrücklich nicht:

- den schnellen Regelkreis von Skytech HEMS ersetzen
- Geräte direkt per Modbus oder MQTT regeln
- ohne lokale Validierung KI-Befehle ausführen
- alle möglichen Energiegeräte sofort unterstützen
- die vollständige Home-Assistant-Datenbank an einen KI-Dienst übertragen
- selbstständig technische Sicherheitsgrenzen verändern
- ohne nachvollziehbare Protokollierung arbeiten
- bei Cloud-Ausfall die lokale Energieanlage blockieren

---

## 24. Technische Grundlagen

Home-Assistant-Apps können über den internen Supervisor-Proxy auf die Home-Assistant-Core-API zugreifen und über interne App-Netzwerke miteinander kommunizieren. Die Home-Assistant-WebSocket-API kann Zustandsänderungen fortlaufend bereitstellen. Eine Weboberfläche kann über Ingress direkt in die Home-Assistant-Oberfläche eingebettet werden.

Home Assistant besitzt außerdem eine LLM-API, über die ausgewählte Assist-Funktionen an Sprachmodelle angebunden und durch eigene Integrationen erweitert werden können. Für den Energy Pilot wird dennoch eine eng begrenzte, projektspezifische Tool-Schnittstelle bevorzugt.

OpenAI und Google Gemini unterstützen Function Calling beziehungsweise Tool Calling. Dabei stellt das Modell strukturierte Funktionsaufrufe mit definierten Parametern bereit. Diese Aufrufe werden von der Anwendung geprüft und ausgeführt. Das Modell erhält keinen direkten Zugriff auf Geräte oder interne APIs.

---

## 25. Referenzen

- Home Assistant – App communication:  
  https://developers.home-assistant.io/docs/apps/communication

- Home Assistant – Presenting your app / Ingress:  
  https://developers.home-assistant.io/docs/apps/presentation/

- Home Assistant – WebSocket API:  
  https://developers.home-assistant.io/docs/api/websocket/

- Home Assistant – REST API:  
  https://developers.home-assistant.io/docs/api/rest/

- Home Assistant – API for Large Language Models:  
  https://developers.home-assistant.io/docs/core/llm/

- OpenAI – Function Calling:  
  https://developers.openai.com/api/docs/guides/function-calling

- OpenAI – Structured Outputs:  
  https://developers.openai.com/api/docs/guides/structured-outputs

- Google Gemini – Function Calling:  
  https://ai.google.dev/gemini-api/docs/function-calling

---

## 26. Zusammenfassung

Skytech Energy Pilot ist eine eigenständige Home-Assistant-App für die KI-gestützte und vorausschauende Energieplanung.

Die App analysiert aktuelle Home-Assistant-Daten, historische Verläufe, externe Prognosen und Benutzerziele. Alle 15 bis 60 Minuten erstellt sie daraus einen strukturierten Energieplan mit Freigaben, Prioritäten, Leistungsgrenzen, Zeitfenstern und Batterie- beziehungsweise Ladezielen.

Skytech HEMS bleibt weiterhin für die schnelle, lokale und sichere Echtzeitregelung zuständig. Der Energy Pilot gibt nur strategische Rahmenbedingungen vor. Jeder Plan ist strukturiert, zeitlich begrenzt, lokal validiert, nachvollziehbar protokolliert und durch eine Fallback-Strategie abgesichert.

Damit entsteht folgende klare Produktaufteilung:

```text
Skytech Energy Pilot
KI-gestützte Prognose, Planung und strategische Optimierung

Skytech HEMS
Lokale Echtzeitregelung, Leistungsberechnung und Geräteansteuerung
```
