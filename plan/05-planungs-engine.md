# 05 · Planungs-Engine

> Herzstück des Energy Pilot: erstellt, simuliert, validiert und aktualisiert den strategischen Energieplan in einem konfigurierbaren Intervall.

**Status:** Entwurf · **info.md-Bezug:** §4, §8, §11, §12, §20

---

## Ziel & Abgrenzung

- Aus Zuständen, Historie, Prognosen und Zielen einen **strukturierten Plan** erzeugen.
- Planung im **15–60-Minuten-Takt**, kein Sekundenbereich.
- **Nicht** hier: KI-Anbindung im Detail (→ [03](03-ki-api.md)), Übergabe an HEMS (→ [06](06-hems-schnittstelle.md)), Planformat (→ [07](07-datenmodell.md)).

Module: **Planning Engine**, **Simulation Engine**, **Plan Validator**, **Plan Submission**, **Monitoring and Feedback**.

---

## Planungsintervalle (info.md §4)

| Art | Empf. Standard | Zweck |
|---|---|---|
| Vollständige Neuplanung | **60 min** | Alle Daten/Prognosen neu bewerten, Plan für 24–48 h |
| Planaktualisierung | **15 min** | Prüfen, ob Anpassung wegen neuer Messwerte/Abweichungen nötig |
| Ereignisbasiert | bei Trigger | außerplanmäßige Neuberechnung |

Alle Intervalle in der UI konfigurierbar; regulärer Bereich zunächst **15–60 min**.

**Ereignis-Trigger (Auswahl):** E-Auto an-/abgesteckt, Abfahrtszeit/Ziel-SOC geändert, PV stark abweichend, Hausverbrauch unerwartet, Gerät verfügbar/ausgefallen, Batterie an kritischer Grenze, neue Strompreise, Nutzer ändert Strategie/Modus/Gewichtung, Plan ungültig/abgelaufen.

---

## Ablauf einer Planung (info.md §11)

```text
1. Aktuelle HA-Daten erfassen
2. Historische Werte lokal verdichten
3. Externe Prognosen aktualisieren
4. Gerätegrenzen und Benutzerziele laden
5. Bestehenden Plan und Abweichungen analysieren
6. Kandidatenplan durch Optimierungslogik und KI erzeugen
7. Kandidatenplan lokal validieren
8. Plan simulieren und bewerten
9. Ungültigen Plan verwerfen oder korrigieren
10. Gültigen Plan an Skytech HEMS übertragen
11. Annahme/Ablehnung protokollieren
12. Ausführung überwachen
13. Prognose und Realität vergleichen
14. Erkenntnisse für die nächste Planung speichern
```

---

## Rollenverteilung KI ↔ Optimierung (info.md §12)

- **KI:** orchestrieren, Zielkonflikte bewerten, Varianten vergleichen, Plan erstellen & begründen.
- **Lokale Optimierungsengine (langfristig):** deterministische Fahrplan-/Leistungsoptimierung. Die KI ruft sie gezielt auf, interpretiert und erklärt die Ergebnisse.
- Validierung/Simulation laufen **lokal**, unabhängig von der KI.

---

## Planinhalte (Ausgabe, info.md §8)

**Batteriespeicher:** min. SOC, Ziel-SOC, Zielzeit, min./max. Ladeleistung, max. Entladeleistung, Netzladung erlaubt?, reservierte Energie, Lade-/Entladestrategie.

**Flexible Verbraucher (je Gerät):** Freigabe, Betriebsmodus, Priorität, min./max. Leistung, geschützte Mindestleistung, Reserve, frühester Start, spätestes Ende, benötigte Energiemenge, Zielzeitpunkt, Netzbezug erlaubt?.

**Metadaten:** Plan-ID, Erstellungszeit, Gültigkeitsbeginn/-ende, verwendete Prognosen, Provider+Modell, Konfidenz, Begründung, Warnungen, erwartete Auswirkungen, Format-Version.

→ Konkretes JSON-Schema in [07 · Datenmodell](07-datenmodell.md).

---

## Erste Ausbaustufe (info.md §20)

- **Batterie:** Mindest-SOC, Ziel-SOC, Zielzeit, max. Lade-/Entladeleistung, Netzladung erlaubt/verboten.
- **Flexible Verbraucher:** Freigabe, Priorität, min./max. Leistung, geschützte Mindestleistung, Reserve, optionales Zeitfenster.
- **Geräte initial:** Batteriespeicher, Heizstab, Heizlüfter 1, Heizlüfter 2.
- **Später:** Wallbox/E-Auto, Wärmepumpe, dynamische Tarife/Netzladung, mehrere Speicher.

---

## Simulation & Validierung

- **Plan Validator:** Struktur, Wertebereiche, Zeitangaben, harte Grenzen, max. Änderung zwischen zwei Plänen, Ablaufzeit, veraltete/fehlende Daten (→ [08](08-sicherheit.md)).
- **Simulation Engine:** Planvarianten bewerten, erwartete Auswirkungen schätzen (Shadow Mode → [10](10-betriebsmodi.md)).

---

## Möglichkeiten in der Oberfläche

- Aktionen: `create_plan`, `simulate_plan`, `submit_plan`, `cancel_plan`.
- Anzeige: zeitlicher Fahrplan, Sollwerte, Begründungen, verwendete Daten (→ [09](09-benutzeroberflaeche.md)).

---

## Offene Entscheidungen

- [ ] v1 rein KI-basiert, oder gleich mit einfacher regelbasierter Optimierung als Rückfallebene?
- [ ] Wie wird „signifikante Prognoseabweichung" als Trigger quantifiziert (Schwellen)?
- [ ] „Maximale Änderung zwischen zwei Plänen" – konkrete Grenzwerte
- [ ] Simulationsmodell: wie detailliert in v1 (Energiebilanz vs. Speicherverluste)?
- [ ] Mindestkonfidenz, ab der ein Plan überhaupt übergeben wird
- [ ] Planungshorizont-Default (24 vs. 48 h) und zeitliche Auflösung (15 min?)

---

## Aufgaben / Umsetzung

- [ ] Scheduler für Voll-/Update-/Ereignisplanung
- [ ] Kontext-Zusammenstellung (Zustände + Historie + Prognosen + Ziele/Grenzen)
- [ ] Kandidatenerzeugung über KI-Provider (→ [03](03-ki-api.md))
- [ ] Plan Validator (lokal, deterministisch)
- [ ] Simulation Engine (v1 vereinfachte Energiebilanz)
- [ ] Monitoring & Feedback (Prognose vs. Realität → [04](04-prognosen.md), [07](07-datenmodell.md))
- [ ] Übergabe an Plan Submission (→ [06](06-hems-schnittstelle.md))

---

## Bezug zu anderen Plänen

- KI-Erzeugung → [03 · KI / API](03-ki-api.md)
- Prognosen → [04 · Prognosen](04-prognosen.md)
- Übergabe/Status → [06 · HEMS-Schnittstelle](06-hems-schnittstelle.md)
- Planformat → [07 · Datenmodell](07-datenmodell.md)
- Grenzen/Validierung → [08 · Sicherheit](08-sicherheit.md)
- Modi (ob/wie übergeben wird) → [10 · Betriebsmodi](10-betriebsmodi.md)
