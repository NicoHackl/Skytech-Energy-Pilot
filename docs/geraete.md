# Geräte

## Gerätemodell (`devices.py`)

- `Device` — gefrorene Dataclass: `name`, `label`, `entity_prefix`, `device_class`
  (`controllable`/`binary`), `output_unit` (`watt`/`ampere`), `extras`, `ai_prompt`.
- `DeviceExtra` — gefrorene Dataclass für eine konfigurierte Zusatz-Entität; leitet
  `kind`, `capture_attrs`, `object_id`, `read_key`, `plan_field`,
  `suggestion_entity_id`, `is_writable_helper`, `should_write_original` aus der
  `read_entity_id`-Domäne ab (siehe [namensschema.md](namensschema.md)).

## Discovery — ausschließlich über HEMS (D-046)

Geräte werden **nicht** aus der Addon-Config gelesen. Einzige Quelle:
`GET /api/device_controls_schema` beim HEMS. Ist HEMS beim Start nicht erreichbar,
kennt EP **keine** Geräte — es gibt bewusst keinen Fallback ("EP ohne HEMS ist
sinnlos", D-046-Begründung).

`discover_from_hems_schema()` parst `[{"label":..., "name":..., "items":[{"entity":...}]}]`,
extrahiert `entity_prefix` per Regex `\.ems_(?P<prefix>.+)_technische_freigabe$`,
klassifiziert `controllable` (hat `_min_technisch_[wa]`) vs. `binary` (hat `_leistung_w`),
leitet Ampere-vs-Watt aus dem `_a`-Suffix ab, überspringt Gruppen mit Label "global".

Weil HA **keine** Addon-Startreihenfolge garantiert, ist HEMS beim EP-Start evtl.
noch nicht erreichbar. Deshalb:

- **Auto-Retry:** bis zu 5 Versuche im 30-s-Abstand (`DISCOVERY_RETRY_ATTEMPTS`/`DISCOVERY_RETRY_DELAY_S`, `web/server.py`).
- **Manueller Sync:** Button "Geräte von HEMS neu laden" im HEMS-Tab → `POST /api/hems/rediscover`.

Jeder Re-Discovery-Lauf baut die Allowlist **komplett neu** (`allowlist.rebuild()`,
nicht additiv) — dadurch verschwinden verwaiste `ems_*`-Entitäten umbenannter/
entfernter Geräte automatisch.

## Anfangsgeräte (Phase 1)

| Gerät | Besonderheit |
|---|---|
| **Batterie (E3DC)** | immer Prio 1, immer freigegeben, **kein** SOC-Limit, **keine** Entladung (nur PV-Überschuss); nur max. Ladeleistung relevant. Einziger Schreibwert: `ep_batterie_geschutzte_mindestleistung_w_vorschlag` (D-037). `constraints.py: BATTERY_PREFIX = "batterie"` erzwingt `forced_prio=1`/`forced_freigabe=True`. |
| **Heizstab** | regelbar; max./min. Leistung + Freigabe als `ems_*` (EP liest). Max. Wassertemperatur ist **nicht** HEMS-relevant — läuft als generische Zusatz-Entität (D-047), beim ersten HEMS-Sync einmalig geseedet (`input_number.ep_heizstab_max_temperatur` → `sensor.ep_heizstab_max_temperatur_vorschlag`), danach im Geräte-Tab frei editier-/löschbar. |
| **Heizlüfter 1 & 2** | feste 1500 W (binär). Ist-Leistung als `ems_<name>_leistung_w` — falls das Feld fehlt, nimmt `constraints.py` `DEFAULT_BINARY_POWER_W = 1500.0` als Fallback an. Freigabe als `ems_<name>_technische_freigabe`. |

Wallbox/E-Auto, Wärmepumpe, dynamische Tarife, mehrere Speicher: bewusst **später**
(siehe [roadmap.md](roadmap.md), M6).

## Harte Grenzen (`constraints.py`)

`build_constraints(devices, readings)` ist die zentrale reine Funktion, die aus den
gelesenen `ems_*`-Werten (`DeviceCollector`-Snapshot) pro Gerät ein `DeviceConstraint`
ableitet — inklusive `ConstraintExtra` für jede konfigurierte Zusatz-Entität (mit
aufgelöstem `kind`/`min`/`max`/`has_date`/`has_time`/`options`). Diese Grenzen sind
die Grundlage für Validator-Stufe 2 (siehe [sicherheit-datenschutz.md](sicherheit-datenschutz.md)).

## Zusatz-Entitäten & Pro-Gerät-KI-Beschreibung

Konfiguration und Vorschlags-Semantik: siehe [namensschema.md](namensschema.md#zusatz-entitäten-d-047d-048d-049d-052).

Seit D-051 hat jedes Gerät zusätzlich ein freies Textfeld **"KI-Beschreibung"**
(`device_prompts.py`, Tabelle `device_prompts`), das gerätespezifische Eigenheiten
erklärt (z. B. "speist Fußbodenheizung, träge, bevorzugt Mittagsbetrieb"). Rein
advisorisch, fließt nur in den Planungs-Prompt ein, wenn gesetzt (Datenminimum),
geht nie an HEMS. Zwei Prompt-Ebenen existieren parallel: der globale Planungs-Prompt
(gesamte Strategie, siehe [planungs-engine.md](planungs-engine.md)) und dieser
Pro-Gerät-Prompt (Einzelgeräte-Erklärung).
