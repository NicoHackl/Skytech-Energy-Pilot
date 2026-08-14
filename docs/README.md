# Dokumentation — Skytech Energy Pilot

Ausführliche technische Referenz. Die **verbindlichen Regeln** stehen nicht hier, sondern in
[`AGENTS.md`](../AGENTS.md) im Repo-Root. Bei Widerspruch gilt `AGENTS.md`.

Diese Doku beschreibt den **tatsächlichen Stand des Codes**, nicht die Wunschvorstellung. Weicht die
Implementierung von der Spec ab, gehört das nach [bekannte-luecken.md](bekannte-luecken.md) — nicht
stillschweigend schöngeschrieben. Sie ersetzt die am 10.07.2026 gelöschten Dateien `info.md`,
`plan/*.md`, `user-regeln.md` und `user-fragen.md`; die Originale bleiben über die Git-Historie
abrufbar (`git show ad48b23^:info.md`).

## Schnellstart für neue Agenten und Entwickler

1. [`AGENTS.md`](../AGENTS.md) lesen — eiserne Regeln und Befehle.
2. [architektur.md](architektur.md) lesen — Projektzweck und Grobstruktur.
3. [git-workflow.md](git-workflow.md) lesen, **bevor** irgendetwas committet wird.
4. Für die konkrete Aufgabe die passende Datei unten nachschlagen, statt zu raten.
5. [bekannte-luecken.md](bekannte-luecken.md) prüfen, bevor angenommen wird, eine hier beschriebene
   Funktion existiere bereits.

## Inhaltsverzeichnis

| Datei | Inhalt |
|---|---|
| [architektur.md](architektur.md) | EP-vs-HEMS-Aufteilung, Tech-Stack, Boot-Sequenz, Datenfluss, Modul-Übersicht |
| [entwicklerrichtlinien.md](entwicklerrichtlinien.md) | Naming, Projektstruktur, Fehlerbehandlung, Logging, Kommentarstil |
| [frontend.md](frontend.md) | React-Stack, Ingress-Besonderheiten, Seiten, API-Client, Auslieferung |
| [design-system.md](design-system.md) | Designsprache `ha`, Tokens je Modus, Klassenkatalog, Zustände, Icons |
| [git-workflow.md](git-workflow.md) | Branch-Modell, Release-Kanäle, Commit-Format, Versionierung |
| [test-strategie.md](test-strategie.md) | Testarten, Pflicht-Testfälle, Coverage-Ziel |
| [design-entscheidungen.md](design-entscheidungen.md) | Entscheidungs-Log D-001 … — Quelle der Wahrheit fürs „warum" |
| [adr/](adr/) | Ausführliche Architecture Decision Records zu einzelnen Entscheidungen |
| [konfiguration.md](konfiguration.md) | Vollständige Addon-Config-Optionsreferenz |
| [datenmodell.md](datenmodell.md) | SQLite-Schema und Migrationen |
| [api-referenz.md](api-referenz.md) | Alle EP-HTTP-Endpunkte + genutzte HEMS-Endpunkte |
| [sicherheit-datenschutz.md](sicherheit-datenschutz.md) | Validierungs-Pipeline, Allowlist, Secrets, Fallback-Verhalten |
| [bekannte-luecken.md](bekannte-luecken.md) | Abweichungen Spec ↔ Code, Stolpersteine, offene Bugs |
| [roadmap.md](roadmap.md) | Meilensteine M0–M6, realistischer Umsetzungsstand |

### Projektspezifische Vertiefungen

| Datei | Inhalt |
|---|---|
| [namensschema.md](namensschema.md) | `ems_*`/`ep_*`-Namensschema, Schreibvertrag, Beispiele |
| [steuermodi.md](steuermodi.md) | Steuermodi (Manuell/Hybrid/Automatisch) vs. Betriebsmodi vs. HEMS-Modus-Achse |
| [geraete.md](geraete.md) | Gerätemodell, HEMS-Discovery, Zusatz-Entitäten, Anfangsgeräte |
| [planungs-engine.md](planungs-engine.md) | Planner-Ablauf, KI-Provider, Determinismus-Absicherung, Prompt-Aufbau |

## Pflegeregeln dieser Doku

- **Jede Information genau einmal.** Steht etwas in `AGENTS.md`, wird es hier nicht wiederholt,
  sondern verlinkt.
- Ändert sich Verhalten, das hier beschrieben ist, wird die betroffene Datei im **selben**
  Arbeitspaket mitgeändert (eiserne Regel 5).
- Datumsangaben als `TT.MM.JJJJ`, Uhrzeiten in Berliner Zeit ohne Offset (eiserne Regel 9).

## Weitere Ordner im Repo

- [`user-beispiele/`](../user-beispiele/) — vom User erstellte `.txt`/`.md`-Vorlagen, haben **immer**
  Vorrang vor KI-generierter Doku (auch vor dieser hier).
- [`claude-fragen/`](../claude-fragen/) — historisches Archiv offener Fragen an den User; Antworten
  sind in [design-entscheidungen.md](design-entscheidungen.md) verdichtet.
- [`claude-ha-config-dateien/`](../claude-ha-config-dateien/) — fertige `<domain>_ep.yaml`-Helfer-Pakete.
- [`CHANGELOG.md`](../CHANGELOG.md) — Änderungslog je Version, Quelle der Wahrheit für „was wurde wann geändert".
- [`upcoming_changes.md`](../upcoming_changes.md) — Notizzettel für bekannte, noch nicht behobene Probleme.
