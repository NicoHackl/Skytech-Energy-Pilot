# 04 · Prognosen (Forecast Manager)

> Beschaffung und Aufbereitung externer Prognosen sowie die lokale Verdichtung historischer Daten als Grundlage der Planung.

**Status:** Entwurf · **info.md-Bezug:** §6.2, §6.3, §17

---

## Ziel & Abgrenzung

- Externe Prognosen **strukturiert** abrufen und der Planung bereitstellen.
- Historische HA-Daten lokal **verdichten** (nicht roh an die KI geben).
- **Nicht** hier: das Lesen der Live-Entitäten (→ [02](02-home-assistant.md)).

> Grundsatz: Das Sprachmodell soll Werte **nicht selbst** unkontrolliert im Internet recherchieren. Prognosen kommen über die App oder vorhandene HA-Integrationen.

---

## Verwendete Services / Technologie

Modul **Forecast Manager** mit Untermodulen:

- **PV Forecast** – PV-Erzeugungsprognose
- **Load Forecast** – Lastprognose (aus Historie abgeleitet)
- **Weather Forecast** – Wetter, Bewölkung, Außentemperatur, Sonnauf-/-untergang
- **Electricity Price Forecast** – stündliche Strompreise, Netzentgelte/Tarifbestandteile

---

## Datenquellen

**Externe Prognosen (info.md §6.3):**

| Bereich | Werte | Mögliche Quelle (zu entscheiden) |
|---|---|---|
| PV | PV-Erzeugungsprognose | Forecast.Solar, Solcast, … |
| Wetter | Bewölkung, Außentemperatur, Sonnenauf-/-untergang | met.no, DWD, OpenWeather, HA-Wetterintegration |
| Preise | stündliche Strompreise, Netzentgelte, Tarifbestandteile | Nordpool/EPEX, Tibber, aWATTar, … |
| Einspeisung | optionale Einspeiseprognosen | je nach Tarif/Quelle |

**Historische Daten – lokal verdichtet (info.md §6.2):**

- 15-Minuten-Mittelwerte
- Verbrauch der letzten 24 Stunden
- typische Lastprofile nach Wochentag/Uhrzeit
- PV-Ertrag vergleichbarer Tage
- bisherige Prognosefehler
- Speicher-SOC-Verlauf
- Laufzeiten flexibler Verbraucher
- tatsächlich benötigte Energiemengen
- erreichte/verfehlte Ladeziele

---

## Datenfluss

- **Hinein:** externe APIs / HA-Integrationen (Wetter, Preis, PV); HA-Historie für die Verdichtung.
- **Hinaus:** aufbereitete Prognosen an die Planungs-Engine ([05](05-planungs-engine.md)) und – verdichtet – an die KI ([03](03-ki-api.md)); Prognose-Sensoren nach HA ([02](02-home-assistant.md)); Speicherung in der DB ([07](07-datenmodell.md)).
- **Feedback-Schleife:** Prognose vs. Realität wird gemessen und für künftige Planungen gespeichert (Prognosefehler).

---

## Möglichkeiten in der Oberfläche (Prognosen-View)

- PV-Prognose, Lastprognose, Wetter, Strompreise
- Prognoseabweichungen (Plan vs. Realität)
- Qualität der Datenquellen

---

## Offene Entscheidungen

- [ ] Konkrete PV-Prognosequelle (Forecast.Solar/Solcast/…) und ob direkt-API oder über HA-Integration
- [ ] Wetterquelle und Preise/Tarifquelle festlegen (regional: Österreich/Deutschland?)
- [ ] Vorhandene HA-Integrationen wiederverwenden vs. eigene Abrufe
- [ ] Aktualisierungsintervalle je Prognoseart (z. B. Preise stündlich, PV mehrmals täglich)
- [ ] Verfahren der Lastprognose (einfacher Mittelwert nach Wochentag/Uhrzeit vs. lernend)
- [ ] Caching/Fehlerbehandlung bei nicht erreichbaren Prognosediensten

---

## Aufgaben / Umsetzung

- [ ] Forecast-Manager-Grundgerüst + einheitliches Prognose-Datenmodell
- [ ] History Aggregator (15-Min-Mittel, Tagesprofile)
- [ ] Adapter je Prognoseart (PV/Wetter/Preis)
- [ ] Prognose-Persistenz + Prognosefehler-Tracking (→ [07](07-datenmodell.md))
- [ ] Prognose-Sensoren nach HA veröffentlichen
- [ ] Service `recalculate_forecast` verdrahten

---

## Bezug zu anderen Plänen

- Live-Daten/Verdichtungsquelle → [02 · Home Assistant](02-home-assistant.md)
- Nutzung in der Planung → [05 · Planungs-Engine](05-planungs-engine.md)
- Verdichtete Eingaben an die KI → [03 · KI / API](03-ki-api.md)
- Speicherung → [07 · Datenmodell](07-datenmodell.md)
