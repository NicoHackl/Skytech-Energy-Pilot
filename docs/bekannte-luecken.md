# Bekannte Lücken & Stolpersteine

Diese Datei ist der wichtigste Startpunkt, bevor man einer alten Spec-Aussage
vertraut — Spec und Code laufen an mehreren Stellen auseinander. Bei jeder größeren
Änderung hier ergänzen/aktualisieren.

## Spec-vs-Code-Lücken (Stand aktuelle Codebasis)

### Ereignisbasierte Nachplanung fehlt noch

Seit D-067 plant der interne Scheduler nach erfolgreicher HEMS-Discovery und erstem Snapshot
regelmäßig gemäß `planning_interval_min` (standardmäßig stündlich). Noch nicht umgesetzt ist
zusätzliches ereignisbasiertes Nachplanen bei E-Auto-Stecker, Abfahrtszeit-/SOC-Ziel-Änderung
oder starker PV-/Lastprognose-Abweichung. Bis dahin greift eine solche Änderung spätestens im
nächsten regulären Lauf; der manuelle Endpunkt bleibt verfügbar.

### Validator-Stufe 5 (Delta-Limit) fehlt — bewusst

Daten-Frische (Stufe 4) und Mindestkonfidenz (Stufe 6) sind seit D-064 implementiert,
`min_confidence_percent` wird ausgewertet. **Stufe 5** (Delta-Limit zum Vorplan, ±20 %
Leistung / ±10 % SOC-Ziel, D-021) bleibt offen, und zwar absichtlich: nachgelagerte Dämpfung
der KI-Ausgabe ist als Ansatz verworfen (D-060) — Stabilität soll im Aufruf entstehen, nicht
dahinter. Siehe [sicherheit-datenschutz.md](sicherheit-datenschutz.md).

### PV-Prognose reicht nur bis morgen

Die konfigurierten Sensoren liefern vier Summenwerte — laufende Stunde, nächste Stunde, Rest
heute, morgen (D-026, Werte im State statt als Attribut). Es gibt **keine** Stundenkurve und
**keinen** Tag 3. Für spätere Tage bleibt nur die Ableitung „Bewölkung gegen gemessenen Ertrag"
aus dem Rückblick (D-065); der Kontext sagt das ausdrücklich (`forecast.horizont`), damit ein
Modell keine Erträge für übermorgen erfindet. Wer den Horizont wirklich verlängern will, braucht
eine Prognose-Integration, die mehr Tage liefert.

Zweiter Punkt am selben Ort: `weather.uvi` liefert OpenWeatherMap je Tag, der Parser verwirft es
(`weather.py`). Als Solarthermie-Proxy wäre es deutlich besser als Bewölkung allein — der erste
Hebel, falls die Einschätzung von Tag 3 in der Praxis nicht trägt.

### Langzeitstatistiken fehlen für die meisten Sensoren

Der Tages-Rückblick (D-065) baut auf der **Roh**-Historie auf, weil die Statistik-API zu wenige
der gebrauchten Sensoren abdeckt: Speicherfühler und die E3DC-Leistungssensoren haben kein
`state_class` und damit keine Tagesstatistiken (live geprüft 17.08.2026). EPs eigene Tabelle
wächst zwar über die ~10 Tage Recorder-Aufbewahrung hinaus, startet aber nur mit dem, was der
Recorder hergibt. Ein `state_class: measurement` per Customize auf diesen Sensoren macht den
Rückblick dauerhaft belastbarer — das ist eine Änderung in HA, nicht im Addon.

### Determinismus hängt am Modell, nicht an der Einstellung

`ai_temperature`/`ai_seed` erreichen nur **Gemini und OpenAI** die API; Claude bekommt keine
Sampling-Parameter. Reasoning-Modelle wie `gpt-5` lehnen sie ab — EP wiederholt dann ohne, und
die eingestellte Temperatur 0 wird faktisch zum Anbieter-Default. Seit D-063 ist dieser Fall
sichtbar (Warnung im Log, `ai_calls.sampling_dropped`, Hinweis im Plan-Tab), aber er
verschwindet dadurch nicht. Wer Reproduzierbarkeit braucht, braucht ein Modell, das die
Parameter annimmt — plus die Kontext-Quantisierung, ohne die ein Seed ohnehin wirkungslos ist.

### Modellverfügbarkeit ist nicht prüfbar, ohne sie zu probieren

Gilt weiter die Lehre aus dem `gemini-3.5-flash`-Hang unten: **kein** Modellname wird als
Default gesetzt, ohne dass ein echter Planungslauf damit nachweislich durchgelaufen ist. Das
betrifft auch neuere Namen wie `gemini-3.1-flash-lite`.

### Steuermodi/Betriebsmodi nicht verdrahtet

Siehe [steuermodi.md](steuermodi.md) — beide Achsen existieren nur als Spec,
kein Code wertet sie aus.

### Kein Auto-Export des Log-Bundles bei ERROR/CRITICAL

D-014 fordert den automatischen Export eines KI-lesbaren Log-Bundles, sobald ein
ERROR/CRITICAL auftritt. Implementiert ist nur der **manuelle** Weg: `GET /api/logs/export`
(JSONL) bzw. der Button im Logs-Tab. `logging_setup.py` kennt keinen Trigger auf Log-Level.

### Keine HEMS↔EP-Contract-Tests

D-015 verlangt, dass die CI mindestens das HEMS↔EP-Zusammenspiel testet. Vorhanden sind
Unit-Tests gegen einen gemockten HTTP-Client (`test_hems_client.py`, `test_web_hems.py`),
aber **keine** dedizierte Contract-Suite gegen ein Mock-HEMS, die das Antwortformat von
`/api/device_controls_schema` und `/api/status` als Vertrag festschreibt. Wer die Discovery
oder das Status-Parsing anfasst, hat also kein Netz gegen HEMS-seitige Formatänderungen.

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

Siehe [namensschema.md](namensschema.md#stolperstein-suffix-übersetzung-beim-zukünftigen-direkt-schreibweg).

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
Steuermodi (siehe [steuermodi.md](steuermodi.md)) berücksichtigt werden; dieser
Eintrag kann obsolet werden, sobald M3 umgesetzt ist — dann `upcoming_changes.md`
und diesen Abschnitt gemeinsam bereinigen.
