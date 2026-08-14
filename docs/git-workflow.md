# Git-Workflow

> Die Grundregel — Commit und Push ausschließlich im aktiv ausgecheckten Arbeitsbranch, nach
> **jeder** abgeschlossenen Aufgabe — steht in [`AGENTS.md`](../AGENTS.md). Hier steht der
> ausführliche Ablauf.

## Branch-Modell (D-022/D-053)

| Branch | Zweck |
|---|---|
| `claude/stage` | Arbeitsbranch für Agenten und laufende Entwicklung (umbenannt von `claude/main`) |
| `stage-dev` | Release-Kanal **Dev** — eigenes `config.yaml` (`slug: …_dev`, Name-Suffix „(Dev)") |
| `stage-beta` | Release-Kanal **Beta** — eigenes `config.yaml` (Suffix „(Beta)") |
| `stage-stable` | Release-Kanal **Stable** |

Der User bindet das Repo in Home Assistant **dreifach** per Branch-URL ein (`…#stage-dev` usw.);
jeder Kanal erscheint dort als eigenes Addon. Deshalb hat jeder Kanal ein eigenes `config.yaml`
mit eigenem `slug` — zwei Addons mit gleichem Slug schließen sich gegenseitig aus.

**Promotion nur manuell auf Zuruf:** `claude/stage` → `stage-dev` → `stage-beta` → `stage-stable`.
Kein Automatismus, kein Agent führt eine Promotion von sich aus durch.

Dieselbe Branch-Regel gilt im separaten Repo [SkytechHEMS](https://github.com/NicoHackl/SkytechHEMS)
(D-022).

> **Namens-Hinweis:** Der ursprüngliche Text von D-053 schreibt die Kanäle mit Schrägstrich
> (`stage/dev`). Angelegt wurden sie mit Bindestrich. Verbindlich sind die real existierenden
> Namen — auf sie zeigen die in HA eingetragenen Repo-URLs, und nur sie triggern die CI.

## Commit-Format

[Conventional Commits](https://www.conventionalcommits.org/), Betreffzeile deutsch, max. 72 Zeichen:

```text
<typ>(<bereich>): <was sich ändert, Imperativ>

<optionaler Rumpf: warum, nicht was>
```

Typen: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`.

```text
feat(planer): Vorschlagswerte je Gerät berechnen
fix(hems-tab): Schutzleistung auch ohne HEMS-Wert anzeigen
docs(architektur): Datenfluss aktualisiert
```

Der Rumpf ist nur nötig, wenn das „warum" nicht aus der Betreffzeile hervorgeht.

## Ablauf je Arbeitspaket

1. Aktuellen Stand holen: `git pull --rebase`
2. Ändern, dann grün bekommen: `ruff check app` und `pytest` (siehe [test-strategie.md](test-strategie.md));
   bei Frontend-Änderungen zusätzlich `npm run build` in `frontend/`
3. [CHANGELOG.md](../CHANGELOG.md) ergänzen (Projektregel 3)
4. Version anheben, wenn die Änderung in Home Assistant sichtbar ist (siehe unten)
5. Betroffene `docs/`-Dateien im **selben** Arbeitspaket aktualisieren
6. `git status` prüfen, dann gezielt `git add`
7. Committen und pushen auf dem aktiv ausgecheckten Branch

Ein Commit bildet **eine** abgeschlossene Änderung ab. Sammelcommits über mehrere unabhängige
Themen sind nicht zulässig — sie machen ein späteres `git revert` unmöglich.

## Versionierung

Zwei Dateien tragen die Version und werden **immer gemeinsam** angehoben:

| Datei | Gelesen von |
|---|---|
| `config.yaml: version` | HA-Supervisor (Addon-Store, Update-Anzeige) |
| `app/energy_pilot/__init__.py: __version__` | `GET /api/health`, Log beim Start |

Bei **jeder** Änderung mit Auswirkung auf Darstellung, Information oder Funktion in Home Assistant
wird die Patch-Nummer um eins erhöht (`0.0.58` → `0.0.59`, Projektregel 2). Eine Drift zwischen
beiden Werten erschwert jede Fehlersuche und gilt als Fehler.

## CI

`.github/workflows/ci.yaml` läuft auf `claude/stage`, `stage-dev`, `stage-beta` und `stage-stable`
(D-024/D-053):

- Ruff-Lint über `app`
- `pytest --cov --cov-fail-under=60`
- Docker-Build als Smoke-Test
- Frontend: `tsc --noEmit` + `vite build` und Gegenprobe, dass das committete `frontend/dist/`
  zum Quellstand passt (siehe [frontend.md](frontend.md))

## Was nie passiert

- Kein `git push --force` auf gemeinsam genutzte Branches
- Kein Commit ohne vorherige Prüfung von `git status`
- Keine Secrets im Commit — vor dem Commit `git diff --staged` prüfen
- Keine generierten Artefakte im Repo — **eine begründete Ausnahme:** `frontend/dist/` wird
  mitcommittet, weil der HA-Supervisor das Addon-Image auf der Zielhardware baut und dort kein
  Node laufen soll (Begründung in [design-entscheidungen.md](design-entscheidungen.md))
