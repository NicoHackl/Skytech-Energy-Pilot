# Bekannte Lücken & Stolpersteine

Diese Datei ist der wichtigste Startpunkt, bevor man einer alten Spec-Aussage
vertraut — Spec und Code laufen an mehreren Stellen auseinander. Bei jeder größeren
Änderung hier ergänzen/aktualisieren.

## Spec-vs-Code-Lücken (Stand aktuelle Codebasis)

### Kein automatischer Scheduler

`planning_interval_min`/`plan_update_interval_min` existieren in `config.yaml` und
den Übersetzungen, aber **kein** Code-Pfad (`main.py`, `web/server.py`, `planner.py`)
ruft `Planner.run()` je auf einem Timer auf. Ein Plan entsteht ausschließlich über
den manuellen Button/Endpunkt `POST /api/plan/run`. Das widerspricht der in
`CLAUDE.md` beschriebenen "EP plant alle 15–60 min" — wer einen Scheduler baut, muss
zusätzlich das Event-basierte Nachplanungs-Konzept (E-Auto Stecker, Abfahrtszeit-
Änderung, SOC-Ziel-Änderung, PV-/Lastprognose-Abweichung, …) aus dem alten
Decision-Log berücksichtigen ([decisions-log.md](decisions-log.md)).

### Validator-Stufe 4 (Daten-Frische) fehlt noch

Stufen 5 (Anti-Flatter/Delta-Limit + Freigabe-Hysterese + Mindesthaltezeit) und 6
(Mindestkonfidenz-Gate, `min_confidence_percent`) sind seit v0.0.51 implementiert (A2/A4).
Offen bleibt nur **Stufe 4 (Daten-Frische)**: sie braucht Zeitstempel-/Qualitäts-Mitführung
im Collector-Snapshot, die es heute nicht gibt. Siehe [validation-safety.md](validation-safety.md).

### Steuermodi/Betriebsmodi nicht verdrahtet

Siehe [control-modes.md](control-modes.md) — beide Achsen existieren nur als Spec,
kein Code wertet sie aus.

### Versions-Drift `__init__.py` vs. `config.yaml`

`app/energy_pilot/__init__.py: __version__` und `config.yaml: version` sind
**nicht synchron** — im Health-Endpoint (`GET /api/health`) zeigt sich der
`__init__.py`-Wert, im HA-Supervisor der `config.yaml`-Wert. Vor dem nächsten
Versions-Bump (Projektregel 2) beide Werte prüfen und ggf. in einem eigenen Schritt
angleichen.

### Veraltete Übersetzung

`translations/de.yaml` (und vermutlich `en.yaml`) dokumentiert noch ein Feld
`weather.onecall.llm_timeline` ("Welche Timeline… in den KI-Kontext fließt"), das im
aktuellen `config.yaml`-Schema **nicht mehr existiert** — seit die Logik auf "jedes
aktivierte Modell fließt in den Kontext" umgestellt wurde (siehe
[configuration.md](configuration.md#wetter-weather-gruppe)). Rein toter Text, keine
funktionale Auswirkung (HA ignoriert unbekannte Übersetzungs-Keys), aber verwirrend
für jeden, der die Übersetzungsdatei als Spec liest.

## Historische Stolpersteine (aus dem alten Decision-Log)

### Gemini-3.5-flash-Hang

`gemini-3.5-flash` wurde ursprünglich per Web-Recherche als existent angenommen
(Google I/O Mai 2026) und als Default gesetzt — hing in der Praxis unbegrenzt, HA-
Ingress brach mit einer HTML-Fehlerseite ab, Frontend warf
`SyntaxError: Unexpected token '<'`. Default korrigiert auf `gemini-2.5-flash`
(nutzerverifiziert). Timeout-Obergrenze auf 600 s angehoben für alle, die
`3.5-flash` trotzdem versuchen wollen. **Lehre:** KI-generierte Annahmen über
Modellverfügbarkeit vor dem Setzen als Default gegen echtes Nutzerverhalten prüfen.

### s6-overlay / SUPERVISOR_TOKEN {#s6-overlay-token-bug}

Das offizielle HA-Base-Image (s6-overlay-Init) reichte `SUPERVISOR_TOKEN` **nicht**
an den App-Prozess durch → `ha_configured=false`, keine Datensammlung möglich.
Behoben durch direkten Build auf `python:3.11-slim` mit schlichtem `CMD`, komplett
ohne HA-Base-Image/s6 (wie beim HEMS-Repo). **Lehre:** beim Docker-Setup nicht
automatisch das "offizielle" HA-Base-Image annehmen — es hat hier real ein
Token-Durchreiche-Problem verursacht.

### Addon-Startreihenfolge nicht garantiert

HA garantiert keine Startreihenfolge zwischen Addons — HEMS kann beim EP-Start noch
nicht erreichbar sein. Führte zum Auto-Retry-Mechanismus bei der Geräte-Discovery
(5×30 s). Bei jeder neuen Start-Zeit-Abhängigkeit auf ein anderes Addon: denselben
Retry-Gedanken anwenden, nicht von garantierter Reihenfolge ausgehen.

### Suffix-Übersetzungsfalle beim künftigen Direkt-Schreibweg

Siehe [entity-naming.md](entity-naming.md#stolperstein-suffix-übersetzung-beim-zukünftigen-direkt-schreibweg).

### "EP ohne HEMS ist sinnlos"-Prinzip

Der ursprüngliche Geräte-Config-Fallback wurde bewusst **ersatzlos entfernt**
(D-046): ein Fallback, der EP mit Phantom-Gerätedaten "am Leben hält", während der
einzige Abnehmer (HEMS) nicht erreichbar ist, bringt nichts. Dieses Prinzip lohnt
sich bei künftigen Fallback-Entscheidungen zu wiederholen — nicht jede Abhängigkeit
verdient einen Fallback, wenn der Downstream-Konsument ohnehin fehlt.

## Offener bekannter Bug (`upcoming_changes.md`)

**Doppelte-Priorität-Gefahr:** Steht der globale EMS-Modus auf manuell und manche
Geräte stehen im EMS auf manuell, andere auf Automatik, dann weist EP zwar jedem
Gerät eine Priorität zu, aber nur bei Geräten, die im EMS auf Automatik stehen, wird
auch die EP-Vorschlagspriorität übernommen — bei auf-manuell-stehenden Geräten gilt
die vom User über HA-Helfer eingestellte Priorität. Muss bei der Implementierung der
Steuermodi (siehe [control-modes.md](control-modes.md)) berücksichtigt werden; dieser
Eintrag kann obsolet werden, sobald M3 umgesetzt ist — dann `upcoming_changes.md`
und diesen Abschnitt gemeinsam bereinigen.
