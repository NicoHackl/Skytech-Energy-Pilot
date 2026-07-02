# 05 — Daten & Speicherung

## Zweck
Lokale Datenhaltung (SQLite für V1) + Verdichtung von Live-/Historiendaten vor KI-Übergabe.

## Speicherinhalte (info.md §18)
- Konfiguration, Entitätszuordnungen, technische Grenzen, Zielgewichtungen.
- Verdichtete historische Werte, Prognosen.
- Energiepläne, Simulationsergebnisse, Planannahmen/-ablehnungen.
- Reale Ergebnisse, Prognoseabweichungen, Fehlermeldungen.
- API-Nutzungsstatistik, Audit-Ereignisse.

Spätere Option: externe DB (PostgreSQL).

## Mittelwertbildung (D-001, D-003)
- EP erhält **Live-Werte**, bildet selbst gleitende Mittel.
- **Drei feste Fenster parallel: 1 / 15 / 60 min.** Keine Ereigniskopplung über die Mittel.
- **Gemittelt:** PV-Leistung, Hausverbrauch, Netzbezug/-einspeisung, Batterieleistung, Ist-Leistungen.
- **Letzter gültiger Wert:** SOC, Temperaturen, Zeiten, Zustände/Verfügbarkeit, Modi.
- **Langzeitprognose nutzt ausschließlich die 60-min-Summierung** (D-012). Speicherstruktur von Anfang an auf 1/15/60 min ausgelegt.

## Verdichtung für Historie (info.md §6.2)
- 15-min-Mittelwerte, Verbrauch letzte 24 h, typische Lastprofile (Wochentag/Uhrzeit), PV-Ertrag vergleichbarer Tage, bisherige Prognosefehler, SOC-Verlauf, Laufzeiten flexibler Verbraucher, benötigte Energiemengen, erreichte/verfehlte Ladeziele.
- **Niemals** die vollständige HA-DB an externe Dienste.

## SQLite-Schema (Entwurf, iterativ)
```
config(key, value, updated_at)
entity_map(role, ha_entity_id, fallback_value, averaging_window_s, is_averaged)
device_extras(device_name, read_entity_id, ai_suggestion, ai_hint, label, unit, sort_order)  -- Zusatz-Entitäten je Gerät (D-047), Migration 6
device_constraints(device, key, value_num, value_text, source, updated_at)
objectives(name, weight, is_hard, updated_at)
samples_raw(ts, entity_id, value)               -- kurzer Ringpuffer
samples_agg(ts_bucket, entity_id, window_s, mean, min, max, n)  -- window_s ∈ {60, 900, 3600}
forecasts(ts, kind, horizon, payload_json, source)
plans(plan_id, schema_version, created_at, valid_from, valid_until,
      strategy, confidence, status, payload_json)
plan_results(plan_id, ts, metric, planned, actual)
simulations(plan_id, ts, payload_json)
ai_calls(ts, provider, model, tokens_in, tokens_out, est_cost, ok, error)
audit(ts, actor, action, subject, detail_json)
errors(ts, level, component, message, detail_json)
```

## Aufbewahrung / Pruning (D-012 — empfohlene Defaults, später per Config erweiterbar)
| Daten | Default-Retention |
|-------|-------------------|
| `samples_raw` | ~6 h |
| 1-min-agg | ~7 Tage |
| 15-min-agg | ~90 Tage |
| 60-min-agg | ~13 Monate |
| Pläne / Audit | ~13 Monate |
- Werte so gewählt, dass die Prognose-/Vergleichszeiträume eingehalten werden; später ausbaubar.
- `reset_learning_data`-Action löscht Lern-/Historiendaten (nicht die Konfig).

## Datenschutz
- Keine persönlichen Namen, keine unnötigen Entitäten an KI.
- Vor Übertragung verdichten; API-Keys geschützt.

## Offene Punkte
- Größenbudget der SQLite-DB im Addon-Container (Retention-Defaults oben sind Startwerte).
