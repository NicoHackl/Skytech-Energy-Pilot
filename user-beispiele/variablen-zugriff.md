# Variablen- & Datenzugriff — HEMS ↔ Energy Pilot

> Strukturierte Fassung von [variablen-zugriff.txt](variablen-zugriff.txt).
> **Inhalt bewusst nur aus der `.txt`:** ausschließlich Variablen, die **direkt über die Namenskonvention** aus HA gelesen/geschrieben werden, sowie die per **API** zwischen HEMS und EP ausgetauschten **internen** Variablen. Konkrete Geräteentitäten, Config-Mappings und Fremddaten-Sensoren stehen hier bewusst **nicht**.
> **Stand 18.06.2026 (an überarbeitete `.txt` angeglichen):** Die `.txt` prefixt die Variablen jetzt explizit — `ems_*` (von EP nur **gelesen**) bzw. `ep_*` (von EP **geschrieben**) — und führt die **Ampere-Varianten auch lesend** (`_a`). Vorschlags-Schreibwerte enden auf `_vorschlag`.
> Offene Punkte aus diesem Dokument → [../claude-fragen/claude-fragen-v5.md](../claude-fragen/claude-fragen-v5.md).

## Geltungsbereich
Nur diese zwei Arten von Werten:
- Werte, die **über die Namenskonvention** direkt aus HA gelesen werden und in **keiner Config** explizit hinterlegt werden müssen.
- Werte, die **per API** zwischen HEMS und EP ausgetauscht und in der jeweiligen Instanz als **interne Variable** gespeichert werden.

## Legende
- **Prefix `ems_`** = vom User gepflegter, **HEMS-seitiger** technischer Wert; EP **liest** ihn nur.
- **Prefix `ep_`** = von **EP** geschriebener **Vorschlagswert** (Suffix `_vorschlag`).
- `XXX` = **Gerätename** (ggf. mit Index), z. B. `heizlufter_1`, `heizstab`, `batterie`.
- Vollform = `<prefix>_XXX_<suffix>`, z. B. `ems_heizstab_max_technisch_w`, `ep_heizlufter_1_prio_vorschlag`.
- **Binärverbraucher** = nur ein/aus. **Regelbarer Verbraucher** = stufenlose Sollleistung; Sollwert-Einheit **W** oder **A** → Suffix `_w` / `_a`.

## Rollen & Zuständigkeit

### User
- Setzt über die HA-Oberfläche die (technischen) **Grenzwerte**, **reservierten Mindestwerte** und die **Priorität**.
- Pflegt grundsätzlich **alle HEMS-Werte**, die manuell gepflegt werden müssen.

### Energy Pilot (EP) — **liest** (`ems_*`)
Liest grundsätzlich alle vom User gepflegten **technischen Werte** eines Geräts. Diese dienen als **Grenzwerte** für die EP-Vorschläge; `ems_XXX_technische_freigabe` sagt zusätzlich, ob das Gerät **aktuell überhaupt arbeiten kann** — selbst wenn es freigegeben wäre.

| Gerätetyp | Variable | Bedeutung |
|---|---|---|
| Binär | `ems_XXX_leistung_w` | (feste) Leistung des Verbrauchers |
| Binär | `ems_XXX_technische_freigabe` | ob das Gerät aktuell überhaupt arbeiten kann |
| Regelbar | `ems_XXX_technische_freigabe` | ob das Gerät aktuell überhaupt arbeiten kann |
| Regelbar (Sollwert in **W**) | `ems_XXX_min_technisch_w` | technische Mindestleistung |
| Regelbar (Sollwert in **A**) | `ems_XXX_min_technisch_a` | technische Mindestleistung |
| Regelbar (Sollwert in **W**) | `ems_XXX_max_technisch_w` | technische Maximalleistung |
| Regelbar (Sollwert in **A**) | `ems_XXX_max_technisch_a` | technische Maximalleistung |

### Energy Pilot (EP) — **schreibt** (`ep_*`)
Schreibt **ausschließlich Vorschlagswerte** — in **HA-Variablen** *und* über einen **HTTP-API-Endpunkt** in **interne Variablen des HEMS**. Gleiche Namenskonvention beim Ende (Gerätename + Suffix), z. B. `ep_heizlufter_1_prio_vorschlag`.

| Gerätetyp | Variable | Bedeutung |
|---|---|---|
| Binär | `ep_XXX_prio_vorschlag` | Prioritäts-Vorschlag |
| Regelbar | `ep_XXX_prio_vorschlag` | Prioritäts-Vorschlag |
| Regelbar (Sollwert in **W**) | `ep_XXX_geschutzte_mindestleistung_w_vorschlag` | geschützte Mindestleistung |
| Regelbar (Sollwert in **A**) | `ep_XXX_geschutzte_mindestleistung_a_vorschlag` | geschützte Mindestleistung |

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
| `ep_XXX_geschutzte_mindestleistung_w_vorschlag` / `_a_vorschlag` | Regelbar | EP | HA-Variable + interne HEMS-Variable (HTTP-API) |
| `XXX_anforderung` | Binär + Regelbar | HEMS | HA (Automationen/Skripte) |

## Datenfluss (Kette)
1. **User** pflegt technische Grenzwerte/Freigaben/Priorität (HEMS-Werte, `ems_*`) in HA-Helfern.
2. **EP liest** diese technischen Werte als Grenzen seiner Vorschläge; `ems_XXX_technische_freigabe` sagt, ob das Gerät überhaupt arbeiten kann.
3. **EP schreibt** ausschließlich Vorschlagswerte (`ep_XXX_prio_vorschlag`, `ep_XXX_geschutzte_mindestleistung_w_vorschlag` / `_a_vorschlag`) in HA-Variablen und über HTTP-API in interne HEMS-Variablen.
4. **HEMS** bildet daraus die `XXX_anforderung` (Binär: `input_boolean` ein / Regelbar: Sollleistung).
5. **HA-Automationen/Skripte** lesen `XXX_anforderung` und schalten/stellen die realen Geräte.

> **Hinweis (Abgleich mit dem Projekt):** Das hier beschriebene `ems_*`/`ep_*`-Suffix-Schema weicht vom aktuell in [../claude-ha-config-dateien/](../claude-ha-config-dateien/) gelieferten Helfer-Naming ab (`ep_heizstab_freigabe`, `ep_heizstab_leistung_maximal`, `ep_batterie_ladeleistung_maximal` …). Auflösung dieses Konflikts → [../claude-fragen/claude-fragen-v5.md](../claude-fragen/claude-fragen-v5.md) (A1).
