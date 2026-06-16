# 10 · Betriebsmodi

> Die vier Betriebsmodi des Energy Pilot und die empfohlene schrittweise Einführung von „nur beobachten" bis „Autopilot".

**Status:** Entwurf · **info.md-Bezug:** §14

---

## Ziel & Abgrenzung

- Festlegen, **ob und wie** Pläne tatsächlich an HEMS gehen.
- Sichere, schrittweise Annäherung an die Vollautomatik.
- **Nicht** hier: die Planerzeugung (→ [05](05-planungs-engine.md)) oder Übergabe-Technik (→ [06](06-hems-schnittstelle.md)).

Gesteuert über `select.skytech_energy_pilot_mode` und `switch.…_auto_submit` (→ [02](02-home-assistant.md)).

---

## Die vier Modi (info.md §14)

### 1. Beobachten
- Daten werden analysiert.
- **Keine** Pläne an HEMS.
- App zeigt Prognosen, mögliche Entscheidungen und Begründungen.

### 2. Vorschlagen
- Pilot erstellt einen konkreten Plan.
- Nutzer muss ihn **manuell bestätigen**.
- Erst danach Übergabe an HEMS.

### 3. Shadow Mode
- Pilot erstellt **automatisch** Pläne.
- Pläne werden **nicht ausgeführt**.
- Theoretische Ergebnisse werden mit der realen Anlagenentwicklung verglichen.

### 4. Autopilot
- Validierte Pläne werden **automatisch** an HEMS übertragen.
- Harte Grenzen und lokale Sicherheitsprüfungen bleiben aktiv.
- Nutzer kann jederzeit in den manuellen Modus wechseln.

---

## Empfohlene Einführung

```text
Beobachten → Vorschlagen → Shadow Mode → Autopilot
```

Der **Shadow Mode** soll die Erfolgskennzahlen (→ [11](11-roadmap.md)) über mehrere Wochen vergleichen, **bevor** der Autopilot aktiviert wird.

---

## Verhalten je Modus (Übersicht)

| Modus | Plan erstellen | An HEMS übergeben | Nutzerfreigabe nötig |
|---|---|---|---|
| Beobachten | nein (nur Analyse/Vorschau) | nein | – |
| Vorschlagen | ja | ja, nach Bestätigung | ja |
| Shadow | ja, automatisch | nein | – |
| Autopilot | ja, automatisch | ja, automatisch | nein (jederzeit abbrechbar) |

---

## Möglichkeiten in der Oberfläche

- Moduswahl (Beobachten/Vorschlagen/Shadow/Autopilot).
- Im Vorschlagsmodus: Plan ansehen, begründet bekommen, **bestätigen/ablehnen**.
- Im Shadow Mode: Vergleichskennzahlen Plan vs. Realität.
- Jederzeit Wechsel in manuellen Modus / Not-Aus (→ [08](08-sicherheit.md)).

---

## Offene Entscheidungen

- [ ] Mindestkonfidenz je Modus (z. B. Autopilot nur ab Konfidenz X)
- [ ] Ablauf der manuellen Bestätigung (in-UI, HA-Benachrichtigung mit Aktion, beides?)
- [ ] Soll Autopilot bei bestimmten Warnungen automatisch in „Vorschlagen" zurückfallen?
- [ ] Mindestdauer/Kriterien des Shadow Mode vor Autopilot-Freigabe
- [ ] Wer darf den Modus ändern (Berechtigungen/Bestätigung)?

---

## Aufgaben / Umsetzung

- [ ] Modus-Zustandsmaschine im Backend
- [ ] Verknüpfung Modus ↔ Plan-Submission-Verhalten (→ [06](06-hems-schnittstelle.md))
- [ ] Bestätigungs-Workflow für „Vorschlagen"
- [ ] Shadow-Vergleich (Plan vs. Realität, Kennzahlen → [11](11-roadmap.md))
- [ ] Moduswahl + Status als HA-Entitäten und in der UI

---

## Bezug zu anderen Plänen

- Planerzeugung → [05 · Planungs-Engine](05-planungs-engine.md)
- Übergabe an HEMS → [06 · HEMS-Schnittstelle](06-hems-schnittstelle.md)
- Sicherheit/Not-Aus → [08 · Sicherheit](08-sicherheit.md)
- Bedienung → [09 · Benutzeroberfläche](09-benutzeroberflaeche.md)
- Reihenfolge/Erfolgskriterien → [11 · Roadmap](11-roadmap.md)
