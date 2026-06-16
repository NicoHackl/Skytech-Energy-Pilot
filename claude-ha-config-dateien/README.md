# HA-Konfigurationsdateien für Skytech Energy Pilot

Fertige Home-Assistant-Helfer-Pakete, die der User **selbst** in seine HA-Konfiguration einfügt (Entscheidung D-005, siehe [../plan/entscheidungen.md](../plan/entscheidungen.md)). EP legt Helfer **nicht** automatisch an.

## Einbinden in Home Assistant
Pro Domäne gibt es eine Datei `<domain>_ep.yaml`. Den Inhalt jeweils **unter den passenden Domain-Block** in deiner `configuration.yaml` (oder ein eingebundenes Package) kopieren, z.B.:

```yaml
input_number: !include input_number_ep.yaml      # oder Inhalt direkt einfügen
input_boolean: !include input_boolean_ep.yaml
input_select:  !include input_select_ep.yaml
input_datetime: !include input_datetime_ep.yaml
```
Danach **HA neu starten** bzw. die YAML-Konfiguration neu laden.

## Namenskonvention (D-004)
Schema: `<DOMAIN>.ep_<GERÄTENAME>[_<INDEX>]_<…>` — analog HEMS, deutsch. Beispiele:
`input_number.ep_batterie_1_soc_mindestwert`, `sensor.ep_heizstab_freigabe`.
Geräte-Index (`_1`) erlaubt später mehrere gleichartige Geräte.

## Dateien
| Datei | Domäne | Inhalt |
|-------|--------|--------|
| `input_number_ep.yaml` | input_number | Zahlen-Grenzwerte (SOC, Leistungen, Temperaturen, Konfidenz) |
| `input_boolean_ep.yaml` | input_boolean | EP-Schalter + Geräte-Freigaben |
| `input_select_ep.yaml` | input_select | Steuermodus, Betriebsmodus, Strategie |
| `input_datetime_ep.yaml` | input_datetime | E-Auto-Abfahrtszeit (später; auch für externen iOS/Java-Zugriff, D-013) |

## Wichtig
- Diese Helfer liefern **Daten von HA → EP** (Grenzwerte/Geräteinfos, user-regeln.md §03). Findet EP einen Helfer nicht, greift der **Fallback in der Addon-Config**.
- **Fremddaten** (PV-Prognose, Strompreis) sind **nicht** hier — die trägst du als bestehende Sensor-Entitätsnamen direkt in der **Addon-Config** ein (D-006).
- **Vorschlagswerte von EP** sind ebenfalls nicht hier — die stellt EP selbst als `sensor.ep_*`-Entitäten bereit.
- Werte (min/max/Defaults) sind Vorschläge — an deine Anlage anpassen.

> Hinweis: Vorlage des Formats stammt aus [../user-beispiele/beispiel-config-yam.txt](../user-beispiele/beispiel-config-yam.txt).
