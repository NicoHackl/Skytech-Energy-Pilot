# Validierung & Sicherheit

## Eiserne Sicherheitsregeln (Quelle: `CLAUDE.md`, hier mit Implementierungsbezug)

1. **KI = Orchestrator, kein Regler.** Freitext ist nie ein Steuerbefehl — nur
   strukturiertes Tool/Function-Calling (`responseSchema`, siehe [planning-engine.md](planning-engine.md)).
2. **Jeder Plan wird lokal validiert** — JSON-Schema + harte Grenzen, Ablaufzeit,
   vollständiges Audit-Log. Harte Grenzen sind nie durch die KI änderbar.
3. **Kein API-Key in Logs/Entitäten** — durchgesetzt in `logging_setup.py`
   (`SECRET_KEYS`-Redaktion), `http_errors.py` (loggt nur den Pfad, nie die volle URL
   mit Query-String — relevant für OpenWeatherMap, das den Key als `appid`-Query-Param
   verlangt, siehe `onecall_client.py: masked_request_url()`), Gemini nutzt ohnehin
   Header-Auth.
4. **Datenminimum:** nur nötige, verdichtete Daten an externe KI — `plan_context.py`.
5. **Kein von KI erzeugter Code wird ausgeführt.**
6. **Fallback:** Bei Cloud-/KI-Ausfall blockiert EP nie die Anlage; HEMS läuft lokal
   weiter. Durchgängig im Code als Muster sichtbar: DB-Schreibfehler
   (`except sqlite3.Error: pass`), Allowlist-Verstoß wird nur geloggt (nie blockiert),
   OneCall-Budget-Erschöpfung überspringt weitere Calls statt zu crashen,
   Reparatur-Pass-Fehler fällt auf die deterministische Validator-Auffüllung zurück.

## Validierungs-Pipeline (`validator.py`)

| Stufe | Prüfung | Status |
|---|---|---|
| 1 | Schema — `plan_schema.schema_errors()` gegen `PLAN_JSON_SCHEMA` (Draft 2020-12, `jsonschema`-Library) | ✅ implementiert, harter Reject bei Fehler |
| 2 | Wertebereiche/Schreibvertrag je Gerät — fehlende Pflichtfelder deterministisch auffüllen, unbekanntes Feld → Fehler, Schutzleistung auf `[min_power, max_power]` geklemmt, Extra-Felder numerisch geklemmt bzw. Select-Werte außerhalb des Pools verworfen. Zusätzlich: Prioritäten werden zu einer lückenlosen 10er-Rangfolge normalisiert (`_normalize_priorities()`) | ✅ implementiert |
| 3 | Zeitlogik — `valid_from < valid_until`, Plan nicht bereits abgelaufen | ✅ implementiert |
| 4 | Daten-Frische der Eingabewerte | ❌ **nicht implementiert** (braucht Zeitstempel-/Qualitäts-Mitführung im Collector) |
| 5 | Anti-Flatter / Delta-Limit zum Vorplan (±20 % Leistung, Batterie ±10 %, D-021) + Freigabe-Hysterese (N Läufe) + Mindesthaltezeit | ✅ implementiert (v0.0.51) als reine `validator.smooth_plan()`; DB-frei, vom Planner auf gültigen Plänen aufgerufen, Pro-Gerät-Zustand in `device_plan_state` |
| 6 | Mindestkonfidenz-Schwelle (`min_confidence_percent`, Default 70) | ✅ implementiert (v0.0.51); Konfidenz unter Schwelle → Reject, Plan wird nicht veröffentlicht (fehlende Konfidenz lehnt nicht ab) |

Stufe 4 ist im Validator-Modul-Docstring weiterhin als offenes TODO markiert (Eingaben
fehlen). Stufen 5/6 greifen; die Anti-Flatter-Schicht läuft als Post-Validierungs-Glättung
(`smooth_plan()`), damit der Validator DB-frei/testbar bleibt.

**D-054:** `technische_freigabe=false` blockiert `freigabe_vorschlag=true` NICHT mehr hart
(weder als Reject in Stufe 2 noch als Sofort-Override in der Freigabe-Hysterese, Stufe 5).
Sie beschreibt nur den AKTUELLEN Ist-Zustand des Geräts, nicht dessen Verfügbarkeit im
gesamten Gültigkeitszeitraum des Plans (24–48 h). Als Fallback (fehlt das Feld im
KI-Vorschlag) dient sie weiterhin als sicherer Startwert.

## Entity-Allowlist (`allowlist.py`, D-038)

Register erlaubter Lese-Entitäten, **vollständig abgeleitet** aus drei Quellen (kein
separates manuelles Pflegen): Mess-Rollen-Mapping, Geräte-`ems_*`-Felder, PV-Prognose-
Sensoren. Durchsetzung ist **weich**: ein Lesezugriff außerhalb der Allowlist wird
geloggt/auditiert (`audit.action='allowlist_violation'`), aber **nicht blockiert** —
eine Fehlkonfiguration darf nie die Anlage stören (Fallback-Prinzip, Regel 6/8).
Wird bei jeder Geräte-Re-Discovery komplett neu aufgebaut (`rebuild()`, nicht additiv),
damit verwaiste Entitäten verschwinden. Transparenz über `GET /api/allowlist` +
Status-Tab.

## Ausfallverhalten (Sollverhalten laut Spec — Detailprüfung gegen aktuellen Code empfohlen)

1. HEMS nutzt bei EP-Ausfall den letzten gültigen Plan bis zu dessen Ablauf.
2. Nach Ablauf fällt HEMS auf eine lokale Default-Strategie zurück.
3. Kritische harte Grenzen bleiben immer aktiv.
4. User wird in HA über den Ausfall informiert.
5. Nach Wiederherstellung erstellt EP einen komplett neuen Plan.
6. Ein abgelaufener Plan wird **nie** stillschweigend unbegrenzt weiterverwendet.

Dieses Verhalten liegt größtenteils auf HEMS-Seite (separates Repo) bzw. ist von der
Übergabe-Ebene 2 (D-032, direkter Schreibweg) abhängig, die noch nicht existiert —
siehe [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md).

## Hybrid-Modus als harte Nebenbedingung

Laut Spec (D-009): im Steuermodus Hybrid werden User-fixierte Werte zu zusätzlichen
harten Nebenbedingungen — ein sie verletzender Plan ist ungültig, exakt so strikt wie
technische Grenzen. **Aktuell nicht implementiert**, siehe [control-modes.md](control-modes.md).
