# D-060: Geräteregeln als Freitext, Begründungspflicht statt Nachbearbeitung

- **Datum:** 17.08.2026
- **Status:** Aktiv
- **Betrifft:** `app/energy_pilot/device_regeln.py`, `plan_context.py`, `plan_schema.py`,
  `validator.py`, `web/server.py`, `frontend/src/pages/Geraete.tsx`,
  `frontend/src/pages/Ziele.tsx`

## Kontext

Beobachtetes Problem: die KI lieferte bei gleicher Sachlage widersprüchliche Vorschläge.
Zwei belegte Fälle aus der Anlage des Users:

1. **Heizstab.** Warmwasser bei 80 °C, die nächsten Tage werden heiß, die Solarthermie soll
   die Warmwasserversorgung übernehmen und der Speicher nicht überhitzen. Die KI gab den
   Heizstab mal frei, mal nicht.
2. **Heizlüfter.** Bei Tagesspitzen über 25 °C wurde mal mit „Heizunterstützung“ eingeschaltet,
   mal ausgeschaltet.

Der Abgleich von Code und Live-Anlage zeigte: das ist überwiegend **keine Halluzination**.
Die Absicht des Users existierte nirgends in maschinenlesbarer Form — nur als optionaler
Freitext `ai_hint` je Zusatzwert (D-047) und `funktion` je Gerät (D-051), beide als je ein
Feld unter vielen in einem mehrere Kilobyte großen JSON-Datenblock. Dazu fehlten Messwerte
(die gemessene Speichertemperatur war keine Größe im Kontext, die Obergrenze 85 °C stand
stattdessen als vermeintlicher Ist-Wert), und die KI konnte abends das heutige Tagesmaximum
nicht kennen. Bei lückenhafter Information und weicher Anweisung sind **beide** Antworten
begründbar — also kam mal die eine, mal die andere.

## Betrachtete Optionen

### A) Typisiertes Regelwerk mit Erzwingung

Eine Tabelle `device_policies` mit typisierten Regeln (Quelle, Operator, Schwelle, Wirkung),
vor dem KI-Aufruf ausgewertet, in den Kontext eingespeist **und** nach dem Aufruf im Validator
gegen die Modellantwort erzwungen (`force_false` etc.).

- **Für:** deterministisch, prüfbar, deckt eiserne Regel 11 („harte Grenzen nie durch die KI
  änderbar“) unmittelbar ab. Beide Fälle oben wären hart gelöst.
- **Gegen:** Der User hat das ausdrücklich **abgelehnt** — er will, dass die Ergebnisse der KI
  selbst besser werden, nicht dass eine nachgelagerte Schicht sie korrigiert. Zusätzlich
  wächst die Konfigurationsoberfläche deutlich (Dropdown-Baukasten je Regel).

### B) Nachgelagerte Dämpfung (Hysterese, Mindesthaltezeit, Delta-Limit)

Eine Freigabe erst übernehmen, wenn die KI sie zwei Läufe hintereinander vorschlägt; Sprünge
gegen den Vorplan begrenzen (Validator-Stufe 5, D-021).

- **Für:** unterdrückt Flattern zuverlässig, unabhängig von der Ursache.
- **Gegen:** Vom User wortwörtlich abgelehnt („so wenig nachgelagerte harte Logik wie
  möglich“). Sie verdeckt außerdem die Ursache, statt sie zu beheben: ein Plan, der aus
  falschen Annahmen entstand, wird durch Verzögerung nicht richtig.

### C) Freitext-Regeln plus erzwungene Selbsterklärung (gewählt)

Der User formuliert die Bedingungen in eigenen Worten — je Gerät (`device_regeln`) und einmal
hausweit (`global_regeln`). Die Regeln gehen als **eigener, im Prompt namentlich
adressierter Block** in den Kontext, nicht als weiteres Feld im Datenrauschen. Das
Antwortschema verlangt je Gerät zwei zusätzliche Pflichtfelder:

- `begruendung` — ein Satz mit der maßgeblichen Messgröße samt Wert,
- `angewandte_regeln` — die Regeln, auf die sich die Entscheidung stützt (leere Liste, wenn
  keine greift).

- **Für:** Entspricht der Vorgabe des Users. Erzwungene Selbsterklärung gegen genannte
  Vorgaben verbessert die Regeltreue, und — unabhängig davon — **macht sie eine
  Fehlentscheidung sichtbar** statt rätselhaft: im Plan-Tab steht, worauf die KI sich berufen
  hat. Kein neuer Sicherheitspfad, keine Parser-Oberfläche.
- **Gegen:** Keine Garantie. Ein Modell kann eine Regel nennen und trotzdem dagegen
  entscheiden. Freitext ist genau der Mechanismus, der vorher nicht zuverlässig griff — der
  Unterschied liegt in Platzierung (System-Kanal, eigener Block), Verbindlichkeit im Prompt
  und der Begründungspflicht, nicht in einer neuen Garantie.

## Entscheidung

**Option C.** Zusätzlich, um die Wahrscheinlichkeit auf der Datenseite zu erhöhen statt auf
der Korrekturseite:

- gemessene Warmwasser- und Außentemperatur als eigene, **gemittelte** Mess-Rollen (D-061) —
  der Verlauf zeigt, ob die Solarthermie lädt;
- `rolle` je Zusatzwert (`ist`/`grenze`/`sollwert`, D-061) — ein Sollwert wird nicht mehr als
  Messwert gelesen;
- Instruktion in den System-Kanal, harte Grenzen als `minimum`/`maximum` ins Antwortschema,
  Wetter-Kennzahlen unabhängig vom Slot-Fenster (D-062);
- Kontext quantisieren, Hash bilden, unveränderte Sachlage ⇒ kein neuer Aufruf (D-063);
- Konfidenz als definierte Teilnoten mit EP-Gegenrechnung, erst darauf ein
  Veröffentlichungs-Gate (D-064).

Option A bleibt als **dokumentierte Rückfallebene**. Reicht Freitext nicht, ist die
Eskalationsreihenfolge: stärkeres Modell für den Plan-Aufruf → Mehrfach-Sampling mit
Mehrheitsvotum → typisierte Regeln mit Erzwingung.

## Konsequenzen

- Eiserne Regel 11 bleibt gewahrt, aber nur für **technische** Grenzen: die klemmt der
  Validator weiter unabhängig vom Prompt. Die Betriebsabsicht des Users ist ausdrücklich
  **keine** harte Grenze in diesem Sinne — das ist der Preis der Entscheidung und muss beim
  Lesen von `sicherheit-datenschutz.md` mitgedacht werden.
- Validator-Stufe 5 (Delta-Limit, D-021) bleibt dauerhaft offen und ist als bewusst
  verworfen zu dokumentieren, nicht als Rückstand.
- Das Abnahmekriterium ist nicht ein Test, sondern eine Messung: Regeltext pflegen, fünf
  Läufe hintereinander auslösen, prüfen ob die Freigaben gleich bleiben und die Begründung
  jedes Mal die passende Regel nennt. Weicht ein Lauf ab, zeigt der Kontext-Hash, ob sich die
  Sachlage geändert hat oder das Modell gestreut hat.
