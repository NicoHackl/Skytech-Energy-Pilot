# Validierung & Sicherheit

## Eiserne Sicherheitsregeln (Quelle: [`AGENTS.md`](../AGENTS.md), hier mit Implementierungsbezug)

1. **KI = Orchestrator, kein Regler.** Freitext ist nie ein Steuerbefehl — die Antwort wird
   über ein **erzwungenes JSON-Schema** strukturiert (`responseSchema` bei Gemini,
   `output_config.format` bei Claude, `response_format` mit Strict bei OpenAI; siehe
   [planungs-engine.md](planungs-engine.md)). Der Mechanismus ist **JSON-Mode/structured
   output**, nicht Tool-/Function-Calling: `tools`/`tool_choice` verwendet EP nirgends. Die
   Sicherheitswirkung ist dieselbe (kein Freitext als Befehl), die frühere Formulierung
   benannte aber den falschen Mechanismus.
2. **Jeder Plan wird lokal validiert** — JSON-Schema + harte Grenzen, Ablaufzeit,
   vollständiges Audit-Log. Harte Grenzen sind nie durch die KI änderbar.
   Seit D-063 ist das Audit tatsächlich vollständig: neben `{ok, errors, clamped}` in `audit`
   speichert `plans` je Lauf auch `prompt`, `context_json`, `response_json` und `context_hash`.
   Vorher war ein Lauf nachträglich nicht reproduzierbar — die Zusage stand in der Doku, im
   Code fehlte sie.
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
| 4 | Daten-Frische — jeder Kontextwert trägt `veraltet`, `datenlage.frische_prozent` zählt den belegten Anteil; die `datenlage`-Teilnote des Modells wird dagegen gedeckelt (`min(Modell, EP)`, Abweichung als Klemmung protokolliert) | ✅ implementiert (D-064) |
| 5 | Delta-Limit zum Vorplan (Default ±20 % Leistung / ±10 % SOC-Ziel, D-021) | ❌ **bewusst nicht implementiert** — nachgelagerte Dämpfung der KI-Ausgabe ist als Ansatz verworfen (D-060); Stabilität entsteht im Aufruf, nicht dahinter |
| 6 | Mindestkonfidenz — Teilnoten als schwächstes Glied aggregiert, unter `min_confidence_percent` (Default 70) wird `publish_blocked` gesetzt | ✅ implementiert (D-064) |

**Wichtig zur Abgrenzung:** Stufe 6 macht einen Plan **nicht ungültig**. Er bleibt `ok`,
wird gespeichert und angezeigt — nur der HA-Schreibweg entfällt, mit Begründung in
`sensor.ep_plan_status` und im Plan-Tab. Ein am Gate gescheiterter Plan wird auch nicht
wiederverwendet (der Hash-Vergleich in `planner._reusable_plan` verlangt einen gültigen,
noch laufenden Plan).

Stufe 5 bleibt offen und ist der einzige verbliebene TODO-Punkt im Validator-Docstring.

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
siehe [bekannte-luecken.md](bekannte-luecken.md).

## Hybrid-Modus als harte Nebenbedingung

Laut Spec (D-009): im Steuermodus Hybrid werden User-fixierte Werte zu zusätzlichen
harten Nebenbedingungen — ein sie verletzender Plan ist ungültig, exakt so strikt wie
technische Grenzen. **Aktuell nicht implementiert**, siehe [steuermodi.md](steuermodi.md).
