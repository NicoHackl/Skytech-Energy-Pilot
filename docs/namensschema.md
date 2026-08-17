# Namensschema `ems_*` / `ep_*`

Zentrale, nicht verhandelbare Regel (Decision D-029, siehe [design-entscheidungen.md](design-entscheidungen.md)):
**Namens-Domäne folgt der Datenrichtung.**

| Präfix | Domäne | Wer pflegt/erzeugt | Wer liest/schreibt EP |
|---|---|---|---|
| `ems_*` | HEMS-Domäne | User bzw. HEMS-Discovery (dynamisch generiert) | EP **liest nur** |
| `ep_*` | EP-Domäne | EP | EP **schreibt** |

Ausnahme (D-035): ein `ep_*`-Wert kann auch ein user-/extern-gepflegter **Grenzwert**
sein, den EP nur liest — z. B. `input_number.ep_heizstab_max_temperatur`. Der Präfix
sagt also "wessen Namensraum", nicht zwingend "wer schreibt".

## Lese-Seite: `ems_*` (implementiert in `devices.py: read_fields()`)

`ems_*`-Entitäten werden **nicht** von EP als Template vorgegeben, sondern
**dynamisch von HEMS pro Gerät erzeugt** aus `entity_prefix` + `class`
(`controllable`/`binary`) + `output_unit` (`watt`→`_w`/`ampere`→`_a`). EP entdeckt die
tatsächlichen Entity-IDs zur Laufzeit über `GET /api/device_controls_schema`
(D-036) statt sie zu raten.

| Geräteklasse | Gelesene Felder |
|---|---|
| binär (z. B. Heizlüfter) | `ems_<prefix>_technische_freigabe`, `ems_<prefix>_leistung_w` |
| regelbar (z. B. Heizstab) | `ems_<prefix>_technische_freigabe`, `ems_<prefix>_min_technisch_<w\|a>`, `ems_<prefix>_max_technisch_<w\|a>` |

Reale Beispiele: `ems_heizstab_technische_freigabe`, `ems_heizlüfter_1_leistung_w`,
`ems_heizstab_max_technisch_w`.

`hems_status_collector.py` liest zusätzlich hilfsweise
`input_number.ems_<prefix>_geschutzte_mindestleistung_<w|a>` direkt aus der HA-Helfer,
falls eine ältere HEMS-Version dieses Feld noch nicht über `/api/status` liefert
(HEMS-Wert hat immer Vorrang, sobald verfügbar).

## Schreib-Seite: `ep_*` (implementiert in `suggestion_publisher.py`)

**Phase-1-Schreibvertrag** (D-030/D-034), als `sensor.*` bereitgestellt:

| Feld | Geräteklasse | Regelbar? |
|---|---|---|
| `ep_<name>_prio_vorschlag` | binär + regelbar | nein |
| `ep_<name>_freigabe_vorschlag` | binär + regelbar | ja (binär) |
| `ep_<name>_geschutzte_mindestleistung_w_vorschlag` bzw. `_a_vorschlag` | regelbar + Batterie | ja |

**Batterie-Sonderfall (D-037):** immer Prio 1, immer freigegeben — EP schreibt nur
`ep_batterie_geschutzte_mindestleistung_w_vorschlag`, kein `prio_vorschlag`/`freigabe_vorschlag`.

Reale Beispiele: `sensor.ep_heizstab_prio_vorschlag`, `sensor.ep_heizlüfter_1_freigabe_vorschlag`.

Der exakte Schreibvertrag je Gerät wird zur Laufzeit von `plan_schema.py:
suggestion_keys()` aus der Geräteklasse berechnet — dort nachschlagen, wenn sich
das Schema ändert.

## Zusatz-Entitäten (D-047/D-048/D-049/D-052)

Im Geräte-Tab kann der User pro Gerät beliebige zusätzliche Entitäten konfigurieren
(löst den früheren Heizstab-Hardcode D-035 ab, der jetzt als einmalig geseedete
Zusatz-Entität existiert — `device_extras.py: seed_defaults()`):

1. **Quell-Entity-ID** (beliebige HA-Domäne: `sensor`, `input_number`, `input_boolean`,
   `input_datetime`, `input_text`, `input_select`, `number`, `text`, `select` …).
2. Checkbox **"KI liefert Vorschlagswert"** → erzeugt bei Aktivierung
   `sensor.ep_<object_id>_vorschlag` (`<object_id>` = Objekt-ID der Quelle ohne
   führendes `ep_`, z. B. `input_number.min_soc_auto` → `sensor.ep_min_soc_auto_vorschlag`).
3. Freitextfeld — erklärt der KI Bedeutung/Verwendung der Entität.
4. **Rolle** (D-061): `ist` (gemessener Wert), `grenze` (vom User gesetzte Ober-/Untergrenze)
   oder `sollwert` (Vorgabe). Geht als `rolle` samt Klartext in den Kontext. Ohne diese Angabe
   liest ein Modell einen Sollwert als Messwert — der belegte Auslöser eines Fehlvorschlags
   (Obergrenze 85 °C als Ist-Temperatur gelesen). **Gemessene** anlagenweite Größen gehören
   nicht hierher, sondern als Mess-Rolle in die Addon-Config
   ([konfiguration.md](konfiguration.md#sensor-zuordnung-sensoren)).

Typ folgt der Domäne (D-048): `input_number`/`number` → Zahl (mit `min`/`max` als
KI-Grenzen **und** Klemmung), `input_boolean`/`switch`/`binary_sensor` → Bool,
`input_datetime` → Datum/Zeit-String (`has_date`/`has_time` bestimmen das Format),
`input_text`/`text` → Text, `input_select`/`select` → Enum (verfügbare `options` als
Wertepool, KI muss exakt einen Wert wählen, D-049 — ein Vorschlag außerhalb des Pools
wird vom Validator **verworfen**, nicht das ganze Gerät). Nicht gelistete Domänen
(v. a. `sensor`) laufen unter `"auto"` (Zahl falls numerischer State, sonst Text).

Zusatz-Vorschläge sind grundsätzlich **advisorisch**: nur HA-Sensor, **nie** an HEMS,
keine harte Klemmung außer bei `input_number`-`min`/`max`.

**Ausnahme "In Original schreiben" (D-052):** zweite Checkbox, nur wählbar wenn
"KI liefert Vorschlagswert" aktiv ist. Schreibt den Vorschlag **zusätzlich** per
HA-Service-Call in die Original-Entität zurück (`HAClient.call_service()`, nicht
State-Override — damit greift HAs eigene Validierung/Min-Max/Optionspool weiterhin).
Nur für echte Helfer-Domänen (`input_number`/`number`/`input_boolean`/`input_datetime`/
`input_text`/`text`/`input_select`/`select`); bei `sensor.*` (read-only von Natur aus)
bleibt es beim reinen `_vorschlag`-Sensor. Bricht bewusst die V1-Grundregel
"Vorschläge sind rein advisorisch" — aber nur pro Zusatz-Entität und nur wenn der
User es explizit aktiviert.

## Stolperstein: Suffix-Übersetzung beim zukünftigen Direkt-Schreibweg

Sobald der geplante 1:1-Schreibweg EP→HEMS kommt (D-032, aktuell **nicht**
implementiert — V1 schreibt nur nach HA-Helfer, siehe [roadmap.md](roadmap.md)):
Die Suffixe sind **nicht** stringidentisch zwischen `ep_*_vorschlag`-Feldern und
HEMS-`ems_*`-Feldern:

| EP-Feld | HEMS-Feld |
|---|---|
| `ep_<p>_prio_vorschlag` | `ems_<p>_prioritat` |
| `ep_<p>_freigabe_vorschlag` | `ems_<p>_freigabe` |
| `ep_<p>_geschutzte_mindestleistung_<w\|a>_vorschlag` | `ems_<p>_geschutzte_mindestleistung_<w\|a>` |

Wer diesen Weg implementiert, muss remappen, nicht blind konkatenieren.

## Sonstige Namenskonventionen

- Umlaute ä/ö/ü werden zu a/o/u (nicht ae/oe/ue) — Entity-IDs sind ASCII ohne
  Umlaute, gegen HEMS-Quellcode verifiziert (`prioritat`, `geschutzte`, `anderung`).
- Allgemeine Infos → Suffix `allgemeine_informationen`, als Sensor-**Attribute**
  (aktuell nicht genutzt, für zukünftige Erweiterung vorgesehen).
- Fremddaten (Strompreis, PV-Prognose-Sensoren, Wetter) haben **kein** Namensschema
  — freie Entitätsnamen, in der Addon-Config gepflegt (Drittanbieter-Integrationen
  folgen der EP-Konvention naturgemäß nicht).
- HA-Helfer werden von EP **nicht automatisch angelegt** — fertige
  `<domain>_ep.yaml`-Pakete liegen in [`claude-ha-config-dateien/`](../claude-ha-config-dateien/),
  Vorlage in [`user-beispiele/`](../user-beispiele/).
