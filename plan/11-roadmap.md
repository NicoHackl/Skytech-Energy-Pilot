# 11 · Roadmap, Ausbaustufen & Erfolgskriterien

> Entwicklungsphasen, der Umfang der ersten Ausbaustufe, Erfolgskriterien und ausdrückliche Nicht-Ziele.

**Status:** Entwurf · **info.md-Bezug:** §20, §21, §22, §23

---

## Ziel & Abgrenzung

- Reihenfolge der Umsetzung und messbare Erfolgskriterien.
- Klare Eingrenzung, was v1 **nicht** leisten soll.
- Verknüpft die Inhalte der übrigen Pläne zu einem Zeitstrahl.

---

## Entwicklungsphasen (info.md §21)

### Phase 1 – Daten und Anzeige
Eigenständiges Add-on · Ingress-UI · HA-Verbindung · konfigurierbare Entitätszuordnung · Anzeige aktueller Werte · Prognoseabruf/-anzeige · **keine** Übergabe an HEMS.
→ [01](01-ha-addon-docker.md), [02](02-home-assistant.md), [04](04-prognosen.md), [09](09-benutzeroberflaeche.md)

### Phase 2 – Vorschlagsmodus
OpenAI- & Gemini-Provider · strukturierte Planausgabe · lokale Validierung · verständliche Begründung · manuelle Bestätigung · Planexport · **noch keine** automatische Steuerung.
→ [03](03-ki-api.md), [05](05-planungs-engine.md), [07](07-datenmodell.md), [10](10-betriebsmodi.md)

### Phase 3 – HEMS-Schnittstelle
Versionierte interne API · Übergabe bestätigter Pläne · Annahme/Ablehnung durch HEMS · Statusrückmeldung · Planablauf und Fallback.
→ [06](06-hems-schnittstelle.md)

### Phase 4 – Shadow Mode
Automatische Planerstellung · Simulation · Vergleich Plan/Realität · Kennzahlen und Fehleranalyse · Optimierung der Prognosen.
→ [05](05-planungs-engine.md), [04](04-prognosen.md), [10](10-betriebsmodi.md)

### Phase 5 – Autopilot
Automatische Übernahme gültiger Pläne · ereignisbasierte Neuberechnung · konfigurierbare Vertrauensschwelle · Benachrichtigungen · umfassendes Audit-Log.
→ [08](08-sicherheit.md), [10](10-betriebsmodi.md)

### Phase 6 – Lokale Optimierungsengine
Mathematische Fahrplanoptimierung · Modellierung von Speicherverlusten · Kosten-/Eigenverbrauchsoptimierung · rollierende Planung · KI zur Orchestrierung/Bewertung/Erklärung.
→ [05](05-planungs-engine.md)

---

## Erste Ausbaustufe – Umfang (info.md §20)

**Batterie:** Mindest-SOC · Ziel-SOC · Zielzeit · max. Ladeleistung · max. Entladeleistung · Netzladung erlaubt/verboten.

**Flexible Verbraucher:** Freigabe · Priorität · min./max. Leistung · geschützte Mindestleistung · Reserve · optionales Zeitfenster.

**Geräte initial:** Batteriespeicher · Heizstab · Heizlüfter 1 · Heizlüfter 2.

**Später:** Wallbox & E-Auto · Wärmepumpe · weitere flexible Verbraucher · dynamische Tarife/Netzladung · mehrere Speicher · weitere Erzeugungsanlagen.

---

## Erfolgskriterien (info.md §22)

Der Energy Pilot ist erfolgreich, wenn er gegenüber einer festen/rein reaktiven Strategie **messbare Vorteile** erzielt:

```text
geringerer Netzbezug · geringere Stromkosten · höherer PV-Eigenverbrauch
weniger unnötige Einspeisung · weniger verfehlte Fahrzeug-Ladeziele
ausreichende Warmwasserverfügbarkeit · geringere Batteriebelastung
bessere Nutzung dynamischer Strompreise · wenige manuelle Eingriffe
nachvollziehbare Entscheidungen · sichere Weiterarbeit bei KI-/Internetausfall
```

Der **Shadow Mode** vergleicht diese Werte über mehrere Wochen, bevor der Autopilot aktiviert wird.

---

## Nicht-Ziele der ersten Version (info.md §23)

Die erste Version soll ausdrücklich **nicht**:

- den schnellen Regelkreis von HEMS ersetzen,
- Geräte direkt per Modbus/MQTT regeln,
- ohne lokale Validierung KI-Befehle ausführen,
- alle Energiegeräte sofort unterstützen,
- die vollständige HA-Datenbank an die KI übertragen,
- selbstständig technische Sicherheitsgrenzen verändern,
- ohne nachvollziehbare Protokollierung arbeiten,
- bei Cloud-Ausfall die lokale Anlage blockieren.

---

## Offene Entscheidungen

- [ ] Reihenfolge bestätigen oder anpassen (z. B. Heizstab/Heizlüfter vor Wallbox – wie in info.md)
- [ ] Zeitliche Grobplanung je Phase (Meilensteine)
- [ ] Welche Erfolgskennzahlen werden in v1 schon automatisch erfasst?
- [ ] Definition „mehrere Wochen" Shadow Mode vor Autopilot
- [ ] Welches Gerät dient als erster End-to-End-Durchstich (Vorschlag: Heizstab)?

---

## Aufgaben / Umsetzung

- [ ] Phasen in konkrete Meilensteine/Issues herunterbrechen
- [ ] Kennzahlen-Erfassung definieren (→ [07](07-datenmodell.md))
- [ ] Phase-1-Durchstich planen (Add-on + UI + ein paar reale Werte)
- [ ] Abnahmekriterien je Phase festhalten

---

## Bezug zu anderen Plänen

- Jede Phase verweist oben auf die zugehörigen Detailpläne.
- Modus-Reihenfolge → [10 · Betriebsmodi](10-betriebsmodi.md)
- Umfang/Inhalte der Pläne → [05 · Planungs-Engine](05-planungs-engine.md)
