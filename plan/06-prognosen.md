# 06 — Prognosen (Forecast Manager)

## Zweck
Stellt strukturierte Prognosen für die Planung bereit. Externe Daten werden durch EP/HA-Integrationen **strukturiert abgerufen** — das Sprachmodell recherchiert nichts selbst im Internet (info.md §6.3).

## Prognosearten (V1-Fokus, D-018)
```
Forecast Manager
├── PV Forecast               # PV-Erzeugungsprognose  ← V1: einzige externe Quelle
├── Load Forecast             # Lastprognose aus Historie/Lastprofilen (intern)
├── Weather Forecast          # OpenWeatherMap, direkt im EP (D-042); Quelle umschaltbar 3h5day/OneCall-4.0 (D-044) – V1: nur EP-intern
└── Electricity Price Forecast# VORERST RAUS – kein dynamischer Tarif beim User
```

## Quellen (D-006, D-018)
- **PV-Prognose:** der User pflegt die **bestehenden HA-Sensoren** in der **Addon-Config**.
  - **WICHTIG:** je Typ **mehrere Sensoren** konfigurierbar (mehrere PV-Ausrichtungen) → EP **summiert** sie.
  - Vier Werte: **Energie aktuelle Stunde, Energie nächste Stunde, Energie verbleibend heute, Energie morgen**.
  - **Jeder Wert liegt direkt im State eines eigenen Sensors** (kein Attribut, D-026) → in der Addon-Config also je Wert (und je Ausrichtung) ein Entitätsname.
- **Strompreis:** in V1 **weggelassen** (kein dynamischer Tarif). Architektur so halten, dass eine Preisquelle später ohne Umbau ergänzbar ist.
- **Wetter (D-042):** **direkt im EP** über die OpenWeatherMap-„5 day / 3 hour forecast"-API abgerufen (eigene externe Quelle, **nicht** über HA-Sensoren wie die PV-Prognose).
  - Koordinaten aus einer **HA-Zone** (`zone.*`, Attribute `latitude`/`longitude`); API-Schlüssel + Parameter (`units`, `lang`, `refresh_min`) in der Addon-Config-Gruppe `weather`. Schlüssel wird nie geloggt (Iron Rule 6).
  - Module `weather.py`/`weather_client.py`/`weather_collector.py`; Endpoint `GET /api/weather`; Wetter-Block im Prognose-Tab. Abruf gedrosselt auf `refresh_min` (Default **60 min**, W3/D-044).
  - **KI-Kontext (D-043):** Wetter fließt in die Planung ein; Detailgrad in der Addon-Config umschaltbar (`weather.llm_detail`: `compact` = Temp/Bewölkung/Regen-W. bis Horizont; `full` = volle 5 Tage, alle Felder).
  - **Quelle umschaltbar (D-044):** `weather.source` = `forecast3h` (5-Tage/3-Stunden, **Default**) **oder** `onecall` (**One Call API 4.0**, Abo „One Call by Call" nötig). Bei `onecall` getrennte Timelines **15min/1h/1day** über `onecall_client.py`/`OneCallCollector`, je einzeln aktivierbar mit **eigenem Refresh-Intervall** (`weather.onecall.enable_*`/`refresh_*`). KI-Timeline konfigurierbar (`weather.onecall.llm_timeline`, Default `1h`).
  - **Pagination + Budget (D-045, O2):** je Timeline **1–5 paginierte Seiten** je Refresh (`pages_*`, Default 1 = erste Seite; jede Seite = ein bezahlter Call, folgt dem `next`-Cursor). **Pflicht-Schutz** gegen Kontingent-Überschreitung: harte **Tages-Call-Obergrenze** (`daily_call_budget`, Default 1000) über **alle** bezahlten One-Call-Anfragen (Timelines + Alerts), in **UTC** gezählt, persistent über den KV-Speicher (`config`/`/data`) → auch ein Neustart umgeht das Limit nicht. Erschöpft ⇒ Abrufe werden übersprungen (Iron Rule 8), auditiert, im UI angezeigt. Modul `onecall_budget.py`.
  - **Unwetter-Alerts (D-045, O3):** behördliche Warnungen über `fetch_alerts` (`enable_alerts`, Default an; `refresh_alerts`, Default 30 min), Dataclass `OneCallAlert`. Vorerst **nur Daten/Anzeige** — noch keine Einspeisung in die Planung (Zukunft: z.B. Batterie-Priorisierung bei drohendem Gewitter).
  - **V1-Scope:** **Noch nicht** als HA-Sensor und **nicht** über die HEMS-API (eigener späterer Schritt). Verbleibende One-Call-Punkte (current-Ist-Wetter, mehrere Timelines ans LLM, Historie) → claude-fragen-v10 (geparkt O1/O4/O5).
- **Lastprognose** primär **intern** aus verdichteter Historie (typische Profile nach Wochentag/Uhrzeit, basierend auf 60-min-agg, siehe [05](05-daten-und-speicherung.md)).

## Verarbeitung
- Prognosen werden normalisiert (Zeitraster, Einheiten) und in `forecasts` gespeichert.
- **Prognosefehler** werden laufend gegen Realität gemessen (Monitoring/Feedback) und für künftige Planungen genutzt.
- Qualität/Aktualität der Quellen wird bewertet und in der UI angezeigt.

## Nutzung in der Planung
- Eingabe für Planning Engine + Simulation (Horizont 24–48 h).
- Bei fehlenden/veralteten Prognosen: Konfidenz senken, Warnung erzeugen, ggf. konservative Strategie.

## UI-Anzeige (siehe [09](09-ui-ingress.md))
PV-Prognose, Lastprognose, Wetter, Strompreise, Prognoseabweichungen, Datenquellen-Qualität.

## Offene Punkte
- Mindestqualität, ab der ein Plan überhaupt erstellt wird.

> Geklärt (D-026): 4 PV-Werte je als eigener Sensor-State (kein Attribut), mehrere Sensoren pro Ausrichtung summierbar.
