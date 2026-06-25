# 07 — Planning & Simulation Engine

## Zweck
Erzeugt den Kandidatenplan aus Zustand, Historie, Prognosen, Grenzen und Zielen; simuliert und bewertet ihn. Ausgabe ist ein strukturierter, zeitlich begrenzter Energieplan.

## Ziele: hart vs. weich (info.md §7)
- **Harte Grenzen** (nie durch KI änderbar/verletzbar): min/max Batterie-SOC, max. Lade-/Entladeleistung, max. Wallboxleistung, min. Ladeleistung, Phasenstrom, max. Warmwassertemperatur, Mindestlauf-/-auszeiten, max. Änderung pro Regelschritt, Netzanschlussleistung, verbindliches Fahrzeug-Ladeziel, Geräteverfügbarkeit, Freigaben. Lokal gespeichert, durch HEMS/Validator garantiert.
- **Weiche Ziele** (gewichtbar, abwägbar): Netzbezug/-einspeisung/Kosten minimieren, PV-Eigenverbrauch maximieren, Batterieschonung, WW/E-Auto aus PV, Abendreserve, Komfort.

Beispielgewichtung (info.md §7): Versorgungssicherheit 100 %, E-Auto-Ziel 100 %, WW-Komfort 100 %, Netzbezug 90 %, Kosten 85 %, Eigenverbrauch 80 %, Einspeisung 70 %, Batterieschonung 50 %.

> **D-011:** Diese Gewichte sind in der **Addon-Config** pflegbar und werden initial mit den info.md-Werten vorbelegt.

> **Steuermodus-Bezug (D-009, [12](12-steuermodi.md)):** Im **Hybrid**-Modus werden vom User fixierte Werte zu **zusätzlichen harten Vorgaben** — die KI plant darum herum und darf sie nicht ändern. Im **Automatisch**-Modus haben KI-Werte Vorrang vor User-Eingaben; im **Manuell**-Modus erzeugt EP keine wirksamen Vorgaben.

## Planinhalt (info.md §8 / §9)
- **Batterie:** min/Ziel-SOC, Zielzeit, min/max Ladeleistung, max Entladeleistung, Netzladung erlaubt?, Abendreserve.
- **Flexible Verbraucher (je Gerät):** Freigabe, Modus, Priorität, min/max Leistung, geschützte Mindestleistung, Reserve, frühester Start/spätestes Ende, benötigte Energie, Zielzeit, Netzbezug erlaubt?
- **Metadaten:** Plan-ID, Zeiten, verwendete Prognosen, Provider/Modell, Konfidenz, Begründung, Warnungen, erwartete Auswirkungen, Schema-Version.

## Erste Ausbaustufe (info.md §20, präzisiert durch D-016/D-017/D-018)
Geräte initial: **Batteriespeicher (E3DC), Heizstab, Heizlüfter 1, Heizlüfter 2**. Später Wallbox/E-Auto, Wärmepumpe, dynamische Tarife.

- **Batterie (D-016):** aktuell **immer Priorität 1 und immer freigegeben**. **Kein** min/max-SOC, **keine** Entladung in der Berechnung (EP regelt nur PV-**Überschuss**). Einziger relevanter Grenzwert: **maximale Ladeleistung**. (Ziel-SOC/Netzladung/Entladung = spätere Ausbaustufe.)
- **Heizstab:** Freigabe, Priorität, max. Leistung, max. Wassertemperatur als Grenze.
- **Heizlüfter 1 & 2 (D-017):** **binäre** Lasten mit **fester 1500 W** (analog HEMS `BinaryDevice`) → nur **Freigabe**/Priorität, keine variable Leistung. Ihre **Lastgröße** liest EP aus `ems_<name>_leistung_w` (D-031).
- **Strompreis (D-018):** in V1 nicht berücksichtigt; weiche Ziele ohne Preiskomponente.

> **EP-Output (Read/Write-Domäne, D-029/D-030):** EP **liest** technische Grenzen/Freigaben/Ist-Leistung aus `ems_*` und **schreibt** in Phase 1 nur `ep_<name>_prio_vorschlag`, `ep_<name>_geschutzte_mindestleistung_w_vorschlag`/`_a_vorschlag` und `ep_<name>_freigabe_vorschlag`. Der reichere Planinhalt oben (Ziel-SOC, Reserven, Zeitfenster …) bleibt internes Planungs-/Ebene-2-Zielbild, **nicht** der V1-Schreibvertrag.

## Erzeugung des Kandidatenplans
- **V1 (D-008): KI erzeugt strukturierten Plan über Tools** (siehe [04](04-ki-provider.md)), gegen harte Grenzen geklemmt. Ergebnis sind **reine Vorschlagswerte** — sichtbar in UI, HA-Sensoren (`sensor.ep_*`) und Logging, aber **keine Übernahme** durch HEMS.
- **Kontext (D-042/D-043):** verdichteter Zustand, PV-Prognose, **Wetterprognose** (`weather.llm_detail`: `compact`/`full`), harte Grenzen, Ziele (Datenminimum, Iron Rule 7).
- **Editierbarer Prompt (D-043):** Die KI-Instruktion ist in der EP-Oberfläche (Plan-Tab) editierbar und in der `config`-Tabelle persistiert (überdauert Neustart/Update). Der `Daten:`-Block wird immer code-seitig angehängt; das Antwort-Schema bleibt code-kontrolliert und der Validator erzwingt die harten Grenzen unabhängig vom Prompt (Iron Rules 5/6).
- Zielbild (Phase 6): deterministische **lokale Optimierungsengine** (mathematische Fahrplanoptimierung, Speicherverluste, Kosten/Eigenverbrauch, rollierende Planung); KI orchestriert/bewertet/erklärt.

## Simulation
- Kandidatenplan gegen Prognosen durchrechnen, erwartete PV/Netz/Kosten/SOC-Verlauf ableiten.
- Mehrere Varianten vergleichbar machen; Bewertung anhand Zielgewichtung.
- Shadow Mode: Pläne automatisch erzeugen + simulieren, mit Realität vergleichen (kein Submit).

## Übergabe
- Nur **validierte** Pläne (siehe [08](08-validierung-sicherheit.md)) gehen je nach Betriebsmodus an HEMS (siehe [03](03-api-schnittstelle-hems.md)).

## Offene Punkte
- Wie viele Planvarianten pro Lauf (Kosten vs. Qualität, v.a. unter Gemini-Free-Rate-Limit)?
- Granularität des Fahrplans (15-min-Slots über 24–48 h?). Datenhaltung ist auf 1/15/60 min ausgelegt; Langzeit nutzt 60 min.
- Steuermodus global vs. pro Gerät (siehe [12](12-steuermodi.md)).
