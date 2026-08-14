---
description: Doku gegen den tatsächlichen Code abgleichen und Abweichungen melden
allowed-tools: Read, Grep, Glob, Bash(git log:*), Edit
---

Gleiche die Doku in `docs/` mit dem tatsächlichen Stand des Codes ab.

Prüfe der Reihe nach:

1. **Befehle** — Laufen die in `AGENTS.md` genannten Install-, Test-, Lint- und Build-Befehle
   überhaupt gegen die vorhandenen Projektdateien? Ein Befehl, der ins Leere zeigt, ist der
   häufigste Doku-Fehler.
2. **Struktur** — Existieren die in `docs/architektur.md` und `docs/entwicklerrichtlinien.md`
   beschriebenen Verzeichnisse und Komponenten? Gibt es Komponenten im Code, die nirgends
   dokumentiert sind?
3. **Schnittstellen** — Stimmen die Endpunkte in `docs/api-referenz.md` mit dem Code überein?
   Fehlende, umbenannte und undokumentierte Endpunkte einzeln nennen.
4. **Datenmodell** — Entsprechen Felder und Typen in `docs/datenmodell.md` dem Schema im Code?
5. **Platzhalter** — Suche `{{`, `<…>` und `<Name>` in `docs/` und `AGENTS.md`. Nicht ausgefüllte
   Platzhalter sind offene Baustellen und werden aufgelistet.
6. **Verweise** — Zeigen alle relativen Markdown-Links auf existierende Dateien?

Ergebnis als Liste, je Punkt: Datei, was die Doku sagt, was der Code macht, Schweregrad.

Ändere nichts von selbst außer eindeutig kaputten Links und offensichtlich falschen Dateipfaden.
Inhaltliche Abweichungen trägst du nach `docs/bekannte-luecken.md` ein — welche Seite falsch ist,
entscheidet der User.
