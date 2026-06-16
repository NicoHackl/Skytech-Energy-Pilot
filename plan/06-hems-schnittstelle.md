# 06 · Schnittstelle zu Skytech HEMS

> Versionierte interne Schnittstelle, über die der Energy Pilot gültige Pläne an Skytech HEMS übergibt und Statusrückmeldungen erhält.

**Status:** Entwurf · **info.md-Bezug:** §10, §13

---

## Ziel & Abgrenzung

- Klar **versionierter Vertrag** als primäre Brücke zwischen beiden Apps.
- Der Energy Pilot **steuert nie** direkt Geräte – jede reale Leistungsänderung läuft über HEMS.
- **Nicht** hier: Geräteregelung selbst (Aufgabe von HEMS), Planerzeugung (→ [05](05-planungs-engine.md)).

Modul: **Skytech HEMS Connector** + **Plan Submission**.

---

## Verwendete Services / Technologie

- **Interne, versionierte REST-API** als primärer Vertrag (HTTP über internes Add-on-Netzwerk).
- Optionaler **MQTT-Adapter** als spätere zusätzliche Transportvariante.
- Der Vertrag ist als **versioniertes Datenschema** definiert – unabhängig von einzelnen HA-Helfern.

---

## Bevorzugter Ablauf (info.md §10)

```text
1. Energy Pilot liest HA-Zustände (REST + WebSocket)
2. Energy Pilot erstellt einen Kandidatenplan
3. Lokaler Validator prüft Struktur, Wertebereiche, Zeitangaben
4. Plan wird optional simuliert
5. Gültiger Plan → über versionierte API an Skytech HEMS
6. Skytech HEMS prüft den Plan erneut
7. HEMS übernimmt nur erlaubte Parameter
8. HEMS meldet Annahme/Ablehnung/Ausführungsstatus zurück
9. Wichtige Zustände werden als HA-Entitäten sichtbar gemacht
```

> Doppelte Prüfung: Pilot validiert lokal **und** HEMS prüft erneut. HEMS bleibt die letzte Sicherheitsinstanz.

---

## Beispielhafte Endpunkte (info.md §10)

```text
POST /api/v1/strategy-plans              # neuen Plan übergeben
GET  /api/v1/strategy-plans/current      # aktuell gültigen Plan abrufen
GET  /api/v1/strategy-plans/{plan_id}    # bestimmten Plan abrufen
GET  /api/v1/system-state                # aktueller Anlagenzustand laut HEMS
GET  /api/v1/device-constraints          # technische Grenzen der Geräte
POST /api/v1/strategy-plans/{plan_id}/cancel   # Plan zurückziehen
```

Rückmeldungen von HEMS, die der Pilot verarbeitet/anzeigt:
- Annahme / Ablehnung (mit Begründung)
- aktueller Ausführungsstatus je Gerät
- ggf. nur teilweise übernommene Parameter

---

## Datenfluss

- **Pilot → HEMS:** validierter, versionierter Plan (JSON-Schema → [07](07-datenmodell.md)).
- **HEMS → Pilot:** Annahme/Ablehnung, Ausführungsstatus, `system-state`, `device-constraints`.
- **Pilot → HA:** wichtige Zustände als Entitäten (z. B. „Plan angenommen/abgelehnt", → [02](02-home-assistant.md)).

---

## Verhalten bei Ausfall (info.md §13)

1. HEMS verwendet den **letzten gültigen Plan** bis zu dessen Ablauf.
2. Nach Ablauf wechselt HEMS auf eine **lokale Standardstrategie**.
3. **Kritische harte Grenzen bleiben immer aktiv.**
4. Der Nutzer wird in HA über den Ausfall informiert.
5. Nach Wiederherstellung erstellt der Pilot einen **vollständig neuen** Plan.
6. Ein abgelaufener Plan wird **niemals** stillschweigend unbegrenzt weiterverwendet.

---

## Offene Entscheidungen

- [ ] Steht die HEMS-API schon fest, oder definieren wir sie hier gemeinsam mit dem HEMS-Projekt?
- [ ] Authentifizierung zwischen den Add-ons (Token/Shared Secret?) und Transportsicherheit
- [ ] Adressierung von HEMS (interner Add-on-Hostname/Port)
- [ ] API-Versionsstrategie (`/api/v1` → wie werden Breaking Changes gehandhabt?)
- [ ] Pull (HEMS holt Plan) vs. Push (Pilot sendet) – info.md beschreibt Push; bestätigen?
- [ ] Idempotenz/Plan-ID-Handling bei wiederholter Übergabe

---

## Aufgaben / Umsetzung

- [ ] Datenschema des Vertrags festschreiben (gemeinsam mit [07](07-datenmodell.md))
- [ ] HEMS Connector (HTTP-Client) + Auth
- [ ] Plan Submission (Senden, Statuspolling, Cancel)
- [ ] Verarbeitung von Annahme/Ablehnung + Mapping auf HA-Entitäten
- [ ] Abruf `system-state` / `device-constraints`
- [ ] Ausfall-/Fallback-Logik und Nutzerbenachrichtigung
- [ ] (später) optionaler MQTT-Adapter

---

## Bezug zu anderen Plänen

- Was übergeben wird → [05 · Planungs-Engine](05-planungs-engine.md)
- Planformat/Schema → [07 · Datenmodell](07-datenmodell.md)
- Harte Grenzen/Fallback → [08 · Sicherheit](08-sicherheit.md)
- Sichtbarkeit in HA → [02 · Home Assistant](02-home-assistant.md)
