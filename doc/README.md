# Skytech Energy Pilot — Dokumentation

Diese Doku ersetzt die am 2026-07-10 gelöschte alte Doku (`info.md`, `plan/*.md`,
`user-regeln.md`, `user-fragen.md`). Sie ist **nicht** eine Wiederherstellung der alten
Dateien, sondern eine Neufassung, die den **tatsächlichen Stand des Codes** beschreibt
— inklusive der Stellen, an denen die Implementierung von der ursprünglichen Planung
abweicht oder Lücken hat. Wo die alten Entscheidungen (D-001 … D-052) noch relevant
sind, wurden sie mit eingearbeitet bzw. in [decisions-log.md](decisions-log.md)
verdichtet. Die Originaldateien bleiben über Git-Historie abrufbar:
`git show ad48b23^:info.md` (Commit `ad48b23` = "doc: Alte Doku gelöscht").

## Verhältnis zu CLAUDE.md

[`CLAUDE.md`](../CLAUDE.md) im Repo-Root ist die **kompakte, verbindliche
Arbeitsgrundlage** für mich (Claude) und andere Agenten — dort stehen die eisernen
Projektregeln, die aktuell gültigen Entscheidungen und der Arbeitsablauf. Bei
Widerspruch zwischen `CLAUDE.md` und dieser Doku hat **`CLAUDE.md` immer Vorrang**.
Diese Doku hier ist die **ausführliche technische Referenz**, auf die `CLAUDE.md`
verweist, statt Details zu duplizieren.

## Sprache

Code (Variablen/Funktionen/Klassen) englisch, Kommentare deutsch, HA-Entitäten/Helfer
deutsch (Projektregel, siehe `CLAUDE.md`). Diese Doku ist konsequent auf Deutsch
gehalten, wie der Rest der Projektdokumentation.

## Inhaltsverzeichnis

| Datei | Inhalt |
|---|---|
| [architecture.md](architecture.md) | EP-vs-HEMS-Aufteilung, Tech-Stack, Boot-Sequenz, Datenfluss, Modul-Übersicht |
| [entity-naming.md](entity-naming.md) | `ems_*`/`ep_*`-Namensschema, Schreibvertrag, Beispiele |
| [control-modes.md](control-modes.md) | Steuermodi (Manuell/Hybrid/Automatisch) vs. Betriebsmodi (Beobachten→Autopilot) |
| [devices.md](devices.md) | Gerätemodell, HEMS-Discovery, Zusatz-Entitäten, Anfangsgeräte (Batterie/Heizstab/Heizlüfter) |
| [planning-engine.md](planning-engine.md) | Planner-Ablauf, KI-Provider, Determinismus-Absicherung, Prompt-Aufbau |
| [validation-safety.md](validation-safety.md) | Validierungs-Pipeline, Allowlist, Fallback-Verhalten, Sicherheitsregeln |
| [configuration.md](configuration.md) | Vollständige Addon-Config-Optionsreferenz |
| [api-reference.md](api-reference.md) | Alle EP-HTTP-Endpunkte + genutzte HEMS-Endpunkte |
| [data-model.md](data-model.md) | SQLite-Schema und Migrationen |
| [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md) | Spec-vs-Code-Lücken, historische Stolpersteine, offene Bugs |
| [decisions-log.md](decisions-log.md) | Verdichtetes Decision-Log D-001 … D-052 |
| [roadmap.md](roadmap.md) | Meilensteine M0–M6, realistischer Umsetzungsstand |
| [contributing.md](contributing.md) | Regeln für Entwicklung — Menschen **und** Agenten |

## Schnellstart für neue Agenten/Entwickler

1. [architecture.md](architecture.md) lesen — Projektzweck und Grobstruktur verstehen.
2. [contributing.md](contributing.md) lesen — Git-/Versions-/Changelog-Regeln, bevor irgendetwas committet wird.
3. Für die konkrete Aufgabe die passende Datei oben nachschlagen, statt zu raten.
4. [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md) prüfen, bevor man annimmt, eine Spec-Aussage sei bereits implementiert — Spec und Code laufen an mehreren Stellen auseinander.

## Weitere Ordner im Repo (kein Teil dieser Doku, aber relevant)

- [`user-beispiele/`](../user-beispiele/) — vom User erstellte `.txt`/`.md`-Vorlagen, haben laut Projektregel **immer** Vorrang vor KI-generierter Doku (auch vor dieser hier).
- [`claude-fragen/`](../claude-fragen/) — historisches Archiv offener Fragen von Claude an den User; Antworten sind in [decisions-log.md](decisions-log.md) verdichtet.
- [`claude-ha-config-dateien/`](../claude-ha-config-dateien/) — fertige `<domain>_ep.yaml`-Helfer-Pakete für den User.
- [`changelog.md`](../changelog.md) — Änderungslog je Version, Quelle der Wahrheit für "was wurde wann geändert".
- [`upcoming_changes.md`](../upcoming_changes.md) — Notizzettel für bekannte, noch nicht behobene Probleme.
