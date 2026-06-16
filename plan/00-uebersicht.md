# 00 · Übersicht & Index

> Einstiegspunkt für alle Teilpläne von **Skytech Energy Pilot**. Hier stehen das Gesamtbild, das Glossar und die Verweise auf die einzelnen Bereichspläne.

**Status:** Entwurf · **Dokumentstand:** 16.06.2026 · **Quelle:** [info.md](../info.md)

---

## Was ist Skytech Energy Pilot?

Eine eigenständige Home-Assistant-App für die **KI-gestützte, vorausschauende Energieplanung**. Sie verbindet Home-Assistant-Daten mit externen Prognosen und einem austauschbaren KI-Dienst (OpenAI, Gemini) und erstellt daraus regelmäßig einen **strategischen Energieplan**.

Wichtig: Der Energy Pilot **regelt nicht** in Echtzeit. Er legt nur die strategischen Rahmenbedingungen fest. Die schnelle, lokale und sichere Geräteregelung übernimmt weiterhin **Skytech HEMS**.

| | Skytech Energy Pilot | Skytech HEMS |
|---|---|---|
| Aufgabe | Strategische Planung | Lokale Echtzeitregelung |
| Horizont | 24–48 h | 1–2 Sekunden |
| Intervall | 15–60 min | sekündlich |
| KI / Cloud | ja | nein (läuft autark) |
| Geräte direkt steuern | **nein** | ja |

---

## Architektur-Gesamtbild

```text
Prognosen, Ziele und Home-Assistant-Daten
                  │
                  ▼
       Skytech Energy Pilot
      strategische Planung
       alle 15–60 Minuten
                  │
                  ▼  (gültiger, versionierter Plan)
           Skytech HEMS
    lokale Regelung alle 1–2 Sekunden
                  │
                  ▼
 Speicher, Heizstab, Heizlüfter, Wallbox
```

Interne Module (siehe [info.md §17](../info.md)):

```text
Home Assistant Connector · Skytech HEMS Connector · Entity Allowlist
State Collector · History Aggregator · Forecast Manager
Device and Constraint Model · User Objective Manager · AI Provider Interface
Planning Engine · Simulation Engine · Plan Validator · Plan Submission
Monitoring and Feedback · Audit Log · Database · Ingress Web UI
```

---

## Die Teilpläne

| # | Bereich | Inhalt |
|---|---------|--------|
| [01](01-ha-addon-docker.md) | **HA-Add-on / Docker** | Verpackung als Add-on, Container, Ingress, Supervisor-Zugriff, Konfigschema |
| [02](02-home-assistant.md) | **Home Assistant** | Connector, Eingangsdaten, Entity-Allowlist, ausgegebene Entitäten |
| [03](03-ki-api.md) | **KI / API** | Provider-Interface, OpenAI & Gemini, Function Calling, Agent-Tools |
| [04](04-prognosen.md) | **Prognosen** | PV-, Last-, Wetter- und Preisprognosen, Forecast Manager |
| [05](05-planungs-engine.md) | **Planungs-Engine** | Intervalle, Planablauf, Planinhalte, Simulation, Validierung |
| [06](06-hems-schnittstelle.md) | **HEMS-Schnittstelle** | Versionierte interne API zwischen Pilot und HEMS |
| [07](07-datenmodell.md) | **Datenmodell** | Plan-JSON-Schema, SQLite, lokale Datenhaltung |
| [08](08-sicherheit.md) | **Sicherheit & Datenschutz** | Harte Grenzen, weiche Ziele, Audit, Kostenkontrolle |
| [09](09-benutzeroberflaeche.md) | **Benutzeroberfläche** | Ingress-Web-UI, Views, Bedienelemente |
| [10](10-betriebsmodi.md) | **Betriebsmodi** | Beobachten → Vorschlagen → Shadow → Autopilot |
| [11](11-roadmap.md) | **Roadmap** | Entwicklungsphasen, Ausbaustufen, Erfolgskriterien, Nicht-Ziele |

---

## Aufbau jeder Plan-Datei

Jede Datei folgt demselben Muster, damit sie als bearbeitbares Arbeitsdokument dient:

1. **Ziel & Abgrenzung** – worum geht es, was gehört *nicht* dazu
2. **Verwendete Services / Technologie** – konkrete Bausteine
3. **Datenfluss / Möglichkeiten** – was rein/raus geht, was die Oberfläche kann
4. **Inhalte & Details** – die fachliche Substanz aus der info.md
5. **Offene Entscheidungen** – `- [ ]` Punkte, die wir gemeinsam klären
6. **Aufgaben / Umsetzung** – `- [ ]` konkrete To-dos
7. **Bezug zu anderen Plänen** – Querverweise

> Die `- [ ]`-Kästchen sind zum Abhaken gedacht. Trag bei den offenen Entscheidungen gern deine Präferenz direkt ein – darauf bauen wir die Umsetzung auf.

---

## Glossar

- **Energy Pilot** – diese App; strategische Planung.
- **Skytech HEMS** – separate App; lokale Echtzeitregelung.
- **Plan / Energieplan** – strukturierter, zeitlich begrenzter, versionierter Datensatz mit Freigaben, Prioritäten, Leistungsgrenzen und Batteriezielen.
- **Harte Grenze** – technische/sicherheitsrelevante Grenze, die die KI **nie** verändern darf (z. B. max. Batterie-SOC).
- **Weiches Ziel** – gewichtetes Optimierungsziel (z. B. Netzbezug minimieren).
- **Kandidatenplan** – noch nicht validierter Planvorschlag.
- **Allowlist** – explizite Liste der HA-Entitäten, die der Pilot lesen darf.
- **Betriebsmodus** – Beobachten / Vorschlagen / Shadow / Autopilot.

---

## Offene Entscheidungen (projektweit)

- [ ] Implementierungssprache des Backends (Vorschlag: **Python**, passt zum HA-Ökosystem)
- [ ] Frontend-Technologie der Ingress-UI (siehe [09](09-benutzeroberflaeche.md))
- [ ] Wie werden Entitäten nach HA veröffentlicht? (siehe [02](02-home-assistant.md))
- [ ] Wird Skytech HEMS parallel entwickelt oder existiert es bereits als Schnittstelle?
- [ ] Lizenz & Repository-Sichtbarkeit (öffentlich/privat)
