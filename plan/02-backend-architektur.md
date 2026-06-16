# 02 — Backend-Architektur

## Zweck
Definiert die internen Module, den Datenfluss und das Laufzeitmodell des EP-Backends.

## Tech-Stack
- **Python 3.11**, **aiohttp** (async Webserver + Ingress), **SQLite** (lokale Datenhaltung).
- Async Scheduler für periodische Planung + Eventbus für ereignisbasierte Neuplanung.
- Bewusst kompatibel zum HEMS-Stack (gleiche Patterns, gemeinsame Wartbarkeit).

## Modulübersicht (info.md §17)
```
Skytech Energy Pilot
├── Home Assistant Connector      # REST + WebSocket, Auth via SUPERVISOR_TOKEN
├── Skytech HEMS Connector        # versionierte API, Planübergabe, Statusabholung
├── Entity Allowlist              # nur freigegebene Entitäten lesbar
├── State Collector               # liest Live-Werte, Ringpuffer
├── History Aggregator            # Verdichtung, gleitende Mittelwerte (siehe unten)
├── Forecast Manager              # PV / Last / Wetter / Strompreis (siehe 06)
├── Device and Constraint Model   # harte Grenzen, Geräteeigenschaften
├── User Objective Manager        # weiche Ziele + Gewichtungen
├── AI Provider Interface         # OpenAI / Gemini (siehe 04)
├── Planning Engine               # Kandidatenplan (siehe 07)
├── Simulation Engine             # Plan simulieren/bewerten
├── Plan Validator                # Schema + harte Grenzen (siehe 08)
├── Plan Submission               # an HEMS übertragen
├── Monitoring and Feedback       # Plan vs. Realität
├── Audit Log                     # vollständige Protokollierung
├── Database                      # SQLite (siehe 05)
└── Ingress Web UI                # SPA (siehe 09)
```

## Laufzeitmodell / Scheduler
- **Vollständige Neuplanung:** Default alle 60 min (konfigurierbar 15–60 min).
- **Planaktualisierung:** Default alle 15 min — prüft, ob bestehender Plan angepasst werden muss.
- **Ereignisbasierte Neuberechnung:** ausgelöst durch E-Auto an/ab, geänderte Abfahrtszeit/Ziel-SOC, starke PV-/Last-Abweichung, Gerät verfügbar/ausgefallen, kritischer Batterie-SOC, neue Strompreise, geänderte Strategie, abgelaufener Plan.
- Alle Intervalle in der UI konfigurierbar.

## State Collector + History Aggregator (D-001, D-003)
- EP erhält **Live-Werte** aus HA und bildet selbst die Verdichtung (siehe [../user-fragen.md](../user-fragen.md)).
- **Drei feste gleitende Fenster parallel: 1 / 15 / 60 min.** Über die Mittelwerte erfolgt **keine** Ereigniserkennung/-kopplung.
- **Gemittelt:** PV-Leistung, Hausverbrauch, Netzbezug/-einspeisung, Batterieleistung, Ist-Leistungen.
- **Nicht gemittelt** (letzter gültiger Wert): SOC-Werte, Temperaturen, Abfahrtszeit, Verbindungs-/Verfügbarkeitszustände, Betriebsmodi.
- Langzeitprognose greift nur auf die **60-min**-Verdichtung zu (D-012).
- Veraltete Messwerte werden erkannt und abgelehnt (info.md §13).

## Planungsablauf (info.md §11)
1. Aktuelle HA-Daten erfassen → 2. Historie verdichten → 3. Prognosen aktualisieren → 4. Grenzen & Ziele laden → 5. Bestehenden Plan + Abweichungen analysieren → 6. Kandidatenplan (Optimierung + KI) → 7. lokal validieren → 8. simulieren/bewerten → 9. ungültigen verwerfen/korrigieren → 10. gültigen an HEMS übertragen → 11. Annahme/Ablehnung protokollieren → 12. Ausführung überwachen → 13. Prognose vs. Realität → 14. Erkenntnisse speichern.

## Fehler-/Ausfallverhalten
- Cloud-/KI-Ausfall darf EP-Backend nicht crashen lassen; Planung pausiert sauber, HEMS läuft lokal weiter.
- Bei Limit-Erreichung (Kosten/API) Wechsel in lokalen/passiven Modus.

## Offene Punkte
- Threadsafety/Concurrency-Modell zwischen Scheduler und Event-Trigger.
