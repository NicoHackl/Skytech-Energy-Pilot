# D-069 — Vorschläge für das HEMS in einer Schnittstellen-Entität

**Datum:** 20.10.2026 · **Status:** Aktiv · **Ändert:** D-029 (Regel 9), D-067 (Veröffentlichung)

## Kontext

Bis Vertrag 1.0 schrieb EP je Gerät und Feld einen Sensor `sensor.ep_<gerät>_<feld>_vorschlag` und
zuletzt `sensor.ep_plan_commit` als atomaren Sichtbarkeitspunkt. Der User hat am 20.10.2026 für alle
Skytech-Projekte festgelegt: Jede Einheit veröffentlicht genau eine Entität
`sensor.<einheit>_schnittstelle` mit allen Informationen für die anderen Teilnehmer.

## Entscheidung

- EP schreibt alle festen Vorschläge eines Plans in **einem** Schreibvorgang nach
  `sensor.energy_pilot_schnittstelle`. State: Präfixe der Geräte mit Vorschlägen. Attribute:
  `plan_id`, `valid_from`, `valid_until`, `schema_version`, `schnittstelle_version`, je Gerät
  `<prefix>_label` und `<prefix>_<feld>` (Planfeld ohne `_vorschlag`, echte Typen).
- Ein Schreibvorgang ist atomar; der Commit-Marker entfällt.
- `sensor.ep_plan_commit` und die Einzelsensoren werden einmal je Prozess per
  `DELETE /api/states/<id>` entfernt.
- Zusatz-Vorschläge (`sensor.ep_<obj>_vorschlag`) und die Anzeige-Entitäten
  (`sensor.ep_plan_status`, `sensor.ep_hems_verbindung`) bleiben einzeln: kein Austausch mit einer
  anderen Einheit.
- Die Richtung HEMS → EP bleibt REST.
- Regel 9 in `AGENTS.md` ist auf Anweisung des Users angepasst.

## Folgen

- EP und HEMS (ab 4.0.0) müssen zusammen aktualisiert werden; sonst wirken keine Vorschläge, das
  HEMS nimmt die Nutzerwerte.
- Dashboards, die die alten Einzelsensoren zeigten, müssen auf Attribute der Schnittstelle umgestellt
  werden.
