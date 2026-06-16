# 07 · Datenmodell & Datenhaltung

> Das versionierte Energieplan-Schema und die lokale Datenhaltung der App.

**Status:** Entwurf · **info.md-Bezug:** §8, §9, §18

---

## Ziel & Abgrenzung

- **Stabiles, versioniertes JSON-Schema** für den Energieplan (Vertrag zu HEMS → [06](06-hems-schnittstelle.md)).
- **Lokale Persistenz** aller relevanten Daten.
- **Nicht** hier: Erzeugung des Plans (→ [05](05-planungs-engine.md)).

Module: **Database**, beteiligt an Validierung über **Plan Validator** ([08](08-sicherheit.md)).

---

## Verwendete Services / Technologie

- **SQLite** für die erste Version (eine Datei, einfache Sicherung).
- Später optional **PostgreSQL** für größere Setups.
- **JSON-Schema** zur Validierung jedes Plans (`schema_version`).

---

## Energieplan-Schema (Beispiel, info.md §9)

```json
{
  "schema_version": "1.0",
  "plan_id": "2026-06-16T14:00:00+02:00",
  "created_at": "2026-06-16T14:00:00+02:00",
  "valid_from": "2026-06-16T14:00:00+02:00",
  "valid_until": "2026-06-16T15:00:00+02:00",
  "strategy": "pv_self_consumption",
  "confidence": 0.86,

  "battery": {
    "minimum_soc_percent": 25,
    "target_soc_percent": 75,
    "target_time": "2026-06-16T17:00:00+02:00",
    "minimum_charge_power_w": 0,
    "maximum_charge_power_w": 3500,
    "maximum_discharge_power_w": 2500,
    "grid_charging_allowed": false,
    "reserve_for_evening_wh": 3200
  },

  "devices": {
    "wallbox": {
      "enabled": true, "mode": "surplus", "priority": 1,
      "minimum_power_w": 1380, "maximum_power_w": 4200,
      "target_energy_wh": 9000, "deadline": "2026-06-17T06:30:00+02:00",
      "grid_power_allowed": false
    },
    "heizstab": {
      "enabled": true, "mode": "surplus", "priority": 2,
      "minimum_power_w": 0, "maximum_power_w": 1800,
      "protected_minimum_power_w": 0,
      "start_not_before": "2026-06-16T14:30:00+02:00",
      "stop_not_after": "2026-06-16T17:00:00+02:00"
    },
    "heizlufter_1": { "enabled": false, "priority": 4 }
  },

  "reasoning_summary": [
    "Hohe PV-Erzeugung wird bis 16:30 Uhr erwartet.",
    "Das E-Auto benötigt bis morgen früh 9 kWh.",
    "Die Warmwassertemperatur ist bereits ausreichend.",
    "Ein Teil der Speicherkapazität soll für die Abendlast reserviert werden."
  ]
}
```

### Feldgruppen (info.md §8)

- **battery:** min/Ziel-SOC, Zielzeit, min/max Ladeleistung, max Entladeleistung, Netzladung erlaubt, reservierte Energie, Strategie.
- **devices[*]:** enabled, mode, priority, min/max Leistung, geschützte Mindestleistung, Reserve, frühester Start/spätestes Ende, benötigte Energiemenge, Zielzeit, Netzbezug erlaubt.
- **Metadaten:** plan_id, created_at, valid_from/until, verwendete Prognosen, provider+model, confidence, reasoning, Warnungen, erwartete Auswirkungen, schema_version.

---

## Zu speichernde Daten (info.md §18)

```text
Konfiguration · Entitätszuordnungen · technische Grenzen · Zielgewichtungen
verdichtete historische Werte · Prognosen · Energiepläne · Simulationsergebnisse
Planannahmen/-ablehnungen · reale Ergebnisse · Prognoseabweichungen
Fehlermeldungen · API-Nutzungsstatistik · Audit-Ereignisse
```

### Tabellen-Skizze (Vorschlag)

- `config`, `entity_map`, `device_constraints`, `objective_weights`
- `history_aggregated`, `forecasts`, `forecast_errors`
- `plans`, `plan_simulations`, `plan_submissions` (Annahme/Ablehnung/Status)
- `real_results`, `errors`, `api_usage`, `audit_log`

---

## Datenfluss

- **Schreibt:** Planungs-Engine (Pläne/Simulationen), Forecast Manager (Prognosen/Fehler), Monitoring (reale Ergebnisse), KI-Layer (API-Nutzung), alle Module (Audit/Errors).
- **Liest:** UI/History-Views, Planungskontext, Auditansicht.

---

## Versionierung & Validierung

- Jeder Plan trägt `schema_version`; Formatänderungen werden versioniert.
- **JSON-Schema-Validierung** jedes Plans vor Persistenz und vor Übergabe an HEMS.
- Alte Pläne bleiben für Audit/Vergleich erhalten.

---

## Offene Entscheidungen

- [ ] Verbindliches JSON-Schema (Datei + Versionsregeln) gemeinsam mit HEMS-Vertrag festlegen
- [ ] Einheiten-Konvention plan-weit (W & Wh, ISO-8601 mit Zeitzone) verbindlich machen
- [ ] `plan_id`-Format: Zeitstempel (wie Beispiel) vs. UUID
- [ ] Aufbewahrungsdauer/Archivierung alter Pläne, Prognosen, Audit-Einträge
- [ ] Migrationsstrategie SQLite → PostgreSQL (Abstraktion via ORM?)
- [ ] Gerätekennungen: feste Keys (`heizstab`, `heizlufter_1`, …) vs. konfigurierbare IDs

---

## Aufgaben / Umsetzung

- [ ] SQLite-Schema + Migrations-Mechanismus
- [ ] Datenzugriffsschicht (Repository/ORM)
- [ ] JSON-Schema-Datei für den Energieplan + Validator-Anbindung (→ [08](08-sicherheit.md))
- [ ] Persistenz für Pläne/Simulationen/Submissions
- [ ] Persistenz für Prognosen/Prognosefehler/reale Ergebnisse
- [ ] API-Nutzungs- und Audit-Tabellen

---

## Bezug zu anderen Plänen

- Planerzeugung → [05 · Planungs-Engine](05-planungs-engine.md)
- Vertrag zu HEMS → [06 · HEMS-Schnittstelle](06-hems-schnittstelle.md)
- Validierung/Audit → [08 · Sicherheit](08-sicherheit.md)
- Prognosen → [04 · Prognosen](04-prognosen.md)
