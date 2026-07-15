# Langfristiger Anpassungsplan für bessere Energy-Pilot-Vorschläge

## Zweck und Status

Dieses Dokument beschreibt das langfristige Zielbild, mit dem die Vorschläge des
Energy Pilot (EP) für das HEMS nachvollziehbarer, stabiler und systemunabhängig
werden sollen. Es ist ein Umsetzungsplan und keine Beschreibung des aktuellen
Funktionsstands. Bei Widersprüchen gelten weiterhin die Projektregeln und die
priorisierten Quellen aus `CLAUDE.md`.

Der Energy Pilot bleibt ein strategischer Planer. Er steuert keine Geräte direkt,
sondern erzeugt zeitlich begrenzte Vorschlagswerte. Das HEMS bleibt für die lokale
Echtzeitregelung, technische Freigaben und die letzte Sicherheitsprüfung
verantwortlich.

## Ziel

Ein Planungslauf soll nicht nur aus Rohwerten einen KI-Vorschlag erzeugen, sondern
aus einer vollständigen, normalisierten und qualitätsbewerteten Momentaufnahme.
Das Ergebnis muss:

- auf unterschiedlichen Anlagen ohne hardcodierte Geräte- oder Entity-Namen
  funktionieren,
- die realen Betriebszustände und technischen Grenzen des HEMS berücksichtigen,
- Energiebedarf, Zeitdruck, PV-Prognose und Datenunsicherheit nachvollziehbar
  gegeneinander abwägen,
- gegenüber vorherigen Vorschlägen stabil bleiben und unnötiges Umschalten
  vermeiden,
- lokal validiert und vor einer Veröffentlichung vom HEMS probegeprüft werden,
- bei fehlenden oder veralteten Daten sicher ausfallen, ohne das HEMS zu blockieren.

## Zielarchitektur

```text
HEMS-Geräte/Capabilities ─┐
HEMS-Laufzeitstatus       ├─> Normalisierung und Datenqualität
HA-Entitäten              ┤              │
PV-/Last-Prognosen        ┘              v
                                  lokale Merkmale
                                         │
                                         v
                                lokaler Basisplan
                                         │
                                         v
                              KI-Strategie/Anpassung
                                         │
                                         v
                         lokale Validierung und Glättung
                                         │
                                         v
                                HEMS-Dry-Run-Prüfung
                                         │
                                         v
                            EP-Vorschlag + Audit-Daten
```

Die KI erhält damit keine unstrukturierten Rohdaten, sondern eine konsistente
Planungsgrundlage. Harte Grenzen, Freigaben und Sicherheitsentscheidungen bleiben
vollständig deterministisch.

## 1. Datenbasis des HEMS erweitern

### 1.1 Geräte und Fähigkeiten

Das HEMS soll Geräte weiterhin als führendes System bereitstellen. Die API muss
Geräteklasse und Fähigkeiten explizit liefern, damit der EP keine Namen wie
`batterie`, `heizstab` oder Präfixe interpretieren muss.

Vorgeschlagener Endpunkt:

```http
GET /api/v1/devices
```

Beispiel:

```json
{
  "api_version": "1.0",
  "devices": [
    {
      "id": "heizstab_ww",
      "label": "Heizstab Warmwasser",
      "class": "thermal_storage",
      "subtype": "variable_heater",
      "output_unit": "W",
      "capabilities": {
        "priority": true,
        "release": true,
        "protected_minimum": true
      },
      "limits": {
        "min_power_w": 0,
        "max_power_w": 3000
      }
    }
  ]
}
```

Benötigte Pflichtinformationen je Gerät:

- stabile Geräte-ID und Anzeigename,
- Geräteklasse und optionaler Untertyp,
- unterstützte Vorschlagsfelder,
- Einheit und Vorzeichenkonvention,
- technische Min-/Max-Werte,
- Kennzeichnung, ob das Gerät binär oder regelbar ist.

### 1.2 Aktueller Planungszustand

Zusätzlich zur Gerätekonfiguration benötigt der EP einen atomaren
Laufzeit-Snapshot. Einzelne, zeitlich versetzte API-Abfragen sollen vermieden
werden.

Vorgeschlagener Endpunkt:

```http
GET /api/v1/planning-state
```

Der Snapshot soll mindestens enthalten:

- `snapshot_at` und HEMS-API-Version,
- HEMS-Modus und globalen Hard-Lockout,
- aktuellen PV-Überschuss, Leistungsdefizit und Netzlimit,
- tatsächliche Leistung und Betriebsart je Gerät,
- aktuelle Priorität und geschützte Mindestleistung,
- manuelle Sperren und technische Freigaben,
- Ergebnis der HEMS-Eignungsprüfung (`eligible`),
- strukturierte Sperrgründe (`blocked_reasons`).

Beispiel:

```json
{
  "snapshot_at": "2026-07-10T12:00:00Z",
  "global": {
    "mode": "automatic",
    "hard_lockout": false,
    "surplus_power_w": 2450,
    "power_deficit_w": 0,
    "grid_import_limit_w": 0
  },
  "devices": {
    "heizstab_ww": {
      "online": true,
      "mode": "ready",
      "manual_lock": false,
      "technical_release": true,
      "eligible": true,
      "actual_power_w": 1800,
      "current_priority": 2,
      "current_protected_minimum_w": 1200,
      "blocked_reasons": []
    }
  }
}
```

### 1.3 Plan vor Veröffentlichung probeprüfen

Langfristig soll das HEMS einen Vorschlag ohne Zustandsänderung prüfen können:

```http
POST /api/v1/plans/validate
```

Antwort:

```json
{
  "accepted": true,
  "conflicts": [],
  "effective_plan": {
    "heizstab_ww": {
      "priority": 2,
      "release": true,
      "protected_minimum_w": 1200
    }
  }
}
```

`effective_plan` zeigt, was das HEMS nach seinen eigenen Regeln tatsächlich
akzeptieren würde. Bei Konflikten veröffentlicht der EP keinen ungeprüften Plan,
sondern korrigiert ihn lokal oder behält den letzten gültigen Vorschlag bei.

## 2. Home-Assistant-Daten dynamisch konfigurieren

HEMS-Geräte werden ausschließlich über das HEMS entdeckt. Zusätzliche
Anlagenwerte aus Home Assistant werden über semantische Rollen konfiguriert. Die
Logik darf niemals von einer konkreten Entity-ID abhängen.

### 2.1 Globale Anlagenwerte

Vorgeschlagene Add-on-Konfiguration:

```yaml
system_inputs:
  - role: pv_power
    entity_id: sensor.pv_gesamtleistung
    unit: W
    sign: positive_generation
    max_age_s: 30
  - role: house_load
    entity_id: sensor.hausverbrauch
    unit: W
    sign: positive_consumption
    max_age_s: 30
  - role: grid_power
    entity_id: sensor.netzleistung
    unit: W
    sign: positive_import
    max_age_s: 30
  - role: battery_power
    entity_id: sensor.batterieleistung
    unit: W
    sign: positive_charge
    max_age_s: 30
  - role: battery_soc
    entity_id: sensor.batterie_soc
    unit: "%"
    max_age_s: 120
  - role: pv_forecast_remaining_today
    entity_id: sensor.pv_prognose_rest_heute
    unit: kWh
    max_age_s: 7200
```

Pflichtrollen für eine Installation sollen vom gewählten Funktionsumfang
abhängen. Optionale Rollen sind beispielsweise Strompreis, Wetter, CO2-Intensität,
Netzbezugsgrenze oder eine externe Lastprognose.

### 2.2 Gerätespezifische Werte

Zusätzliche Werte werden über stabile HEMS-Geräte-IDs zugeordnet:

```yaml
device_inputs:
  - device_id: heizstab_ww
    signal: actual_temperature_c
    source: entity
    entity_id: sensor.warmwasser_temperatur
    unit: "°C"
    required: true
  - device_id: heizstab_ww
    signal: target_temperature_c
    source: entity
    entity_id: input_number.warmwasser_ziel
    unit: "°C"
    required: true
  - device_id: heizstab_ww
    signal: storage_volume_l
    source: constant
    value: 300
    unit: l
    required: false
```

Unterstützte Quellen sollen mindestens `entity`, `constant` und später optional
`hems` umfassen. Jede Zuordnung benötigt Typ, Einheit, Altersgrenze und
Pflichtstatus. Die UI sollte gültige Signale anhand der Geräteklasse anbieten und
vor dem Speichern die Entity sowie deren Einheit prüfen.

### 2.3 Geräteklassenprofile

Die Planungslogik arbeitet mit Klassenprofilen statt Gerätedetails. Anfangs
werden folgende Profile benötigt:

| Geräteklasse | Typische Eingangsdaten | Abgeleitete Planungsgröße |
|---|---|---|
| Batterie | SOC, Kapazität, Ziel/Reserve, Ladegrenze, Wirkungsgrad | fehlende Ladeenergie und nutzbare Ladeleistung |
| Thermischer Speicher | Ist-/Min-/Ziel-/Max-Temperatur, Volumen, Verluste, Deadline | thermischer Energiebedarf und Komfortabstand |
| Binärer Verbraucher | Bedarf/Zustand, Nennleistung, Mindestlaufzeit, Mindestsperrzeit, Deadline | nächste sinnvolle Startmöglichkeit und benötigte Energie |
| Regelbarer Verbraucher | aktueller Sollwert, Min-/Max-Leistung, Energiebedarf, Deadline | zulässiger Leistungsbereich und Zeitdruck |
| Wallbox/E-Auto | SOC oder geladene Energie, Ziel, Kapazität, Abfahrtszeit, Ladegrenzen | fehlende Ladeenergie und spätester Start |
| Wärmepumpe | Temperaturen, Sollbereiche, COP-Kennlinie, Sperr-/Laufzeiten | Wärmebedarf und bevorzugte Betriebsfenster |

Neue Geräte derselben Klasse verwenden dieselbe Logik. Hersteller- oder
anlagenspezifische Werte kommen nur aus Capabilities und Mappings.

## 3. Lokale Vorverarbeitung und Merkmalsbildung

Vor jedem KI-Aufruf berechnet der EP deterministische Merkmale. Die Berechnung
wird getestet und ist im Audit-Log nachvollziehbar.

### 3.1 Datenqualität

Für jedes Eingangssignal werden ermittelt:

- Alter und Aktualität,
- Quelle und Einheit,
- Plausibilität und Wertebereich,
- Vollständigkeit und Ersatzwert,
- Qualitätsstufe `good`, `degraded` oder `invalid`.

Kritische veraltete oder ungültige Daten führen nicht zu einer kreativen
KI-Schätzung. Der EP verwendet dann einen konservativen Fallback oder erzeugt
keinen neuen Vorschlag.

### 3.2 Systemmerkmale

Mindestens lokal berechnen:

- aktuellen und konservativ nutzbaren PV-Überschuss,
- PV-Trend aus 1-/15-/60-Minuten-Werten,
- geglättete Grundlast,
- verbleibende PV-Energie heute und im Planungshorizont,
- verfügbare Energie nach Grundlast und reservierter Batterieladung,
- Prognosefehler und Unsicherheitsabschlag,
- Netzimport/-export und mögliche Grenzverletzungen,
- Abweichung zwischen aktuellem Zustand, letztem Plan und neuem Basisplan.

### 3.3 Gerätemerkmale

Je Gerät mindestens:

- geschätzter verbleibender Energiebedarf,
- früheste und späteste Laufzeit,
- Deadline-Druck,
- Komfort-/Zielabweichung,
- technische Verfügbarkeit,
- aktuelle Laufzeit und Sperrzeit,
- mögliche Leistungsstufen,
- Kosten eines Starts, Stopps oder Planwechsels.

Eine transparente Dringlichkeit kann beispielsweise so gebildet werden:

```text
urgency =
    0.40 * deadline_pressure
  + 0.30 * normalized_energy_need
  + 0.20 * comfort_or_target_gap
  + 0.10 * availability_risk
```

Gewichte sind konfigurierbar. Die KI darf diese Bewertung strategisch
kommentieren, aber keine technischen Grenzen überschreiben.

## 4. Lokalen Basisplan erzeugen

Vor der KI wird ein einfacher, vollständig deterministischer Basisplan erzeugt:

1. technisch gesperrte oder ungeeignete Geräte ausschließen,
2. Pflichtbedarfe und Deadlines priorisieren,
3. konservativ verfügbare Energie auf Geräte verteilen,
4. Mindestlaufzeiten, Sperrzeiten und Leistungsgrenzen beachten,
5. Batterie- und Netzrestriktionen berücksichtigen,
6. Änderungen gegenüber dem letzten Plan minimieren.

Der Basisplan ist gleichzeitig:

- funktionsfähiger Fallback bei KI-Ausfall,
- Referenz, an der KI-Änderungen messbar werden,
- Grundlage für Tests und spätere Optimierungsverfahren,
- Schutz vor stark schwankenden oder unvollständigen KI-Ergebnissen.

In einer späteren Ausbaustufe kann der heuristische Basisplan durch eine
15-Minuten-Zeitreihenoptimierung beziehungsweise Model Predictive Control (MPC)
ersetzt werden. Die KI bleibt auch dann für Strategie und erklärbare Gewichtung
zuständig, nicht für harte Regelung.

## 5. Rolle des ersten KI-Aufrufs ändern

Die KI soll nicht mehr allein aus verdichteten Rohwerten sämtliche
Vorschlagswerte erfinden. Sie erhält:

- normalisierte System- und Gerätemerkmale,
- Datenqualität und Prognoseunsicherheit,
- HEMS-Laufzeitstatus und strukturierte Sperrgründe,
- lokalen Basisplan,
- vorherigen gültigen EP-Plan,
- Zielgewichte und Betriebs-/Steuermodus,
- Feedback aus früheren Planungsläufen.

Die strukturierte Antwort enthält bevorzugt:

```json
{
  "strategy": "use_expected_pv_window",
  "adjustments": {
    "heizstab_ww": {
      "priority_delta": 1,
      "protected_minimum_delta_w": 300,
      "release_recommendation": "keep",
      "reason_codes": ["deadline_pressure", "pv_window_available"]
    }
  },
  "confidence": 0.86,
  "warnings": []
}
```

Die KI liefert damit Strategie und begrenzte Anpassungen am Basisplan. Der EP
berechnet daraus den finalen Kandidaten. Freitextbegründungen bleiben rein
erklärend und werden nie als Steuerbefehl ausgewertet.

## 6. Nachgelagerte lokale Logik

Nach dem KI-Aufruf wird der Kandidat deterministisch verarbeitet:

1. Antwortschema und Vollständigkeit prüfen.
2. Harte HEMS- und Gerätebegrenzungen anwenden.
3. Unbekannte technische Grenzen als nicht freigegeben behandeln.
4. Gesamtleistungs- und Energiebudget über alle Geräte prüfen.
5. Prioritäten normalisieren und Gleichstände stabil auflösen.
6. Delta-Limits und Hysterese gegenüber dem letzten Plan anwenden.
7. Mindesthaltezeiten für Freigabe- und Prioritätsänderungen prüfen.
8. Ablaufzeit und Daten-Snapshot-ID setzen.
9. Kandidat per HEMS-Dry-Run prüfen.
10. Nur einen akzeptierten Plan veröffentlichen und vollständig auditieren.

Empfohlene Startwerte, jeweils konfigurierbar:

- maximale Leistungsänderung pro Lauf: `±20 %`,
- maximale Änderung eines Batterie-Vorschlags: `±10 %`,
- Freigabewechsel erst nach zwei konsistenten Planungsläufen,
- Prioritätswechsel nur bei materiell unterschiedlicher Dringlichkeit,
- kein neuer Plan bei ungültigen kritischen Messwerten,
- jeder Vorschlag läuft spätestens mit dem nächsten Planungsintervall ab.

## 7. Optionaler zweiter KI-Aufruf als Kritiker

Ein zweiter KI-Aufruf ist sinnvoll, aber nicht als alleiniger Sicherheitsfilter.
Er wird nur bei erhöhtem Risiko ausgeführt, beispielsweise bei:

- großen Abweichungen vom Basis- oder vorherigen Plan,
- Wechsel einer Gerätefreigabe,
- vielen lokalen Klemmungen,
- schlechter Datenqualität,
- Widerspruch zwischen Prognose und aktueller Entwicklung,
- Konflikten aus dem HEMS-Dry-Run.

Der Kritiker erhält den Eingangskontext, Basisplan, vorgeschlagenen Kandidaten und
alle lokalen Prüfergebnisse. Seine Ausgabe bleibt klein und strukturiert:

```json
{
  "verdict": "revise",
  "issues": [
    {
      "code": "forecast_risk",
      "device_id": "heizstab_ww",
      "severity": "medium"
    }
  ],
  "patches": {
    "heizstab_ww": {
      "protected_minimum_delta_w": -300
    }
  }
}
```

Patches durchlaufen erneut die vollständige lokale Validierung und den
HEMS-Dry-Run. Bei Fehler, Timeout oder unbrauchbarer Antwort gilt der bereits
lokal validierte konservative Kandidat. Ein positives KI-Urteil kann niemals eine
lokale oder HEMS-seitige Ablehnung aufheben.

## 8. Feedback-Schleife

Der EP speichert pro Planungslauf keine unnötigen Rohdaten, aber ausreichend
verdichtete Ergebnisdaten:

- Prognose gegenüber tatsächlicher PV-Energie,
- geplanter gegenüber tatsächlich nutzbarer Leistung,
- EP-Vorschlag gegenüber HEMS-Effektivergebnis,
- Ziel-/Komfortverletzungen,
- unnötige Starts, Stopps und Prioritätswechsel,
- Netzbezug/-export während des Vorschlagsfensters,
- Ablehnungs-, Klemmungs- und Sperrgründe.

Daraus werden lokal Korrekturfaktoren abgeleitet, zum Beispiel ein
prognoseabhängiger Sicherheitsabschlag oder anlagenspezifische Grundlast. Diese
Korrekturen sind begrenzt, versioniert, rücksetzbar und im UI sichtbar. Sie
ersetzen keine technischen Grenzwerte.

## 9. Konfiguration und Installationswechsel

Bei einer Neuinstallation auf einem anderen System sollen nur folgende Schritte
nötig sein:

1. HEMS-Verbindung einrichten und Geräte synchronisieren.
2. Automatisch erkannte Geräteklassen und Capabilities bestätigen.
3. erforderliche HA-Rollen und Gerätesignale über Entity-Auswahl zuordnen.
4. Einheiten, Vorzeichen und Datenalter automatisch prüfen lassen.
5. optional Zielgewichte und konservative Standardwerte anpassen.
6. einen Diagnose- und Dry-Run ohne Veröffentlichung durchführen.

Keine Planungsregel darf konkrete Entity-IDs, Anzeigenamen oder eine feste Anzahl
von Geräten enthalten. Alle gespeicherten Mappings werden gegen stabile
HEMS-Geräte-IDs und semantische Signalnamen geführt.

Die Konfiguration benötigt außerdem:

- exportierbare/importierbare Profile,
- Schema-Versionen und Migrationen,
- Anzeige fehlender Pflichtsignale,
- Test-Schaltflächen pro Entity-Mapping,
- Status `bereit`, `eingeschränkt` oder `nicht planbar` je Gerät,
- nachvollziehbare Defaults pro Geräteklasse.

## 10. Umsetzungsreihenfolge

### Phase 1 – Daten und Transparenz

1. Gemeinsames versioniertes Datenmodell für Geräte, Capabilities und
   Laufzeitstatus definieren.
2. HEMS-Endpoints `/api/v1/devices` und `/api/v1/planning-state` umsetzen.
3. EP-Collector um Zeitstempel, Quellen, Qualitätsstatus und HEMS-Status erweitern.
4. Konfigurierbare HA-Rollen und gerätespezifische Signal-Mappings ergänzen.
5. Audit-Ausgabe um normalisierte Eingangsdaten und Sperrgründe erweitern.

### Phase 2 – Deterministische Planung

6. Klassenprofile und lokale Merkmalsberechnung implementieren.
7. Heuristischen Basisplan mit Energie-, Leistungs- und Deadline-Prüfung bauen.
8. Stabilisierung mit Delta-Limits, Hysterese und Mindesthaltezeiten ergänzen.
9. Regressionstests mit festen Anlagen-Szenarien und fehlerhaften Daten erstellen.

### Phase 3 – KI gezielt einsetzen

10. Prompt und Schema auf Strategie plus begrenzte Anpassungen umstellen.
11. Vorherigen Plan, Datenqualität und Basisplan in den KI-Kontext aufnehmen.
12. Optionalen risikobasierten Kritiker-Aufruf ergänzen.
13. Vergleichstests `Basisplan` gegen `Basisplan + KI` einführen.

### Phase 4 – HEMS-Abstimmung und Lernen

14. HEMS-Endpunkt `/api/v1/plans/validate` implementieren und im EP erzwingen.
15. Feedback-Kennzahlen und begrenzte lokale Korrekturfaktoren einführen.
16. Shadow-Mode über mehrere Wochen auswerten, bevor automatische Übernahme
    freigegeben wird.
17. Bei Bedarf heuristischen Basisplan durch eine zeitdiskrete MPC-Optimierung
    ergänzen.

## 11. Abnahmekriterien

Die Erweiterung gilt als erfolgreich, wenn:

- dieselbe EP-Version ohne Codeänderung auf Anlagen mit anderen Entity- und
  Gerätenamen eingerichtet werden kann,
- fehlende oder veraltete Pflichtdaten klar erkannt werden und keinen aggressiven
  neuen Vorschlag auslösen,
- kein veröffentlichter Vorschlag technische HEMS-Grenzen verletzt,
- wiederholte Läufe mit nahezu gleichen Daten keine unnötigen Freigabe- oder
  Prioritätswechsel erzeugen,
- jeder Vorschlagswert auf Eingangsdaten, Basisplan, KI-Anpassung und lokale
  Korrekturen zurückgeführt werden kann,
- der lokale Basisplan bei KI-Ausfall weiterhin einen sicheren Vorschlag oder eine
  begründete Nicht-Planung liefert,
- die KI-Variante in Shadow-Tests messbar bessere Zielerfüllung als der Basisplan
  erreicht, ohne mehr Grenzverletzungen oder Schaltvorgänge zu verursachen.

Empfohlene Vergleichskennzahlen:

- Anteil genutzter PV-Energie,
- zusätzlicher Netzbezug durch planbare Verbraucher,
- Ziel-/Deadline-Erfüllung je Geräteklasse,
- Anzahl Freigabe- und Prioritätswechsel pro Tag,
- Anteil lokal geklemmter KI-Werte,
- HEMS-Dry-Run-Ablehnungsquote,
- Planstabilität zwischen aufeinanderfolgenden Läufen,
- Prognosefehler und Qualität der verwendeten Eingangsdaten.

## Kurzfassung der wichtigsten Architekturentscheidungen

- Das HEMS liefert Geräte, Fähigkeiten, aktuelle Betriebszustände und die letzte
  technische Planprüfung über versionierte APIs.
- Home Assistant liefert frei zuordenbare Anlagen- und Gerätesignale über
  semantische Config-Felder.
- Der EP normalisiert die Daten, bewertet ihre Qualität und berechnet zuerst einen
  lokalen Basisplan.
- Die erste KI optimiert Strategie und begrenzte Planänderungen; sie bestimmt keine
  harten Grenzen.
- Ein optionaler zweiter KI-Aufruf kritisiert nur risikoreiche Kandidaten und kann
  keine lokale Ablehnung überstimmen.
- Lokale Validierung, Glättung, Ablaufzeit und HEMS-Dry-Run entscheiden, was
  veröffentlicht wird.
- Geräteklassen und Capabilities halten das System auch bei anderen Geräten und
  Entity-Namen vollständig konfigurierbar.
