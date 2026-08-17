# D-066: Bilanz über Tage statt Schwellwerten — gerechnete Merkmale für die KI

- **Datum:** 17.08.2026
- **Status:** Aktiv
- **Betrifft:** `app/energy_pilot/features.py`, `device_speicher.py`, `history.py`,
  `history_collector.py`, `plan_context.py`, `web/server.py`,
  `frontend/src/pages/{Prognose,Geraete}.tsx`

## Kontext

Nach dem Freitext-Regelwerk (D-060) blieb die Frage offen, **woran** die KI eigentlich entscheiden
soll. Der User hat sie mit einem Beispiel beantwortet, das jede Schwellwert-Logik widerlegt:

> Wenn der Pufferspeicher aktuell 65 °C hat und die nächsten 3 Tage sollen >27 °C und sonnig
> werden, dann will ich den Heizstab nicht einschalten, weil es für den heutigen Tag noch reicht
> und die Solarthermie die nächsten 3 Tage das sowieso schafft. Anders, wenn es jetzt noch 2 Tage
> leicht bewölkt ist, aber PV-Überschuss zustande kommt — dann soll der Heizstab laufen, weil
> sonst die Temperatur weiter fällt und die nächsten Tage die Solarthermie nichts produzieren wird.

**Dieselben 65 °C, zwei entgegengesetzte richtige Antworten.** Keine Schwelle auf die
Speichertemperatur kann das ausdrücken, und eine Kette aus Schwellen auch nicht — die Entscheidung
hängt an einer Energiebilanz über mehrere Tage.

Der zuvor von mir vorgeschlagene Weg (Freitext per LLM in typisierte Regeln übersetzen, dann
deterministisch erzwingen) scheitert daran im Kern: er hätte die Absicht des Users in genau die
Schwellen gepresst, die hier nachweislich falsch sind. Der Denkfehler lag bei der Annahme, nicht
bei der Freitext-Entscheidung.

Was der KI fehlte, war deshalb kein Regelwerk, sondern **Rechengrundlage**:

| Frage aus dem Beispiel | Vorher verfügbar |
|---|---|
| Wie viel Energie steckt über dem Komfortminimum im Speicher? | nichts — weder Volumen noch Komfortminimum waren bekannt, nur °C |
| Wie viel Wärme bringt die Solarthermie an einem Tag? | nichts — der Rückblick reichte 60 Minuten weit und war nach jedem Neustart leer |
| Reicht das die nächsten Tage? | nicht beantwortbar, nur erratbar |
| Gibt es morgen noch Überschuss? | nur die Bruttoprognose, ohne Grundlast |

## Betrachtete Optionen

### A) Deterministischer Optimierer entscheidet, KI erklärt

Vorwärtssimulation der Speichertemperatur über den Horizont, Fahrplan per Greedy oder MILP, LLM
nur noch für Formulierung und Anomalien.

- **Für:** vollständig reproduzierbar, testbar, kein Modellrisiko.
- **Gegen:** widerspricht der Vorgabe des Users, dass die KI entscheidet. Und es bräuchte ein
  belastbares thermisches Modell samt Solarthermie-Ertragsschätzung — Daten, die die Anlage nicht
  liefert (kein Sensor im Solarkreis, ein einzelner Speicherfühler, keine PV-Prognose über morgen
  hinaus). Ein Optimierer auf geratenen Eingangsgrößen ist nicht besser als ein Modell auf
  geratenen Eingangsgrößen, nur unbeweglicher.

### B) Kandidatenpläne: Code erzeugt zulässige Varianten, KI wählt

- **Für:** ein illegaler Plan wird strukturell unmöglich, die Streuung bleibt auf „welche der
  legalen Optionen" begrenzt.
- **Gegen:** setzt voraus, dass man die Varianten überhaupt bewerten kann — und dafür braucht man
  zuerst die Bilanzgrößen. Die Option ist also nicht Alternative, sondern **Folgeschritt**.

### C) Bilanzgrößen rechnen, Entscheidung bei der KI (gewählt)

EP rechnet die Größen, die die Frage des Users beantwortbar machen, und übergibt sie als Zahlen:

- **Rückblick** (D-065): gemessene Tageswerte der letzten Tage aus der HA-Historie. Steigt die
  Speichertemperatur, während die elektrische Tagesenergie desselben Geräts bei ≈ 0 liegt, kam die
  Wärme von einer anderen Quelle. **Damit ist der Solarthermie-Beitrag messbar, ohne einen
  einzigen neuen Sensor** — beim User real belegt: 14 Tage ≈ 0,014 kWh/Tag elektrisch, Speicher
  trotzdem bis 89 °C.
- **Gerätemerkmale**: `reserve_kwh`, `energiebedarf_kwh`, `fremdwaerme_mittel_kwh`,
  `deckung_tage`.
- **Systemmerkmale**: geglättete Grundlast aus den Tagesminima, daraus der Netto-Überschuss.

- **Für:** entspricht der Vorgabe (KI entscheidet), nutzt ausschließlich Daten, die real
  vorliegen, und macht die Bilanz im Plan-Tab prüfbar. Nichts davon ist eine Regel.
- **Gegen:** die kWh-Zahlen sind Schätzungen (durchmischter Speicher, ein Fühler). Und es bleibt
  eine Modellentscheidung — die KI *kann* die Bilanz ignorieren.

## Entscheidung

**Option C.** Zusätzlich zwei ausdrückliche Ehrlichkeiten im Kontext, weil beide Fehlschlüsse
sonst wahrscheinlich sind:

1. `forecast.horizont = "heute und morgen"` plus der Satz, dass es für spätere Tage **keine**
   Ertragsprognose gibt und die Einschätzung über den Rückblick laufen muss. Ohne das erfindet ein
   Modell Tag-3-Erträge.
2. Der Hinweis, dass die kWh-Angabe eine Schätzung für einen durchmischten Speicher ist — gut für
   „reicht es einige Tage", nicht für Feinregelung.

Option B bleibt der dokumentierte Folgeschritt, falls die Streuung trotz Bilanz zu groß ist.
Option A bleibt verworfen, solange die Anlage keine belastbare Ertragsmessung im Solarkreis und
keine PV-Prognose über morgen hinaus liefert.

## Konsequenzen

- Die neuen Gerätefelder (Volumen, Komfortminimum, Zielwert) sind **Anlagendaten und eine
  Anforderung**, keine Entscheidungsregel. Diese Abgrenzung zu D-060 muss beim Lesen der
  Geräte-Doku mitgedacht werden: „nie unter 45 °C" sagt nicht, wann der Heizstab läuft.
- Fehlt eine Eingabe, bleibt das Merkmal `None` und erscheint als `fehlt` im Kontext. Ein
  stiller Nullwert wäre hier gefährlicher als eine Lücke — 0 kWh Reserve liest sich wie „Speicher
  leer".
- EP liest ab jetzt die HA-**Historie**. Das ist eine neue Abhängigkeit vom Recorder; fällt er
  aus, bleiben die Tage offen und werden später nachgeholt (eiserne Regel 13). Die eigene Tabelle
  wächst über die Recorder-Aufbewahrung hinaus, sodass der Rückblick mit der Zeit belastbarer
  wird als HA selbst.
- Zwei Verbesserungen liegen beim Anlagenbetreiber, nicht im Code: `state_class: measurement` für
  Speicherfühler und E3DC-Sensoren (permanente Tagesstatistiken statt ~10 Tagen Rohdaten) und eine
  PV-Prognose, die über morgen hinausreicht.
- Das Abnahmekriterium ist die Begründung im Plan-Tab: sie muss die **Bilanz mit Zahlen** nennen
  („Reserve 4,1 kWh, letzte Tage +6 kWh/Tag ohne Strom, Folgetage ähnlich bewölkt"), nicht eine
  Regel zitieren. Tut sie das nicht, hat die KI die Merkmale ignoriert — und das ist dann ein
  Modellproblem, kein Datenproblem.
