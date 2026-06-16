# 06 — Prognosen (Forecast Manager)

## Zweck
Stellt strukturierte Prognosen für die Planung bereit. Externe Daten werden durch EP/HA-Integrationen **strukturiert abgerufen** — das Sprachmodell recherchiert nichts selbst im Internet (info.md §6.3).

## Prognosearten (V1-Fokus, D-018)
```
Forecast Manager
├── PV Forecast               # PV-Erzeugungsprognose  ← V1: einzige externe Quelle
├── Load Forecast             # Lastprognose aus Historie/Lastprofilen (intern)
├── Weather Forecast          # später optional (in V1 NICHT benötigt)
└── Electricity Price Forecast# VORERST RAUS – kein dynamischer Tarif beim User
```

## Quellen (D-006, D-018)
- **PV-Prognose:** der User pflegt die **bestehenden HA-Sensoren** in der **Addon-Config**.
  - **WICHTIG:** je Typ **mehrere Sensoren** konfigurierbar (mehrere PV-Ausrichtungen) → EP **summiert** sie.
  - Vier Werte: **Energie aktuelle Stunde, Energie nächste Stunde, Energie verbleibend heute, Energie morgen**.
  - **Jeder Wert liegt direkt im State eines eigenen Sensors** (kein Attribut, D-026) → in der Addon-Config also je Wert (und je Ausrichtung) ein Entitätsname.
- **Strompreis:** in V1 **weggelassen** (kein dynamischer Tarif). Architektur so halten, dass eine Preisquelle später ohne Umbau ergänzbar ist.
- **Wetter:** in V1 **nicht** benötigt (PV-Prognose deckt die Erzeugungsgrundlage ab).
- **Lastprognose** primär **intern** aus verdichteter Historie (typische Profile nach Wochentag/Uhrzeit, basierend auf 60-min-agg, siehe [05](05-daten-und-speicherung.md)).

## Verarbeitung
- Prognosen werden normalisiert (Zeitraster, Einheiten) und in `forecasts` gespeichert.
- **Prognosefehler** werden laufend gegen Realität gemessen (Monitoring/Feedback) und für künftige Planungen genutzt.
- Qualität/Aktualität der Quellen wird bewertet und in der UI angezeigt.

## Nutzung in der Planung
- Eingabe für Planning Engine + Simulation (Horizont 24–48 h).
- Bei fehlenden/veralteten Prognosen: Konfidenz senken, Warnung erzeugen, ggf. konservative Strategie.

## UI-Anzeige (siehe [09](09-ui-ingress.md))
PV-Prognose, Lastprognose, Wetter, Strompreise, Prognoseabweichungen, Datenquellen-Qualität.

## Offene Punkte
- Mindestqualität, ab der ein Plan überhaupt erstellt wird.

> Geklärt (D-026): 4 PV-Werte je als eigener Sensor-State (kein Attribut), mehrere Sensoren pro Ausrichtung summierbar.
