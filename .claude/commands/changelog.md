---
description: Changelog-Eintrag aus den aktuellen Änderungen erzeugen
allowed-tools: Bash(git diff:*), Bash(git status), Bash(git log:*), Read, Edit
---

Erzeuge einen Eintrag für `CHANGELOG.md` aus den aktuellen Änderungen.

Aktueller Stand:
- Status: !`git status --short`
- Diff: !`git diff HEAD --stat`

Vorgehen:

1. Ermittle aus dem Diff, was sich **funktional** geändert hat — nicht welche Dateien angefasst
   wurden. Reine Formatierung, Refactoring ohne Verhaltensänderung und Testanpassungen erzeugen
   keinen Eintrag.
2. Ordne jede Änderung einer Kategorie zu: `Hinzugefügt`, `Geändert`, `Behoben`, `Entfernt`,
   `Sicherheit`.
3. Formuliere je Änderung **eine** Zeile auf Deutsch, aus Sicht des Nutzers — was er jetzt anders
   erlebt, nicht wie es implementiert wurde.
4. Trage die Zeilen in `CHANGELOG.md` unter `## [Unveröffentlicht]` in den passenden Abschnitt ein.
   Fehlt der Abschnitt, lege ihn an.

Ergibt der Diff keine nutzerrelevante Änderung: sag das und ändere nichts.
