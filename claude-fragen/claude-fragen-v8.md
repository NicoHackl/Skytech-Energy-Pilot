# Claude-Fragen — v8 (Stand 25.06.2026)

> Neue Fragen rund um die **Wettervorhersage (OpenWeatherMap)**, die ich in v0.0.17 direkt
> in den Energy Pilot integriert habe. Die **B-Fragen aus [claude-fragen-v7.md](claude-fragen-v7.md)
> (B1–B4) sind weiterhin offen** und gelten unverändert weiter — sie sind hier nicht dupliziert.
> Format wie gehabt: Antwort direkt unter die Frage; ich übernehme sie danach nach
> [../plan/entscheidungen.md](../plan/entscheidungen.md) und entferne sie in v9.

---

## Was bereits umgesetzt ist (zur Einordnung)
- OWM „5 day / 3 hour forecast" wird **direkt im EP** abgerufen (`weather_client.py`).
- Koordinaten aus einer **HA-Zone** (Default `zone.home`, Attribute `latitude`/`longitude`).
- API-Schlüssel + Parameter in der Addon-Config-Gruppe `weather` (Schlüssel wird **nie geloggt**).
- Abruf gedrosselt auf `refresh_min` (Default 30 min); Daten read-only via `GET /api/weather` + UI-Block.
- **Bewusst noch nicht:** keine HA-Sensoren, keine HEMS-Übergabe, **keine** Einspeisung in den KI-Kontext.

---

## W — Wetter

### W1 — Wetterdaten in den KI-Planungskontext aufnehmen? *(wichtigste Frage)*
Bisher sagen [info.md](../info.md) §6 und [plan/06-prognosen.md](../plan/06-prognosen.md): „Wetter in V1 nicht für die KI nötig (PV-Prognose deckt die Erzeugung ab)". Deine neue Vorgabe ist „Daten **aktuell nur im Energy Pilot** benötigt" — das habe ich als **Sammeln + Anzeigen (UI/API)** umgesetzt, **ohne** den KI-Prompt (`plan_context.py`) zu verändern (Datenminimum, Iron Rule 7; Token-Budget; Antwort-Schema bleibt schlank).
**Frage:** Sollen die Wetterdaten **jetzt schon** in den KI-Kontext (`build_context`) einfließen, oder bleibt es vorerst bei reiner EP-interner Anzeige? Falls einfließen: welche Felder (Empfehlung: **Bewölkung `clouds` + Niederschlagswahrscheinlichkeit `pop` + Temperatur**, da PV-/Last-relevant) und über welchen Horizont (Empfehlung: nur bis `forecast_horizon_h`, nicht alle 5 Tage)?

Antwort:

### W2 — Zeitraster: 3-Stunden-Schritte direkt nutzen?
OWM liefert die 5-Tage-Prognose in **3-Stunden-Schritten** (40 Werte). Das passt nicht zum 1/15/60-min-Mittelungsschema der Messgrößen (D-001), ist aber für den Planungshorizont 24–48 h ausreichend.
**Frage:** 3-Stunden-Raster **unverändert** übernehmen (meine aktuelle Umsetzung), oder soll EP auf z.B. stündlich **interpolieren**? — Empfehlung: 3h-Raster direkt, keine Interpolation.

Antwort:

### W3 — Defaults Einheiten/Sprache/Refresh bestätigen
Aktuelle Defaults: `units=metric` (°C, m/s), `lang=de` (lokalisierte Wetterbeschreibung), `refresh_min=30` (OWM-Forecast ändert sich serverseitig nur alle paar Stunden — häufigere Abrufe wären reine Verschwendung).
**Frage:** Passen diese Defaults so? Insbesondere `refresh_min=30` ok, oder lieber seltener (z.B. 60)?

Antwort:

### W4 — Koordinatenquelle: Zone vs. HA-Kernstandort
Ich lese Länge/Breite aus der **HA-Zone** (`zone.home`), wie von dir vorgegeben. HA hat zusätzlich einen globalen Standort (`config/latitude`,`longitude`).
**Frage:** Bei `zone.home` als Default bleiben (so umgesetzt) — oder soll der globale HA-Standort als zusätzlicher **Fallback** dienen, falls die Zone keine Koordinaten hat? — Empfehlung: vorerst nur Zone, klare Fehlermeldung bei fehlenden Koordinaten.

Antwort:

### W5 — Behaltene Wetterfelder
Ich normalisiere je Schritt: `temp`, `feels_like`, `clouds`, `pop`, `wind_speed`, `humidity`, `rain_3h`, `snow_3h`, `condition`/`condition_id`. Verworfen: Druck, Sicht, Windrichtung/-böen, temp_min/max.
**Frage:** Reicht dieser Satz, oder fehlt etwas Energierelevantes (z.B. Windrichtung für spätere Windkraft)?

Antwort:

### W6 — Spätere Bereitstellung (HA-Sensoren / HEMS) als eigener Schritt
Du hast „**aktuell** noch nicht als HA-Sensoren oder über die interne API an das HEMS" gesagt — ich habe das daher bewusst ausgelassen (analog zur Staffelung der Vorschlagssensoren M2/M3).
**Frage (nur Bestätigung):** Wetter-als-HA-Sensor und Wetter-über-HEMS-API kommen als **eigener, späterer Meilenstein** — keine sofortige Aktion?

Antwort:
