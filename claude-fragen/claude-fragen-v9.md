# Claude-Fragen — v9 (Stand 26.06.2026)

> **STATUS (verarbeitet 26.06.2026):** O1–O5 beantwortet. **O2/O3 umgesetzt → Decision Log D-045**
> (v0.0.22: Pagination 1–5 + Pflicht-Tages-Call-Budget; Unwetter-Alerts). **O1/O4/O5 für die
> Zukunft geparkt** → [claude-fragen-v10.md](claude-fragen-v10.md). Diese Datei bleibt als Q&A-Historie.

> Neue offene Fragen rund um die **OpenWeatherMap One Call API 4.0**, die ich in v0.0.21 als
> **opt-in-Alternative** zur bestehenden „5 day / 3 hour forecast"-API integriert habe.
> Die **B-Fragen aus [claude-fragen-v6.md](claude-fragen-v6.md) (B1–B4)** sind weiterhin offen und
> gelten unverändert weiter — sie sind hier nicht dupliziert.
> Format wie gehabt: Antwort direkt unter die Frage; ich übernehme sie danach nach
> [../plan/entscheidungen.md](../plan/entscheidungen.md) und entferne sie in v10.

---

## Was bereits umgesetzt ist (zur Einordnung) — One Call API 4.0 (D-044)
- Neuer Config-Umschalter `weather.source`: `forecast3h` (**Default**, unverändert) oder `onecall`.
- Bei `onecall`: getrennte Timelines **15min** (`timeline/15min`), **1h** (`timeline/1h`),
  **1day** (`timeline/1day`) je einzeln aktivierbar mit **eigenem Abruf-/Refresh-Intervall**
  (`weather.onecall.refresh_15min` / `refresh_1h` / `refresh_1day`).
- **Nur erste Seite** je Timeline pro Refresh (keine Pagination) → 1 bezahlter Call/Timeline/Refresh;
  deckt ~12,5 h (15min) / ~20 h (1h) / 10 Tage (1day) ab.
- Welche Timeline ins LLM geht, ist konfigurierbar (`weather.onecall.llm_timeline`, Default `1h`).
- **Hinweis:** One Call API 4.0 erfordert das kostenpflichtige Abo „One Call by Call" (1000 Calls/Tag
  frei). `forecast3h` bleibt der schlüssel-/abofreie Default-Pfad.
- **Bewusst noch nicht:** kein `current`-Ist-Wetter, keine Pagination, keine Unwetter-Alerts,
  kein Tages-Call-Budget-Zähler, keine HA-Sensoren/HEMS-Übergabe.

---

## O — One Call API 4.0

### O1 — `current` (Ist-Wetter) zusätzlich abrufen?
Die 4.0-API bietet neben den Timelines einen `current`-Endpunkt (aktuelles Wetter). Ich habe ihn
**bewusst weggelassen** (Datenminimum; ein zusätzlicher Call je Refresh).
**Frage:** Soll das Ist-Wetter (`current`) zusätzlich abgerufen und in UI/KI-Kontext angezeigt werden,
oder reichen die Forecast-Timelines? — Empfehlung: vorerst nur Timelines.

Antwort: vorerst nicht implementieren, aber für die Zukunft im Hinterkopf lassen

### O2 — Tiefer als die erste Seite paginieren (+ Call-Budget-Schutz)?
Aktuell wird je Timeline **nur die erste Seite** geholt (15min ≈ 12,5 h, 1h ≈ 20 h). Für den vollen
48-h-Horizont in 15-min-Auflösung wären ~4 paginierte Calls nötig (jede Seite = eigener bezahlter Call).
**Frage:** Soll später eine **konfigurierbare Seitenzahl/Horizonttiefe** je Timeline ergänzt werden —
und falls ja, mit einem **Tages-Call-Zähler** als Schutz gegen versehentliches Überschreiten der
1000 Calls/Tag? — Empfehlung: erst bei konkretem Bedarf, dann mit Budget-Zähler.

Antwort: wir machen es das man zwischen 1-5 paginierte Calls auswählen kann und **GANZ WICHTIG** es **MUSS** ein Schutz für die 1000 Calls/Tag eingebaut sein

### O3 — Unwetter-Alerts auswerten?
Die 4.0-API liefert behördliche Unwetterwarnungen (`alert/{alert_id}`). Aktuell ungenutzt.
**Frage:** Sind Alerts energierelevant genug, um sie anzuzeigen / in den KI-Kontext zu nehmen
(z.B. Sturm/Hagel → PV-Schutz)? — Empfehlung: optionaler späterer Meilenstein.

Antwort: wir nhemen die Daten definitv mal mit auf, vorallem für den Zukunftsaspekt das man dann z.b. die Batterieladung stärke priorisieren kann wenn ein gewitter droht und somit ein möglicher stromausfall

### O4 — Mehrere Timelines gleichzeitig ans LLM?
Derzeit fließt **genau eine** Timeline (`llm_timeline`, Default 1h) in den KI-Kontext (Token-Budget).
**Frage:** Soll die KI später **kombiniert** Fein- + Grob-Auflösung bekommen (z.B. 1h bis Horizont
**plus** 1day-Ausblick), oder bleibt es bei einer Timeline? — Empfehlung: vorerst eine Timeline.

Antwort: vorerst eine timeline, aber ich kann mir für die Zukunft sehr gut vorstellen z.b. 15 min timeline für 3h und die 1h stunden timeline für 2 tage etc.

### O5 — Historische Daten (47 Jahre) später für PV-Kalibrierung?
Die 4.0-API kann auch weit zurückliegende Verläufe liefern. Aktuell ausschließlich Forecast genutzt.
**Frage:** Ist historischer Abruf (z.B. zur Kalibrierung der PV-Erwartung) ein späteres Thema, oder
dauerhaft außerhalb des EP-Scopes? — Empfehlung: außerhalb V1-Scope, später prüfen.

Antwort: im aktuellen Scope ist es für uns defintiv kein Thema, da es einen geringen einfluss haben wird, für v2+ kann ich es mir sehr gut vorstellen das wir irgedwas in diese richtung noch machen werden
