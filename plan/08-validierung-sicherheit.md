# 08 — Validierung & Sicherheit

## Zweck
Garantiert, dass nur strukturierte, gültige und sichere Pläne an HEMS gelangen. Sicherheit hat Vorrang vor Optimierung.

## Verbindliche Sicherheitsregeln (info.md §13)
- Zugriff nur auf freigegebene Entitäten/Funktionen (Entity Allowlist, D-038 — **soft**: Verstöße werden protokolliert/auditiert, nicht blockiert; Register aus den Config-Quellen, siehe [01](01-homeassistant-integration.md)).
- Keine direkte Ansteuerung von Modbus/MQTT/Geräte-APIs durch das Sprachmodell.
- Strukturierte Ein-/Ausgaben; **JSON-Schema-Validierung jedes Plans**.
- Prüfung aller technischen Grenzen (harte Grenzen, siehe [07](07-planning-engine.md)).
- Ablaufzeit für jeden Plan; Ablehnung veralteter Messwerte; Erkennung fehlender Daten.
- Maximale Änderung zwischen zwei Plänen begrenzen.
- Optional notwendige Benutzerfreigabe (Modus „Vorschlagen").
- Vollständiges Audit-Log; Not-Aus und manueller Modus.
- Lokaler HEMS-Betrieb bei Cloud-Ausfall; **kein** von KI erzeugter Code wird ausgeführt.
- Kein API-Key in Logs/Entitäten; konfigurierbares Datenminimum für externe KI.

## Validierungs-Pipeline (lokal, vor Übergabe)
1. **Schema:** Plan gegen versioniertes JSON-Schema (`schema_version`) prüfen.
2. **Wertebereiche:** alle Felder gegen harte Grenzen klemmen/ablehnen.
3. **Zeitlogik:** valid_from < valid_until, Zielzeiten plausibel, nicht abgelaufen.
4. **Datenaktualität:** Eingangsmesswerte frisch genug; sonst ablehnen.
5. **Delta-Limit:** Änderung ggü. vorherigem Plan ≤ erlaubtes Maximum. **Default ±20 % Leistung / ±10 % SOC-Ziel pro Planwechsel, in Addon-Config konfigurierbar (D-021).**
6. **Konfidenz:** unter Mindestkonfidenz → kein Submit (ggf. Warnung/konservativ). **Default 70 %, in Addon-Config konfigurierbar (D-021).**
7. Ungültiger Plan wird verworfen oder korrigiert (info.md §11 Schritt 9).

**Doppelte Sicherung:** HEMS validiert den Plan beim Empfang erneut und übernimmt nur erlaubte Parameter.

## Verhalten bei Ausfall (info.md §13)
1. HEMS nutzt letzten gültigen Plan bis Ablauf.
2. Nach Ablauf → lokale Standardstrategie.
3. Kritische harte Grenzen bleiben immer aktiv.
4. User wird in HA informiert.
5. Nach Wiederherstellung erstellt EP einen vollständig neuen Plan.
6. Abgelaufener Plan wird **nie** stillschweigend unbegrenzt weiterverwendet.

## Hybrid-Modus: User-Fixierungen sind harte Vorgaben (D-009)
Im **Hybrid**-Steuermodus ([12](12-steuermodi.md)) werden vom User fixierte Werte/Gerätestatus zu **zusätzlichen harten Vorgaben** in der Validierung behandelt: Ein Kandidatenplan, der eine User-Fixierung verletzt, ist **ungültig** und wird verworfen/korrigiert — genauso streng wie technische Grenzen. Im **Automatisch**-Modus überschreiben KI-Werte die User-Eingaben (nicht aber technische Sicherheitsgrenzen).

## Betriebsmodi als Sicherheitsstufen (info.md §14)
`Beobachten → Vorschlagen → Shadow Mode → Autopilot` — siehe [roadmap.md](roadmap.md). Autopilot nur nach erprobtem Shadow Mode; jederzeit manueller Modus möglich. Abgrenzung Steuermodi vs. Betriebsmodi: [12](12-steuermodi.md).

## Audit-Log
- Jede Entscheidung, Planänderung, Annahme/Ablehnung, jeder Fehler und API-Call protokolliert (Tabelle `audit`, siehe [05](05-daten-und-speicherung.md)).
- Maschinenlesbar exportierbar (siehe [10](10-logging-observability.md)).

## Offene Punkte
- Welche Aktionen erfordern in „Vorschlagen" zwingend User-Freigabe?
- Format/Version des Plan-JSON-Schemas (gemeinsam mit HEMS pflegen).

> Geklärt (D-021): Mindestkonfidenz 70 %, Delta-Limit ±20 % Leistung / ±10 % SOC — Defaults, in Addon-Config konfigurierbar.
