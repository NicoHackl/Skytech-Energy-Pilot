# 08 · Sicherheit, Grenzen, Datenschutz & Kosten

> Harte Grenzen, weiche Ziele, das Sicherheitskonzept sowie Datenschutz- und Kostenkontrolle. Querschnitt über alle Module.

**Status:** Entwurf · **info.md-Bezug:** §7, §13, §19

---

## Ziel & Abgrenzung

- Sicherstellen, dass die KI **nie** technische/sicherheitsrelevante Grenzen verletzt.
- Strukturierte, validierte, protokollierte Abläufe; Schutz von Schlüsseln und Daten.
- **Nicht** hier: die Geräteregelung selbst (HEMS), aber die Grenzen werden lokal garantiert.

Beteiligte Module: **Plan Validator**, **Audit Log**, **Entity Allowlist**, **Device and Constraint Model**, **User Objective Manager**.

---

## Harte Grenzen (info.md §7)

Dürfen **niemals** durch die KI verändert oder verletzt werden – lokal gespeichert, durch HEMS bzw. lokalen Validator garantiert:

```text
min./max. Batterie-SOC · max. Lade-/Entladeleistung Speicher
max. Wallboxleistung · min. technisch mögliche Ladeleistung
zulässige Stromstärke je Phase · max. Warmwassertemperatur
Mindestlaufzeiten · Mindestauszeiten · max. Änderung pro Regelschritt
zulässige Netzanschlussleistung · verbindliches Fahrzeug-Ladeziel
Geräteverfügbarkeit · Benutzer-/Sicherheitsfreigaben
```

## Weiche Ziele & Gewichtung (info.md §7)

Gegeneinander abwägbar, mit Gewichten. Beispiel:

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

→ Gewichte sind in der UI einstellbar (→ [09](09-benutzeroberflaeche.md)).

---

## Sicherheitskonzept – verbindliche Regeln (info.md §13)

- Zugriff nur auf **freigegebene** Entitäten und Funktionen (Allowlist).
- **Keine** direkte Ansteuerung von Modbus/MQTT/Geräte-APIs durch das Sprachmodell.
- Strukturierte Ein-/Ausgaben; **JSON-Schema-Validierung** jedes Plans.
- Prüfung **aller** technischen Grenzen; Ablaufzeit für jeden Plan.
- Ablehnung **veralteter** Messwerte; Erkennung **fehlender** Daten.
- **Maximale Änderung** zwischen zwei Plänen begrenzen.
- Optional notwendige **Benutzerfreigabe**; vollständiges **Audit-Log**.
- **Not-Aus** und manueller Modus.
- Lokaler Betrieb von HEMS bei Cloud-Ausfall; **kein** durch KI erzeugter Code wird ausgeführt.
- **Kein API-Schlüssel** in Logs oder Entitäten; konfigurierbares Datenminimum für externe KI.

---

## Verhalten bei Ausfall (info.md §13)

1. HEMS nutzt letzten gültigen Plan bis zum Ablauf.
2. Danach lokale Standardstrategie.
3. Kritische harte Grenzen bleiben aktiv.
4. Nutzer wird informiert.
5. Nach Wiederherstellung neuer Plan.
6. Abgelaufener Plan **nie** stillschweigend unbegrenzt weiter.

(Siehe auch [06 · HEMS-Schnittstelle](06-hems-schnittstelle.md).)

---

## Datenschutz & Kostenkontrolle (info.md §19)

- Externe KI erhält **nur** für die Planung notwendige Daten.
- Keine persönlichen Namen / unnötigen Entitäten.
- Historie vor Übertragung **verdichtet** (→ [04](04-prognosen.md)).
- API-Schlüssel **geschützt** gespeichert.
- Jede Anfrage protokolliert: Anbieter, Modell, Zeitpunkt, geschätzter Verbrauch.
- **Tages-/Monatslimits** konfigurierbar; bei Erreichen → lokaler/passiver Modus.
- Nutzer kann einsehen, **welche Daten** übermittelt wurden.
- Sichere Deaktivierung / einfache lokale Strategie auch **ohne** KI.

---

## Möglichkeiten in der Oberfläche

- Pflege harter Grenzen und Gewichtung weicher Ziele.
- Not-Aus / manueller Modus, Mindestkonfidenz.
- Datenfreigabe-Umfang, Kostenlimits, Einsicht in übertragene Daten und API-Nutzung.

---

## Offene Entscheidungen

- [ ] Wo „leben" die harten Grenzen primär – im Pilot, in HEMS, oder doppelt (empfohlen: doppelt)?
- [ ] Konkrete Schwellen: max. Messwert-Alter, max. Planänderung, Mindestkonfidenz
- [ ] Secret-Speicher: HA-Add-on-Secrets vs. eigener verschlüsselter Store
- [ ] Default-Datenminimum (welche Felder gehen standardmäßig an die KI?)
- [ ] Standard-Tages-/Monats-Kostenlimit und Reaktion (passiv vs. lokale Strategie)
- [ ] Umfang des Audit-Logs (welche Ereignisse, Aufbewahrung)

---

## Aufgaben / Umsetzung

- [ ] Constraint-Modell + Speicherung der harten Grenzen
- [ ] Plan Validator (Schema + Wertebereiche + Grenzen + Zeit + Änderungslimit)
- [ ] Veralt-/Fehlend-Daten-Erkennung
- [ ] Audit-Log (zentral, manipulationsarm)
- [ ] Secret-Handling + Log-Scrubbing (keine Keys in Logs/Entitäten)
- [ ] Kosten-/Nutzungslimits + Moduswechsel bei Überschreitung
- [ ] Not-Aus / manueller Modus + Nutzerbenachrichtigung

---

## Bezug zu anderen Plänen

- Validierung im Ablauf → [05 · Planungs-Engine](05-planungs-engine.md)
- Schlüssel/Datenminimum → [03 · KI / API](03-ki-api.md)
- Fallback/HEMS → [06 · HEMS-Schnittstelle](06-hems-schnittstelle.md)
- Audit/Persistenz → [07 · Datenmodell](07-datenmodell.md)
- Bedienung → [09 · Benutzeroberfläche](09-benutzeroberflaeche.md)
