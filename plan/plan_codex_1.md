# Verbesserte HEMS–Energy-Pilot-Planung

## Zusammenfassung

HEMS bleibt die autoritative Quelle für Geräte, technische Grenzen, User-Einstellungen und Istzustände. Der Energy Pilot erhält diese Daten automatisch und plant rollierend stündlich mit 24–48 Stunden Ausblick. Für die erste Ausbaustufe werden keine neuen HA-Entitäten benötigt; Solarthermie bleibt eine ausdrücklich gekennzeichnete Proxy-Schätzung.

## Implementierungsänderungen

- Den bestehenden HEMS-Endpunkt `/api/device_controls_schema` abwärtskompatibel erweitern:
  - Geräteklasse, Präfix, Einheit, erlaubte Modi und Überschuss-Regelprinzip.
  - `actual_power_entity` für regelbare Geräte sowie `switch_entity` für binäre Geräte.
  - Stabile Schlüssel, Einheit und semantische Rolle aller `ems_*`-Userinputs.
- Energy Pilot übernimmt den vollständigen HEMS-Gerätevertrag. In den KI-Kontext gelangen nur planungsrelevante Werte:
  - Freigaben, Modi, Priorität, technische Min-/Max-Werte, geschützte Mindestleistung und Reserven.
  - Binäre Leistung, Mindestlauf-/Mindestauszeit und Abschaltverzögerung.
  - Istleistung, HEMS-Anforderung, tatsächlicher Zustand und die Information, dass HEMS bereits auf verfügbaren PV-Überschuss begrenzt.
  - Rampen-, Spannungs- und Phasendetails bleiben überwiegend Diagnosewerte und werden nicht unnötig in den Prompt geschrieben.
- `actual_power_entity` automatisch als historische Leistungsquelle verwenden. Bei binären Geräten Energie aus Schaltzeit und Nennleistung ableiten. Technische Grenzwerte dürfen niemals als Verbrauchsmessungen integriert werden.
- Fremdwärme nur berechnen, wenn der elektrische Heizstabeintrag belastbar herausgerechnet werden konnte. Fehlt diese Grundlage, bleiben Fremdwärme, Reichweite und Solarthermieertrag `unbekannt`.
- Solarthermie-Proxy aus bereinigter Speichertemperaturhistorie, PV-Ertrag/-Prognose und Wetter bilden. Das Ergebnis heißt fachlich „nicht-elektrische thermische Nettobilanz“, nicht gemessener Solarthermieertrag, und erhält eine Datenqualitätsbewertung.
- Bestehende Speicherwerte für Volumen, Komfortminimum und Zieltemperatur weiterverwenden. Fehlen Volumen oder Komfortminimum, wird die kWh-Bilanz deaktiviert und die Plan-Konfidenz reduziert.
- `input_number.e3dc_heizstab_maxtemperatur` bleibt eine harte, nur gelesene Nutzergrenze. Werte mit Rolle `grenze` dürfen weder KI-Vorschläge erzeugen noch ins Original zurückgeschrieben werden; bestehende widersprüchliche Flags werden per DB-Migration deaktiviert. Die strategische Zieltemperatur kommt aus den internen Speicherwerten.
- Einen internen EP-Scheduler ergänzen:
  - erster Lauf nach erfolgreicher HEMS-Discovery und erstem Messdaten-Snapshot,
  - danach gemäß `planning_interval_min`, standardmäßig stündlich,
  - Schutz gegen parallele manuelle und automatische Läufe,
  - Fehler behalten keinen abgelaufenen Plan künstlich am Leben.
- Die bisherige HA-Automation, die auf die gestoppte Stable-Instanz zeigt, nach erfolgreicher Scheduler-Inbetriebnahme deaktivieren. Die Planung hängt dann nicht mehr von einer externen Automation ab.
- HEMS lehnt fehlende, fehlerhafte oder abgelaufene Vorschläge ab und fällt feldweise auf den Nutzerwert zurück. EP veröffentlicht Vorschläge zuerst und anschließend `sensor.ep_plan_commit` als Commit-Marker mit `plan_id`, `valid_from` und `valid_until`; HEMS akzeptiert nur passende Vorschläge.
- EP publiziert nach HA-Neustart oder Wiederverbindung einen noch gültigen Plan erneut.

## Planungs- und Begründungslogik

- Das strukturierte Planergebnis erhält maschinenprüfbare Entscheidungsfaktoren, etwa `komfortreserve`, `solarthermie_proxy`, `pv_uberschussfenster`, `priorisierung`, `technische_sperre`, `nutzerregel` und `unzureichende_daten`.
- Für HEMS-Überschussverbraucher ist „Netzbezug reduzieren“ kein zulässiger Abschaltgrund. Grid-Daten bleiben Diagnose- und Batterieinformationen.
- „Zu heiß“ beziehungsweise eine Temperaturgrenze darf nur genannt werden, wenn Isttemperatur, Ziel/Grenze und prognostizierter Wärmeeintrag die Aussage numerisch tragen.
- Solarthermieentscheidung:
  - Reserve reicht einschließlich erwarteter nicht-elektrischer Erwärmung über den Horizont: Heizstab gesperrt.
  - Reserve droht vor der nächsten Solarthermiechance unter das Komfortminimum zu fallen: Heizstab freigegeben, damit HEMS vorhandenen PV-Überschuss nutzen kann.
  - Unzureichende Daten: konservative Entscheidung, niedrigere Konfidenz und keine erfundene Solarthermiebegründung.
- Ein lokaler semantischer Validator blockiert widersprüchliche Begründungen vor der Veröffentlichung.

## Tests und Abnahme

- Contract-Tests für altes und erweitertes HEMS-Schema sowie automatische Übernahme aller Gerätetypen.
- Tests für Istleistungs-/Schaltzeithistorie und die sichere Deaktivierung der Fremdwärmebilanz bei fehlender elektrischer Quelle.
- Replay-Szenarien:
  - gleicher Speicherstand, sonnige Folgetage → Heizstab gesperrt;
  - gleicher Speicherstand, schlechte Folgetage und sinkende Reserve → Heizstab für PV-Überschuss freigegeben;
  - negativer HEMS-Überschuss bei nahezu null Netzbezug → keine Netzbezugsbegründung;
  - Temperatur unter Ziel und Maximalgrenze → „zu heiß“ wird verworfen.
- Scheduler-Tests für Start, Stundenwechsel, Parallelaufrufe, Providerfehler und Neustart.
- HEMS-Tests für abgelaufene Pläne, falsche `plan_id`, fehlenden Commit-Marker und Nutzerwert-Fallback.
- Zunächst mindestens 48 Stunden im aktuellen manuellen HEMS-Modus als Shadow-Betrieb; keine automatische Umschaltung der HEMS-Modi. Danach kann der Heizstab separat in den EP-Modus übernommen werden.

## Annahmen

- Für die erste Version existiert kein verwendbarer direkter Solarthermie-, Kollektor- oder Solarpumpensensor.
- `sensor.elwa_modbus_isttemperatur` bleibt Warmwasser-Istwert und `input_number.e3dc_heizstab_maxtemperatur` die harte Obergrenze.
- Die Heizstableistung kommt automatisch über die HEMS-Konfiguration; `sensor.heizstab_energy` und andere Energiezähler müssen nicht zusätzlich im EP gepflegt werden.
- Weitere direkte HA-Sensoren werden erst nach gemeinsamer Prüfung ihrer Entitäts-ID, Einheit, Historienqualität und fachlichen Bedeutung aufgenommen.
