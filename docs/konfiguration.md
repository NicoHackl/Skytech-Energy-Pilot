# Addon-Konfiguration

Leitprinzip: so gut wie **alles** ist in der Addon-Config einstellbar. Defaults
kommen von Claude, sind aber immer überschreibbar. `config.py: AddonConfig.load()`
legt `/data/options.json` (von HA Supervisor geschrieben) über `DEFAULTS`, überspringt
`None`-Werte; `LOG_LEVEL`-Env-Var kann `log_level` zusätzlich überschreiben (Dev-Zweck).
Zugriff im Code über `__getattr__` (`config.model`, `config.hems_base_url`, …) bzw.
`config.values[key]` für verschachtelte Gruppen.

`config.py`s `DEFAULTS`-Dict ist 1:1 konsistent mit `config.yaml`s `options:`-Block —
bei Änderungen **beide** synchron halten.

## Allgemein

**KI-Anbieter (D-056):** `provider` wählt einen von drei Anbietern (Gemini, Claude,
OpenAI). Jeder hat ein eigenes aufklappbares Untermenü `providers.<name>` mit
`api_key`/`model`/`timeout_s`/`rate_limit_per_min`; nur das Untermenü des aktiven
Anbieters wird genutzt. `ai_temperature`/`ai_seed` sind geteilt (Gemini/OpenAI senden
sie mit; Claude akzeptiert keine festen Sampling-Parameter mehr). Migration bestehender
Gemini-Installationen: `resolve_active_provider` (`config.py`) fällt für Gemini auf die
alten flachen Top-Level-Keys (`api_key`/`model`/`ai_request_timeout_s`/
`ai_rate_limit_per_min`) zurück, solange das Untermenü leer ist — der Schlüssel geht beim
Update nicht verloren; nach dem Update sollte er ins Gemini-Untermenü eingetragen werden.

| Option | Default | Bereich | Zweck |
|---|---|---|---|
| `log_level` | `info` | debug\|info\|warning\|error | Log-Verbosität |
| `provider` | `gemini` | gemini\|claude\|openai | Aktiver KI-Anbieter (D-056). Zugangsdaten im jeweiligen Untermenü `providers.<name>` |
| `providers.<name>.api_key` | leer | Passwort, nie geloggt | Schlüssel je Anbieter; leer (beim aktiven Anbieter) = KI-Planung deaktiviert |
| `providers.<name>.model` | gemini `gemini-2.5-flash`, claude `claude-sonnet-5`, openai `gpt-5` | frei | Modell je Anbieter |
| `providers.<name>.timeout_s` | 30 | 5–600 | Timeout je KI-Aufruf |
| `providers.<name>.rate_limit_per_min` | gemini 10 / claude 50 / openai 60 | 1–1000 | Wartedrossel (Gemini-Free ~10/min) |
| `ai_temperature` | 0.0 | 0–2 | Determinismus (Gemini/OpenAI; Claude ignoriert Sampling-Params). siehe [planungs-engine.md](planungs-engine.md) |
| `ai_seed` | 42 | frei | Determinismus. Wirkt nur zusammen mit der Kontext-Quantisierung (D-063) — bei jedem Lauf anderer Prompt ⇒ Seed ohne Wirkung |
| `ai_thinking_budget` | 0 | 0–32768 | **Nur Gemini** (D-063): `thinkingConfig.thinkingBudget`. 0 = Thinking aus (reproduzierbar), >0 begrenzt es, Wert entfernt ⇒ Anbieter-Default |
| `ai_repair_missing` | true | bool | Nachforder-Aufruf bei fehlenden Pflichtfeldern |
| `planning_interval_min` | 60 | 15–60 | Gültigkeitsdauer eines Plans (`valid_until = now + Wert`). **Kein** Planungstakt — es gibt keinen Scheduler |
| `plan_update_interval_min` | 15 | 5–60 | **Config existiert, wird nicht ausgewertet** |
| `forecast_horizon_h` | 24 | 12–48 | Planungshorizont |
| `min_confidence_percent` | 70 | 0–100 | Konfidenz-Gate (D-064): ein gültiger Plan unter der Schwelle wird gespeichert und angezeigt, aber **nicht** nach HA geschrieben. Grundlage sind die vier Konfidenz-Teilnoten, aggregiert als schwächstes Glied. 0 ⇒ kein Gate |
| `collect_interval_s` | 30 | 5–300 | Haupt-Poll-Takt (Mess-Rollen, Geräte, Prognose) |
| `publish_suggestions` | true | bool | `sensor.ep_*_vorschlag` nach HA schreiben; `false` = reiner Beobachten-Modus |
| `hems_base_url` | leer | frei | leer = keine HEMS-Anbindung, keine Geräte-Discovery |
| `hems_status_interval_s` | 60 | 10–3600 | eigener Poll-Takt für HEMS-Status-Rückkopplung |
| `publish_status` | true | bool | `sensor.ep_plan_status`/`sensor.ep_hems_verbindung` schreiben |

## PV-Prognose

`pv_forecast` — Liste von `{label, current_hour, next_hour, remaining_today, tomorrow}`,
je Ausrichtung ein Eintrag; EP summiert Werte über alle Ausrichtungen. `pv_forecast_unit`
(Default `kWh`). Jeder Wert liegt im **State** des jeweiligen Sensors, nicht im Attribut.

## Wetter (`weather`-Gruppe)

| Option | Default | Zweck |
|---|---|---|
| `weather.api_key` | leer | leer = Wetterabruf aus |
| `weather.zone_entity` | `zone.home` | Koordinatenquelle (Attribute `latitude`/`longitude`) |
| `weather.units` | `metric` | metric\|imperial\|standard |
| `weather.lang` | `de` | OWM-Sprachcode |
| `weather.source` | `forecast3h` | forecast3h (kostenlos) \| onecall (Abo-pflichtig) |
| `weather.refresh_min` | 60 | Mindestabstand der Abrufe (forecast3h) |
| `weather.llm_detail` | `compact` | compact (Bewölkung/Regen/Temp bis Horizont) \| full (komplette 5-Tage-Prognose) |

**One Call API 4.0** (`weather.onecall`, nur bei `source: onecall`): `enable_15min`
(false)/`enable_1h`/`enable_1day` (beide true) — **jedes aktive Modell wird abgerufen
UND fließt in den KI-Kontext**, beliebige Kombination möglich (kein Einzel-Select
mehr, seit D-054-ähnlicher Änderung — `translations/de.yaml` hat dazu noch einen
veralteten Eintrag, siehe [bekannte-luecken.md](bekannte-luecken.md#veraltete-übersetzung)).
`refresh_15min/1h/1day` (15/60/180 min), `pages_15min/1h/1day` (1–5, mehr Horizont
= mehr bezahlte Calls). `daily_call_budget` (Default 1000 = OWM-Freikontingent) —
harte Tagesobergrenze **aller** bezahlten One-Call-Aufrufe, UTC-Tag, überlebt
Neustarts (in der DB persistiert). `enable_alerts`/`refresh_alerts` — Unwetterwarnungen,
aktuell nur Anzeige, **nicht** in die Planung eingespeist.

## Ziele (D-055, kein Addon-Config-Abschnitt mehr)

Die früheren 8 festen `objective_weights` (statisches Gewicht 0–100 % in der
Addon-Config) sind entfernt. Stattdessen definiert der User im Tab
"Grenzen und Ziele" eigene Ziele (DB-Tabelle `ziele`,
[objectives.py](../app/energy_pilot/objectives.py)): `id`, `name`,
`beschreibung`, optionale Liste zugeordneter (vom HEMS erkannter) Geräte —
**ohne** Gewicht. Ein vorgelagerter Klassifizierungs-LLM-Aufruf
(`planner.py`, `plan_context.build_classification_context`) bekommt dieselben
Daten wie der Plan-Aufruf plus die Zieldefinitionen und leitet daraus je
Planungslauf die Gewichtung ab (0–100 % je Ziel); das Ergebnis fließt
unverändert als `objectives` (key/label/weight) in den Plan-Kontext ein.
Scheitert der Klassifizierungs- oder der Plan-Aufruf, gilt der gesamte
Planungslauf als gescheitert (kein stiller Fallback). Ohne konfigurierte
Ziele entfällt der Klassifizierungs-Aufruf ersatzlos. Der Klassifizierungs-
Prompt ist im Plan-Tab editierbar ("Klassifizierungs-Prompt bearbeiten",
analog zum Planungs-Prompt). Harte Grenzen sind **nicht** hier, sondern
werden aus den `ems_*`-Werten abgeleitet (`constraints.py`).

## Sensor-Zuordnung (`sensoren`)

`entity_pv_power`, `entity_house_load`, `entity_grid_power`, `entity_grid_import`,
`entity_grid_export`, `entity_battery_power`, `entity_battery_soc`,
`entity_hot_water_temp`, `entity_outdoor_temp` — Mapping der 9
festen Mess-Rollen ([roles.py](../app/energy_pilot/roles.py)) auf reale HA-Entity-IDs.
Änderung erfordert Addon-Neustart (Mapping wird beim Boot geladen).

Die beiden **Temperatur-Rollen** (D-061) sind neu und werden **gemittelt** geführt (Ausnahme
zu D-003): EP liefert der KI `latest` **und** die 1-/15-/60-Minuten-Mittel. Erst dieser
Verlauf zeigt, ob eine andere Wärmequelle arbeitet — steigt die Speichertemperatur, ohne dass
der Heizstab Leistung zieht, lädt die Solarthermie. Gerätespezifische **Grenzen und Sollwerte**
bleiben Zusatzwerte im Geräte-Tab ([geraete.md](geraete.md)); die Rollen sind für gemessene,
anlagenweite Größen.

## DB-gestützte Laufzeit-Einstellungen (`settings.py`, **nicht** Addon-Config)

Getrennter Key-Value-Store in der `config`-SQLite-Tabelle für Werte, die zur
Laufzeit über die UI geändert werden und Neustarts/Addon-Updates überleben müssen,
ohne Git-Push:

- **Planungs-Prompt** (`PLANNING_PROMPT_KEY`) — editierbar im Plan-Tab.
- **Klassifizierungs-Prompt** (`CLASSIFICATION_PROMPT_KEY`, D-055) — ebenfalls im Plan-Tab
  editierbar, steuert den vorgelagerten Ziel-Gewichtungs-Aufruf.
- **Hausweite Freitext-Regeln** (`GLOBAL_RULES_KEY`, D-060) — gepflegt im Tab
  „Grenzen & Ziele“; Regeln je Gerät liegen in der Tabelle `device_regeln`.
- **OneCall-Tagesbudget-Zähler** (`onecall_budget.py`).
