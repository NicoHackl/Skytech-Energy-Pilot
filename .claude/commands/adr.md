---
description: Neue Design-Entscheidung im Log und optional als ADR anlegen
argument-hint: <Entscheidung in einem Satz>
allowed-tools: Read, Edit, Write, Grep, Glob
---

Halte diese Design-Entscheidung fest: **$ARGUMENTS**

Vorgehen:

1. Lies `docs/design-entscheidungen.md` und ermittle die nächste freie `D-xxx` (fortlaufend,
   nie eine vergebene wiederverwenden).
2. Prüfe, ob eine bestehende Entscheidung dadurch abgelöst wird. Falls ja: deren Status auf
   `Ersetzt` setzen und auf die neue ID verweisen — die alte Zeile **nicht löschen**.
3. Ergänze eine Zeile in der Log-Tabelle: ID, Datum, Entscheidung, Status, Begründung.
   Die Begründung nennt ausdrücklich, **welche Alternative verworfen wurde und warum**.
4. Ist die Entscheidung tragweit (betrifft Architektur, Datenformate oder Zuständigkeitsgrenzen):
   lege zusätzlich `docs/adr/D-xxx-<kurzname>.md` auf Basis von `docs/adr/0000-vorlage.md` an,
   fülle alle Abschnitte inklusive **Rücknahmebedingung**, und verlinke aus der Tabelle darauf.
5. Prüfe, ob durch die Entscheidung eine Aussage in `docs/architektur.md` oder `AGENTS.md` falsch
   wird. Falls ja: dort im selben Zug korrigieren.

Fehlt dir Kontext für die Begründung, frag nach — eine Entscheidung ohne belastbares „warum" ist
im Log wertlos.
