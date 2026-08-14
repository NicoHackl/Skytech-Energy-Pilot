# AGENTS.md — Skytech Energy Pilot

> **Diese Datei ist die einzige Quelle der Wahrheit für Projektregeln.**
> `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` und `.cursor/rules/` sind reine
> Verweise hierher und enthalten selbst **keine** Regeln. Regeln werden ausschließlich hier gepflegt.

## Projektzweck

**Skytech Energy Pilot (EP)** ist ein eigenständiges Home-Assistant-Addon für KI-gestützte,
vorausschauende **strategische** Energieplanung (Horizont 24–48 h). **EP plant, das HEMS regelt.**
EP steuert niemals Geräte direkt.

- **HEMS** (Basis, Pflicht) — lokale Echtzeitregelung im 1–2-s-Takt, PV-Überschussverteilung.
  Eigenes Repo: [SkytechHEMS](https://github.com/NicoHackl/SkytechHEMS).
- **EP** (optionale KI-Erweiterung) — liefert Priorität, Freigabe und Schutzleistung je Gerät als
  **Vorschlag**.
- HEMS läuft ohne EP voll funktionsfähig weiter. EP ohne HEMS ist sinnlos.

Tech-Stack: Python 3.11, aiohttp (Webserver + Ingress), SQLite (WAL). Oberfläche: React 18 +
TypeScript + Vite. HA-Zugriff über den Supervisor-Core-API-Proxy via `SUPERVISOR_TOKEN`.

## Präzedenz bei Widersprüchen

1. **Direkte Anweisung des Users im Gespräch** — schlägt alles.
2. **`user-beispiele/`** — vom User selbst erstellte Vorlagen (`.txt`/`.md`).
3. **Diese Datei (`AGENTS.md`)** — die eisernen Regeln.
4. **`docs/`** — ausführliche technische Referenz.

Widerspricht `docs/` dieser Datei, ist `docs/` falsch und wird korrigiert — nicht umgekehrt.
Widersprechen sich `docs/` und `user-beispiele/`, wird `docs/` auf den Stand der User-Vorlage
gebracht.

## Eiserne Regeln (nicht verhandelbar)

1. **Git:** Commit und Push erfolgen ausschließlich im aktiv ausgecheckten Arbeitsbranch, nach
   **jeder** abgeschlossenen Aufgabe — auch im HEMS-Repo (D-022). Release-Kanäle `stage-dev` /
   `stage-beta` / `stage-stable`, Promotion nur manuell auf Zuruf. Details:
   [docs/git-workflow.md](docs/git-workflow.md).
2. **Sprache Code:** Variablen, Funktionen, Klassen, Dateinamen **englisch**.
3. **Sprache Text:** Kommentare, Commit-Messages, Log-Meldungen, UI-Texte, Doku **deutsch**.
   HA-Entitäten und -Helfer ebenfalls deutsch, Umlaute ä/ö/ü → a/o/u (nicht ae/oe/ue).
4. **Changelog-Pflicht:** Jede funktionale oder gestalterische Änderung bekommt im selben
   Arbeitspaket einen Eintrag in [CHANGELOG.md](CHANGELOG.md).
5. **Doku-Pflicht:** Ändert sich Verhalten, das in `docs/` beschrieben ist, wird die betroffene
   Datei im selben Arbeitspaket mitgeändert. Keine Nachreichung.
6. **Versionspflicht:** Jede Änderung mit Auswirkung auf Darstellung, Information oder Funktion in
   Home Assistant erhöht die Patch-Nummer — **gemeinsam** in `config.yaml: version` und
   `app/energy_pilot/__init__.py: __version__`. Beide Werte müssen identisch bleiben.
7. **Keine Secrets:** Keine API-Keys, Tokens oder Zugangsdaten im Code, in Logs, in HA-Entitäten
   oder in Commit-Messages. Siehe [docs/sicherheit-datenschutz.md](docs/sicherheit-datenschutz.md).
8. **Nicht raten:** Ist eine Anforderung unklar, wird gefragt statt geraten. Getroffene Annahmen
   werden explizit genannt. Offene Punkte gehören nach `claude-fragen/`, nicht in eine Vermutung
   im Code.
9. **Namens-Domäne nach Datenrichtung (D-029):** vom User oder HEMS gepflegte technische
   Gerätewerte sind `ems_*` (HEMS-Domäne, EP **liest** nur); EP-Vorschlagswerte sind `ep_*`
   (EP **schreibt**), bereitgestellt als `sensor.ep_<gerät>_<feld>_vorschlag`. Nicht verhandelbar.
   Schreibvertrag und Ausnahmen: [docs/namensschema.md](docs/namensschema.md).
10. **KI ist Orchestrator, nie Regler.** Freitext ist niemals ein Steuerbefehl — ausschließlich
    strukturiertes Tool-/Function-Calling mit erzwungenem Antwortschema. Kein von der KI erzeugter
    Code wird ausgeführt.
11. **Jeder Plan wird lokal validiert** — gegen JSON-Schema **und** harte Grenzen, mit Ablaufzeit
    und vollständigem Audit-Log. Harte Grenzen sind durch die KI nie änderbar.
    [docs/sicherheit-datenschutz.md](docs/sicherheit-datenschutz.md).
12. **Datenminimum:** Nur nötige, verdichtete Daten an eine externe KI — niemals die HA-Datenbank.
13. **Fallback:** Bei Cloud- oder KI-Ausfall blockiert EP **nie** die Anlage; das HEMS regelt lokal
    weiter. Fehler werden geloggt und auditiert, nicht als harter Abbruch behandelt.
14. **Oberfläche:** React + TypeScript (`strict`) + Vite, eine `styles.css` mit Design-Tokens,
    eigenes Icon-Set. **Keine** UI-Bibliothek, kein CSS-Framework, kein State- oder
    Data-Fetching-Paket, keine Literalfarben, keine gestaltenden Inline-Styles. Vor der ersten Zeile
    Frontend-Code [docs/frontend.md](docs/frontend.md) und
    [docs/design-system.md](docs/design-system.md) lesen — unter HA-Ingress gelten dort
    Sonderregeln, allen voran: **kein Pfad beginnt mit `/`**.
15. **Datum und Uhrzeit:** Datumsangaben ausnahmslos als `TT.MM.JJJJ` (z. B. `14.08.2026`).
    Uhrzeiten in Berliner Zeit (`Europe/Berlin`) als `hh:mm`, bei Bedarf `hh:mm:ss`. **Nie** ein
    Zeitzonen-Kürzel oder einen Offset anhängen. Gilt für alle menschenlesbaren Ausgaben: Doku,
    `CHANGELOG.md`, ADRs, Commit-Messages, Log-Meldungen, UI-Texte, Fehlermeldungen. Maschinenformate
    (SQLite-Spalten, API-Nutzlasten, Plan-Zeitstempel) bleiben ISO/UTC und werden erst bei der
    Ausgabe umgesetzt.
16. **Designsprache:** Für dieses Projekt gilt **Home Assistant** (`data-design="ha"`, Akzent
    `#18BCF2`) — festgelegt, weil EP im HA-Ingress-Panel läuft. Wird nicht erneut erfragt und nicht
    zur Laufzeit umgeschaltet. [docs/design-system.md](docs/design-system.md).
17. **Hell und Dunkel:** Die Oberfläche bietet einen sichtbaren Schalter zwischen Hell- und
    Dunkel-Modus. Beide Modi sind vollständig ausgestaltet, die Wahl überlebt das Neuladen, die
    Voreinstellung kommt vom Betriebssystem.

## Befehle

| Zweck | Befehl |
|---|---|
| Abhängigkeiten installieren | `pip install -r app/requirements-dev.txt` und `cd frontend && npm install` |
| Tests | `pytest` |
| Linting / Formatierung | `ruff check app` |
| Build (Frontend) | `cd frontend && npm run build` |
| Build (Addon-Image) | `docker build -t energy-pilot .` |

Vor jedem Commit müssen Tests und Linting fehlerfrei durchlaufen; nach einer Frontend-Änderung
zusätzlich der Frontend-Build, dessen Ergebnis (`frontend/dist/`) mitcommittet wird.

## Wo steht was

Diese Datei enthält bewusst **keine** technischen Details. Vor der Arbeit an einem Thema die
passende Datei lesen, statt zu raten:

| Datei | Inhalt |
|---|---|
| [docs/README.md](docs/README.md) | Einstieg und Index der gesamten Doku |
| [docs/architektur.md](docs/architektur.md) | EP-vs-HEMS, Boot-Sequenz, Datenfluss, Modul-Übersicht |
| [docs/entwicklerrichtlinien.md](docs/entwicklerrichtlinien.md) | Naming, Struktur, Fehlerbehandlung, Logging, Kommentarstil |
| [docs/frontend.md](docs/frontend.md) | Frontend-Stack, Ingress-Besonderheiten, Seiten, API-Client, Auslieferung |
| [docs/design-system.md](docs/design-system.md) | Tokens, Klassenkatalog, Zustände, Responsiv, Icons |
| [docs/git-workflow.md](docs/git-workflow.md) | Branches, Release-Kanäle, Commit-Format, Versionierung |
| [docs/test-strategie.md](docs/test-strategie.md) | Testarten, Pflicht-Testfälle, Coverage-Ziel |
| [docs/design-entscheidungen.md](docs/design-entscheidungen.md) | Entscheidungs-Log D-001 … — Quelle der Wahrheit fürs „warum" |
| [docs/konfiguration.md](docs/konfiguration.md) | Addon-Config-Optionsreferenz, DB-gestützte Laufzeitwerte |
| [docs/datenmodell.md](docs/datenmodell.md) | SQLite-Schema und Migrationen |
| [docs/api-referenz.md](docs/api-referenz.md) | EP-Endpunkte + genutzte HEMS-Endpunkte |
| [docs/sicherheit-datenschutz.md](docs/sicherheit-datenschutz.md) | Validierungs-Pipeline, Allowlist, Secrets, Fallback |
| [docs/bekannte-luecken.md](docs/bekannte-luecken.md) | Abweichungen Spec ↔ Code, Stolpersteine, offene Bugs |
| [docs/roadmap.md](docs/roadmap.md) | Meilensteine M0–M6 und Umsetzungsstand |
| [docs/namensschema.md](docs/namensschema.md) | `ems_*`/`ep_*`, Schreibvertrag je Geräteklasse |
| [docs/steuermodi.md](docs/steuermodi.md) | Steuermodi, Betriebsmodi, HEMS-Modus-Achse |
| [docs/geraete.md](docs/geraete.md) | Gerätemodell, HEMS-Discovery, Zusatz-Entitäten |
| [docs/planungs-engine.md](docs/planungs-engine.md) | Planner-Ablauf, KI-Provider, Determinismus |

## Arbeitsablauf

1. Passende `docs/`-Datei lesen, bevor Code entsteht — und `user-beispiele/`, wenn das Thema dort
   berührt wird.
2. [docs/bekannte-luecken.md](docs/bekannte-luecken.md) prüfen, bevor angenommen wird, eine in der
   Doku beschriebene Funktion sei tatsächlich implementiert.
3. Implementieren, `ruff check app` und `pytest` laufen lassen (Frontend: `npm run build`).
4. Changelog-, Doku- und Versionseinträge im **selben** Arbeitspaket nachziehen.
5. Committen und pushen auf dem aktiv ausgecheckten Branch.
6. Neue Grundsatzentscheidung? → Eintrag in
   [docs/design-entscheidungen.md](docs/design-entscheidungen.md), ausführlich als ADR unter
   [docs/adr/](docs/adr/).
