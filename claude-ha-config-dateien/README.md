# HA-Konfigurationsdateien für Skytech Energy Pilot

Fertige Home-Assistant-Helfer-Pakete, die der User **selbst** in seine HA-Konfiguration einfügt (Entscheidung D-005, siehe [../docs/design-entscheidungen.md](../docs/design-entscheidungen.md)). EP legt Helfer **nicht** automatisch an.

## Einbinden in Home Assistant
Pro Domäne gibt es eine Datei `<domain>_ep.yaml`. Den Inhalt jeweils **unter den passenden Domain-Block** in deiner `configuration.yaml` (oder ein eingebundenes Package) kopieren, z.B.:

```yaml
input_number: !include input_number_ep.yaml      # oder Inhalt direkt einfügen
input_boolean: !include input_boolean_ep.yaml
input_select:  !include input_select_ep.yaml
input_datetime: !include input_datetime_ep.yaml
```
Danach **HA neu starten** bzw. die YAML-Konfiguration neu laden.

## Namenskonvention — Domäne nach Datenrichtung (D-004/D-029)
- **`ems_*`** = vom **User gepflegte technische Gerätewerte** (Grenzwerte, Freigaben, Ist-Leistung) → **HEMS-Domäne**, EP **liest** sie nur. **Nicht** in diesen `ep_`-Paketen enthalten.
- **`ep_*`** = **EP-eigene** Schalter/Parameter bzw. EP-**Vorschlagswerte** (`…_vorschlag`). Nur diese liefere ich hier.
- Vollständiger Datenfluss + Read-/Write-Schema: [../user-beispiele/variablen-zugriff.md](../user-beispiele/variablen-zugriff.md).
- **Geklärt (D-036):** Die `ems_*`-Gerätehelfer sind **im HEMS definiert** (dort dynamisch pro Gerät erzeugt) — **kein** `ems_*`-Template von EP. EP liest die echten Entity-IDs über den HEMS-Endpunkt `GET /api/device_controls_schema`.
- **Ausnahme (D-035):** `input_number.ep_heizstab_max_temperatur` ist ein **`ep_*`-Grenzwert, den EP liest** (max. Wassertemperatur, nicht HEMS-relevant) — daher hier in `input_number_ep.yaml` enthalten.

## Dateien
| Datei | Domäne | Inhalt |
|-------|--------|--------|
| `input_number_ep.yaml` | input_number | EP-Planungsparameter (`ep_*`), `ep_heizstab_max_temperatur` (Grenzwert, EP liest, D-035) + dokumentierte `ems_*`-Lesewerte |
| `input_boolean_ep.yaml` | input_boolean | EP-Schalter (`ep_*`) + dokumentierte `ems_*`-Freigaben |
| `input_select_ep.yaml` | input_select | Steuermodus, Betriebsmodus, Strategie (`ep_*`) |
| `input_datetime_ep.yaml` | input_datetime | E-Auto-Abfahrtszeit (später; auch für externen iOS/Java-Zugriff, D-013) |

## Altlasten aufräumen (Stand 0.0.61)

Mehrere `ep_*`-Helfer aus früheren Ausbaustufen liegen in bestehenden Installationen noch in
HA, werden von EP aber **nirgends gelesen** — und widersprechen den Addon-Optionen, die
dieselben Größen führen. Wer sie stehen lässt, stellt Werte ein, die keine Wirkung haben:

| Helfer | Wird von EP gelesen? | Stattdessen |
|---|---|---|
| `input_number.ep_mindestkonfidenz` | nein | Addon-Option `min_confidence_percent` (D-064) |
| `input_number.ep_prognosehorizont` | nein | Addon-Option `forecast_horizon_h` |
| `input_number.ep_planungsintervall` | nein | Addon-Option `planning_interval_min` |
| `input_select.ep_steuermodus`, `ep_betriebsmodus`, `ep_strategie` | nein | Steuermodi sind nicht verdrahtet ([../docs/steuermodi.md](../docs/steuermodi.md)); wirksam ist die HEMS-Modus-Achse (D-057) |
| `input_boolean.ep_aktiv`, `ep_automatische_planung`, `ep_automatische_ubernahme`, `ep_ereignis_neuplanung` | nein | es gibt keinen Scheduler ([../docs/bekannte-luecken.md](../docs/bekannte-luecken.md)) |

Diese Helfer können aus der HA-Konfiguration **entfernt** werden. Sie stehen deshalb auch nicht
mehr in den Paketdateien dieses Ordners. Weiterhin gebraucht wird `ep_heizstab_max_temperatur`
(Grenzwert, EP liest, D-035/D-061) und `ep_eauto_abfahrtszeit`, sofern als Zusatzwert gepflegt.

**Neu ab 0.0.61 (D-061):** Warmwasser- und Außentemperatur trägst du **nicht** als Helfer ein,
sondern als bestehende Sensor-Entitäten in der Addon-Option `sensoren`
(`entity_hot_water_temp`, `entity_outdoor_temp`) — EP führt darauf die Mittelwerte, damit die
KI den Verlauf sieht.

## Wichtig
- **Geräte-Grenzwerte/Freigaben/Ist-Leistung liefern diese Dateien NICHT** — sie sind `ems_*` (HEMS-Domäne, D-029). Hier nur als Kommentar dokumentiert, damit klar ist, was HEMS bereitstellen muss. Findet EP einen Wert nicht, greift der **Fallback in der Addon-Config**.
- **Fremddaten** (PV-Prognose, Strompreis) sind **nicht** hier — die trägst du als bestehende Sensor-Entitätsnamen direkt in der **Addon-Config** ein (D-006).
- **Vorschlagswerte von EP** sind ebenfalls nicht hier — die stellt EP selbst als `sensor.ep_*_vorschlag`-Entitäten bereit (D-030).
- Werte (min/max/Defaults) sind Vorschläge — an deine Anlage anpassen.
- **KI-Übernahme wird im HEMS gesteuert (D-033), nicht hier.** Der HEMS-Helfer
  `input_select.ems_regelmodus` (Werte `auto`/`manuell`/`nur_heizen`/`nur_laden`/`aus`)
  entscheidet: **`auto` = alle Geräte übernehmen den EP-Vorschlag**, `manuell` = normale
  HEMS-Regeln. Pro Gerät verfeinerbar über den bestehenden `input_select.ems_<gerät>_modus`
  (`auto` = EP für dieses Gerät, `manuell` = normale Regeln, `aus` = aus). Diese Selektoren
  sind **HEMS-Domäne** und existieren bereits — hier sind **keine** neuen `ep_*`-Helfer nötig.

> Hinweis: Vorlage des Formats stammt aus [../user-beispiele/beispiel-config-yam.txt](../user-beispiele/beispiel-config-yam.txt).
