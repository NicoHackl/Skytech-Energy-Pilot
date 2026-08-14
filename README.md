# Skytech Energy Pilot

Home-Assistant-Addon für KI-gestützte, vorausschauende strategische Energieplanung (Horizont 24–48 h).
Es plant Priorität, Freigabe und Schutzleistung je Gerät als Vorschlag — geregelt wird weiterhin vom
[Skytech HEMS](https://github.com/NicoHackl/SkytechHEMS).

**EP plant, HEMS regelt.** EP steuert nie ein Gerät direkt: es schreibt seine Vorschläge als
`sensor.ep_*_vorschlag` nach Home Assistant. Fällt EP oder die KI aus, regelt das HEMS lokal
unverändert weiter.

## Installation in Home Assistant

Das Repo wird als Addon-Repository per Branch-URL hinzugefügt — je Release-Kanal einmal:

| Kanal | URL |
|---|---|
| Dev | `https://github.com/NicoHackl/Skytech-Energy-Pilot#stage-dev` |
| Beta | `https://github.com/NicoHackl/Skytech-Energy-Pilot#stage-beta` |
| Stable | `https://github.com/NicoHackl/Skytech-Energy-Pilot#stage-stable` |

Danach das Addon installieren, in den Optionen mindestens den KI-Anbieter samt Schlüssel und die
`hems_base_url` setzen (z. B. `http://local_skytech_hems:8099`) und starten. Die Oberfläche liegt
als Ingress-Panel in der HA-Seitenleiste.

Die HA-Helfer legt EP **nicht** selbst an — fertige Pakete liegen in
[`claude-ha-config-dateien/`](claude-ha-config-dateien/).

## Nutzung

Neun Bereiche in der Oberfläche: **Status** (Verbindungen, Version), **Daten** (Messwerte mit
1/15/60-min-Mittel), **Geräte** (vom HEMS erkannte Geräte, Zusatz-Entitäten, KI-Beschreibung),
**Prognose** (PV und Wetter), **Grenzen & Ziele** (abgeleitete harte Grenzen, eigene Ziele),
**Plan** (Planungslauf auslösen, Prompts bearbeiten, Ergebnis prüfen), **HEMS**
(Status-Rückkopplung, Geräte-Sync), **Einstellungen** und **Logs**.

Ein Plan entsteht heute ausschließlich über den Knopf im Plan-Tab — einen automatischen Scheduler
gibt es noch nicht (siehe [docs/bekannte-luecken.md](docs/bekannte-luecken.md)).

## Entwicklung

```bash
pip install -r app/requirements-dev.txt   # Backend-Abhängigkeiten
pytest                                    # Tests
ruff check app                            # Linting

cd frontend && npm install                # Frontend-Abhängigkeiten
npm run build                             # Typprüfung + Bündel nach frontend/dist/
```

Vor dem ersten Commit lesen: [CONTRIBUTING.md](CONTRIBUTING.md).

## Dokumentation

| Wofür | Wo |
|---|---|
| Verbindliche Projektregeln (Menschen **und** KI-Agenten) | [AGENTS.md](AGENTS.md) |
| Technische Referenz | [docs/README.md](docs/README.md) |
| Änderungen je Version | [CHANGELOG.md](CHANGELOG.md) |

## Lizenz

Privates Projekt, keine Lizenz erteilt.
