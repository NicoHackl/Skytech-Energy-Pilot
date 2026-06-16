# 01 · HA-Add-on / App / Docker

> Verpackung und Betrieb des Energy Pilot als eigenständige Home-Assistant-App (Add-on) in einem Docker-Container mit Ingress-Oberfläche.

**Status:** Entwurf · **info.md-Bezug:** §3, §17, §24

---

## Ziel & Abgrenzung

- Energy Pilot läuft als **eigenständiges HA-Add-on**, getrennt von Skytech HEMS.
- Eigener Container, eigene Datenhaltung, eigene UI, eigene Updates.
- **Nicht** Teil dieses Plans: Geräteansteuerung (→ HEMS), KI-Logik (→ [03](03-ki-api.md)).

Kennwerte aus der info.md:

| Eigenschaft | Wert |
|---|---|
| App-Slug | `skytech_energy_pilot` |
| Containername | `skytech-energy-pilot` |
| Repository | `Skytech-Energy-Pilot` |

---

## Verwendete Services / Technologie

- **Home Assistant Supervisor** verwaltet das Add-on (Start/Stop/Update/Backup).
- **Docker-Container** als Laufzeitumgebung.
- **Ingress** bettet die Web-UI direkt in die HA-Oberfläche ein (kein separater Port nötig).
- **Supervisor-Proxy** für den Zugriff auf die HA-Core-API (REST + WebSocket).
- **Internes App-Netzwerk** für die App-zu-App-Kommunikation mit Skytech HEMS.

Typische Add-on-Dateistruktur (Vorschlag):

```text
Skytech-Energy-Pilot/
├── config.yaml        # Add-on-Manifest: Name, Slug, Optionen, Schema, Ingress
├── build.yaml         # Basis-Images je Architektur
├── Dockerfile         # Build des Containers
├── run.sh / s6-rc     # Start-/Init-Skripte
├── apparmor.txt       # optionales Sicherheitsprofil
├── icon.png / logo.png
├── DOCS.md / CHANGELOG.md
└── app/               # eigentliche Anwendung (Backend + UI)
```

Wichtige `config.yaml`-Felder (Vorschlag):

```yaml
name: Skytech Energy Pilot
slug: skytech_energy_pilot
version: "0.1.0"
arch: [aarch64, amd64]
ingress: true
ingress_port: 8099
panel_icon: mdi:transmission-tower
hassio_api: true
homeassistant_api: true
auth_api: true
map: []            # ggf. share/config für SQLite-Datei
options: {}        # siehe Konfigschema unten
schema: {}
```

---

## Datenfluss

- **Hinein:** HA-Core-Zustände über Supervisor-Proxy (→ [02](02-home-assistant.md)); Konfiguration über die Add-on-Optionen + Ingress-UI.
- **Hinaus:** Web-UI über Ingress; Pläne an Skytech HEMS über internes Netzwerk (→ [06](06-hems-schnittstelle.md)); ausgegebene HA-Entitäten (→ [02](02-home-assistant.md)).

---

## Konfigschema des Add-ons

Erstkonfiguration über die Add-on-Optionen (UI-Detailkonfiguration später in der Ingress-Oberfläche, siehe [09](09-benutzeroberflaeche.md)). Kandidaten:

- [ ] `log_level` (debug/info/warning/error)
- [ ] `ai_provider` (openai/gemini)
- [ ] `ai_api_key` (Secret-Feld, niemals geloggt → [08](08-sicherheit.md))
- [ ] `planning_interval_min` / `full_replanning_interval_min`
- [ ] `forecast_horizon_h`
- [ ] `hems_base_url` (interne Add-on-Adresse von Skytech HEMS)
- [ ] `database_path`

> Hinweis: API-Schlüssel und Secrets gehören in geschützte Felder, nicht in normale, einsehbare Optionen.

---

## Inhalte & Details

- Add-on muss **ohne** Cloud/KI sauber starten und in einen passiven/lokalen Modus gehen können (→ [08](08-sicherheit.md), [10](10-betriebsmodi.md)).
- Persistente Daten (SQLite) müssen Add-on-Neustarts und -Updates überleben (→ [07](07-datenmodell.md)).
- Logs/Versionsstände eindeutig der App zuordenbar (Vorteil der Trennung, info.md §3).

---

## Offene Entscheidungen

- [ ] Basis-Image: offizielle HA-Base-Images (`ghcr.io/home-assistant/*-base`) vs. eigenes Slim-Image
- [ ] Init-System: **S6-Overlay** (HA-Standard) vs. einfaches `run.sh`
- [ ] AppArmor-Profil aktivieren (empfohlen für Veröffentlichung)?
- [ ] Wo liegt die SQLite-Datei: Add-on-eigenes `/data` (Standard) vs. `share`/`config`-Mount?
- [ ] Veröffentlichung über eigenes **Add-on-Repository** (HACS/Custom-Repo)?
- [ ] Ressourcenlimits (CPU/RAM) und unterstützte Architekturen (nur amd64+aarch64?)

---

## Aufgaben / Umsetzung

- [ ] Repository-Grundgerüst + `config.yaml`/`build.yaml`/`Dockerfile`
- [ ] Add-on lokal in einer HA-Testinstanz installierbar machen
- [ ] Ingress-Endpunkt mit „Hello World"-UI verdrahten
- [ ] Supervisor-Proxy-Zugriff auf HA-API verifizieren (→ [02](02-home-assistant.md))
- [ ] Persistente Datenablage einrichten (→ [07](07-datenmodell.md))
- [ ] CI/Build für die Container-Images

---

## Bezug zu anderen Plänen

- Datenanbindung an HA → [02 · Home Assistant](02-home-assistant.md)
- UI in der Ingress-Oberfläche → [09 · Benutzeroberfläche](09-benutzeroberflaeche.md)
- Persistenz → [07 · Datenmodell](07-datenmodell.md)
- Kommunikation mit HEMS → [06 · HEMS-Schnittstelle](06-hems-schnittstelle.md)
