# Variablen- & Datenzugriff — HEMS ↔ Energy Pilot

> Strukturierte Fassung von [variablen-zugriff.txt](variablen-zugriff.txt).
> **Inhalt bewusst nur aus der `.txt`:** ausschließlich Variablen, die **direkt über die Namenskonvention** aus HA gelesen/geschrieben werden, sowie die per **API** zwischen HEMS und EP ausgetauschten **internen** Variablen. Konkrete Geräteentitäten, Config-Mappings und Fremddaten-Sensoren stehen hier bewusst **nicht**.
> Offene Punkte aus diesem Dokument → [../claude-fragen/claude-fragen-v6.md](../claude-fragen/claude-fragen-v6.md).

## Geltungsbereich
Nur diese zwei Arten von Werten:
- Werte, die **über die Namenskonvention** direkt aus HA gelesen werden und in **keiner Config** explizit hinterlegt werden müssen.
- Werte, die **per API** zwischen HEMS und EP ausgetauscht und in der jeweiligen Instanz als **interne Variable** gespeichert werden.

## Legende
- `XXX` = Namenskonvention aus **Entitätstyp + Gerätename** (z. B. `heizlufter_1`).
- Jeder Eintrag unten = vollständiges Suffix-Schema **inkl. Domänen-Prefix** (`ems_` / `ep_`).
- **Domänen-Regel:** vom **User gepflegte technische Gerätewerte → `ems_*`** (HEMS-Domäne, EP **liest** nur). **EP-Vorschlagswerte → `ep_*`** (EP **schreibt**).
- **Binärverbraucher** = nur ein/aus. **Regelbarer Verbraucher** = stufenlose Sollleistung.
- Sollwert-Einheit eines Geräts: `_w` = Watt, `_a` = Ampere.

## Rollen & Zuständigkeit

### User
- Setzt über die HA-Oberfläche die (technischen) **Grenzwerte**, **reservierten Mindestwerte** und die **Priorität**.
- Pflegt grundsätzlich **alle HEMS-Werte** (`ems_*`), die manuell gepflegt werden müssen.

### Energy Pilot (EP) — **liest** (`ems_*`)
Liest grundsätzlich alle vom User gepflegten **technischen Werte** eines Geräts. Diese dienen als **Grenzwerte** für die EP-Vorschläge; `…_technische_freigabe` sagt zusätzlich, ob das Gerät **aktuell überhaupt arbeiten kann** — selbst wenn es freigegeben wäre.

| Gerätetyp | Variable | Bedeutung |
|---|---|---|
| Binär | `ems_XXX_leistung_w` | Ist-/Lastleistung des Verbrauchers |
| Binär | `ems_XXX_technische_freigabe` | ob das Gerät aktuell überhaupt arbeiten kann |
| Regelbar | `ems_XXX_technische_freigabe` | ob das Gerät aktuell überhaupt arbeiten kann |
| Regelbar (Watt) | `ems_XXX_min_technisch_w` | technische Mindestleistung |
| Regelbar (Ampere) | `ems_XXX_min_technisch_a` | technische Mindestleistung |
| Regelbar (Watt) | `ems_XXX_max_technisch_w` | technische Maximalleistung |
| Regelbar (Ampere) | `ems_XXX_max_technisch_a` | technische Maximalleistung |

### Energy Pilot (EP) — **schreibt** (`ep_*`)
Schreibt **ausschließlich Vorschlagswerte** — in **HA-Variablen** *und* über einen **HTTP-API-Endpunkt** in **interne Variablen des HEMS** (gestaffelt, siehe Hinweis). Gleiche Namenskonvention beim Ende (Gerätename + Prefix + Suffix), z. B. `ep_heizlufter_1_prio_vorschlag`.

| Gerätetyp | Variable | Bedeutung |
|---|---|---|
| Binär | `ep_XXX_prio_vorschlag` | Prioritäts-Vorschlag |
| Binär | `ep_XXX_freigabe_vorschlag` | Freigabe-Vorschlag |
| Regelbar | `ep_XXX_prio_vorschlag` | Prioritäts-Vorschlag |
| Regelbar | `ep_XXX_freigabe_vorschlag` | Freigabe-Vorschlag (D-034) |
| Regelbar (Watt) | `ep_XXX_geschutzte_mindestleistung_w_vorschlag` | geschützte Mindestleistung, Einheit **W** |
| Regelbar (Ampere) | `ep_XXX_geschutzte_mindestleistung_a_vorschlag` | geschützte Mindestleistung, Einheit **A** |

> Aufgelöst (D-034): Der regelbare Verbraucher erhält **wie der binäre** ein `ep_XXX_freigabe_vorschlag`. Die doppelte `prio`-Zeile in der `.txt` war ein Tippfehler.
> Gerätespezifisch (D-035): Der **Heizstab** hat zusätzlich `sensor.ep_heizstab_max_temperatur_vorschlag` (EP-Sensor, **EP schreibt**) und liest den Grenzwert `input_number.ep_heizstab_max_temperatur` (Helfer, da **user-gepflegt** — daher EP-Domäne, aber **EP liest**).

### HEMS
- Steuert über die vom User festgelegten Werte die `XXX_anforderung`-Werte:
  - **Binärverbraucher:** schaltet das `input_boolean` ein.
  - **Regelbarer Verbraucher:** legt die **Sollleistung** fest.

### Home Assistant
- Setzt über **Automationen/Skripte** die realen **Zustände/Leistungswerte** anhand dessen, was in `XXX_anforderung` für das jeweilige Gerät geschrieben wurde.

## Zugriffsmatrix (wer schreibt / wer liest)

| Variable | Gerätetyp | Schreibt | Liest / Ziel |
|---|---|---|---|
| `ems_XXX_leistung_w` | Binär | User | EP |
| `ems_XXX_technische_freigabe` | Binär + Regelbar | User | EP |
| `ems_XXX_min_technisch_w` / `_a` | Regelbar | User | EP |
| `ems_XXX_max_technisch_w` / `_a` | Regelbar | User | EP |
| `ep_XXX_prio_vorschlag` | Binär + Regelbar | EP | HA-Variable + interne HEMS-Variable (HTTP-API) |
| `ep_XXX_freigabe_vorschlag` | Binär + Regelbar | EP | HA-Variable + interne HEMS-Variable (HTTP-API) |
| `ep_XXX_geschutzte_mindestleistung_w_vorschlag` / `_a_vorschlag` | Regelbar + Batterie | EP | HA-Variable + interne HEMS-Variable (HTTP-API) |
| `input_number.ep_heizstab_max_temperatur` (Helfer) | Heizstab (EP-Domäne) | User/extern | EP (liest, Grenzwert) |
| `sensor.ep_heizstab_max_temperatur_vorschlag` (EP-Sensor) | Heizstab | EP | HA-Anzeige/Dashboards (Vorschlag) |
| `XXX_anforderung` | Binär + Regelbar | HEMS | HA (Automationen/Skripte) |

## Schreibweg — gestaffelt
Die `ep_*`-Vorschlagswerte werden gestaffelt verteilt:
- **Anfang (V1):** ausschließlich in **HA-Helfer/-Entitäten**. Der User verdrahtet sie zunächst selbst testweise in HA-Automationen.
- **Später:** zusätzlich **1:1** direkt über **HTTP-API-Endpunkte in interne HEMS-Variablen** (gleiche Werte → gleich viele Endpunkte wie HA-Helfer). Dann dienen die HA-Entitäten nur noch der **Übersichtlichkeit/Anzeige** (Dashboards), die eigentliche Auswertung passiert im HEMS.

## Datenfluss (Kette)
1. **User** pflegt technische Grenzwerte/Freigaben/Priorität als `ems_*`-Werte in HA-Helfern.
2. **EP liest** diese technischen Werte als Grenzen seiner Vorschläge; `ems_XXX_technische_freigabe` sagt, ob das Gerät überhaupt arbeiten kann.
3. **EP schreibt** ausschließlich Vorschlagswerte (`ep_XXX_prio_vorschlag`, `ep_XXX_freigabe_vorschlag`, `ep_XXX_geschutzte_mindestleistung_w_vorschlag` / `_a_vorschlag`) — V1 in HA-Variablen, später zusätzlich in interne HEMS-Variablen.
4. **HEMS** bildet daraus die `XXX_anforderung` (Binär: `input_boolean` ein / Regelbar: Sollleistung).
5. **HA-Automationen/Skripte** lesen `XXX_anforderung` und schalten/stellen die realen Geräte.
