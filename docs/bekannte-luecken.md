# Bekannte Lücken & Stolpersteine

Diese Datei ist der wichtigste Startpunkt, bevor man einer alten Spec-Aussage
vertraut — Spec und Code laufen an mehreren Stellen auseinander. Bei jeder größeren
Änderung hier ergänzen/aktualisieren.

## Spec-vs-Code-Lücken (Stand aktuelle Codebasis)

### Kein automatischer Scheduler

**Kein** Code-Pfad (`main.py`, `web/server.py`, `planner.py`) ruft `Planner.run()` je auf
einem Timer auf. `planning_interval_min` wird zwar gelesen, aber **nur** als
Plan-Gültigkeitsdauer (`valid_until = now + planning_interval_min`, `planner.py`) — nicht als
Takt; `plan_update_interval_min` wird nirgends gelesen. Ein Plan entsteht ausschließlich über
den manuellen Button/Endpunkt `POST /api/plan/run`. Das widerspricht der in
`AGENTS.md` beschriebenen "EP plant alle 15–60 min" — wer einen Scheduler baut, muss
zusätzlich das Event-basierte Nachplanungs-Konzept (E-Auto Stecker, Abfahrtszeit-
Änderung, SOC-Ziel-Änderung, PV-/Lastprognose-Abweichung, …) aus dem alten
Decision-Log berücksichtigen ([design-entscheidungen.md](design-entscheidungen.md)).

### `min_confidence_percent` unbenutzt

Seit Projektbeginn in der Config, im Validator-Modul-Docstring als offene "Stufe 6"
vermerkt, aber sonst im gesamten Code nirgends gelesen.

### Validator-Stufen 4–6 fehlen

Daten-Frische, Delta-Limit zum Vorplan, Mindestkonfidenz-Gate — alle drei im
`validator.py`-Docstring als TODO markiert. Siehe [sicherheit-datenschutz.md](sicherheit-datenschutz.md).

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
