# Variablen- & Datenzugriff — HEMS ↔ Energy Pilot

> Strukturierte Fassung von [variablen-zugriff.txt](variablen-zugriff.txt).
> **Inhalt bewusst nur aus der `.txt`:** ausschließlich Variablen, die **direkt über die Namenskonvention** aus HA gelesen/geschrieben werden, sowie die per **API** zwischen HEMS und EP ausgetauschten **internen** Variablen. Konkrete Geräteentitäten, Config-Mappings und Fremddaten-Sensoren stehen hier bewusst **nicht**.
> Offene Punkte aus diesem Dokument → [../claude-fragen/claude-fragen-v5.md](../claude-fragen/claude-fragen-v5.md).

## Geltungsbereich
Nur diese zwei Arten von Werten:
- Werte, die **über die Namenskonvention** direkt aus HA gelesen werden und in **keiner Config** explizit hinterlegt werden müssen.
- Werte, die **per API** zwischen HEMS und EP ausgetauscht und in der jeweiligen Instanz als **interne Variable** gespeichert werden.

## Legende
- `XXX` = Namenskonvention aus **Entitätstyp + Gerätename** (z. B. `heizlufter_1`).
- Jeder Eintrag unten = das **Suffix-Schema**, das an `XXX` angehängt wird.
- **Binärverbraucher** = nur ein/aus. **Regelbarer Verbraucher** = stufenlose Sollleistung.

## Rollen & Zuständigkeit

### User
- Setzt über die HA-Oberfläche die (technischen) **Grenzwerte**, **reservierten Mindestwerte** und die **Priorität**.
- Pflegt grundsätzlich **alle HEMS-Werte**, die manuell gepflegt werden müssen.

### Energy Pilot (EP) — **liest**
Liest grundsätzlich alle vom User gepflegten **technischen Werte** eines Geräts. Diese dienen als **Grenzwerte** für die EP-Vorschläge; `XXX_technische_freigabe` sagt zusätzlich, ob das Gerät **aktuell überhaupt arbeiten kann** — selbst wenn es freigegeben wäre.

| Gerätetyp | Variable (Suffix) | Bedeutung |
|---|---|---|
| Binär | `XXX_leistung_w` | Leistung des Verbrauchers |
| Binär | `XXX_technische_freigabe` | ob das Gerät aktuell überhaupt arbeiten kann |
| Regelbar | `XXX_technische_freigabe` | ob das Gerät aktuell überhaupt arbeiten kann |
| Regelbar | `XXX_min_technisch_w` | technische Mindestleistung |
| Regelbar | `XXX_max_technisch_w` | technische Maximalleistung |

### Energy Pilot (EP) — **schreibt**
Schreibt **ausschließlich Vorschlagswerte** — in **HA-Variablen** *und* über einen **HTTP-API-Endpunkt** in **interne Variablen des HEMS**. Gleiche Namenskonvention beim Ende (Gerätename + Prefix + Suffix), z. B. `heizlufter_1_prio_vorschlag`.

| Gerätetyp | Variable (Suffix) | Bedeutung |
|---|---|---|
| Binär | `XXX_prio_vorschlag` | Prioritäts-Vorschlag |
| Regelbar | `XXX_prio_vorschlag` | Prioritäts-Vorschlag |
| Regelbar (Sollwert in Watt) | `XXX_geschutzte_mindestleistung_w` | geschützte Mindestleistung, Einheit **W** |
| Regelbar (Sollwert in Ampere) | `XXX_geschutzte_mindestleistung_a` | geschützte Mindestleistung, Einheit **A** |

### HEMS
- Steuert über die vom User festgelegten Werte die `XXX_anforderung`-Werte:
  - **Binärverbraucher:** schaltet das `input_boolean` ein.
  - **Regelbarer Verbraucher:** legt die **Sollleistung** fest.

### Home Assistant
- Setzt über **Automationen/Skripte** die realen **Zustände/Leistungswerte** anhand dessen, was in `XXX_anforderung` für das jeweilige Gerät geschrieben wurde.

## Zugriffsmatrix (wer schreibt / wer liest)

| Variable (Suffix) | Gerätetyp | Schreibt | Liest / Ziel |
|---|---|---|---|
| `XXX_leistung_w` | Binär | User | EP |
| `XXX_technische_freigabe` | Binär + Regelbar | User | EP |
| `XXX_min_technisch_w` | Regelbar | User | EP |
| `XXX_max_technisch_w` | Regelbar | User | EP |
| `XXX_prio_vorschlag` | Binär + Regelbar | EP | HA-Variable + interne HEMS-Variable (HTTP-API) |
| `XXX_geschutzte_mindestleistung_w` | Regelbar (Watt) | EP | HA-Variable + interne HEMS-Variable (HTTP-API) |
| `XXX_geschutzte_mindestleistung_a` | Regelbar (Ampere) | EP | HA-Variable + interne HEMS-Variable (HTTP-API) |
| `XXX_anforderung` | Binär + Regelbar | HEMS | HA (Automationen/Skripte) |

## Datenfluss (Kette)
1. **User** pflegt technische Grenzwerte/Freigaben/Priorität (HEMS-Werte) in HA-Helfern.
2. **EP liest** diese technischen Werte als Grenzen seiner Vorschläge; `XXX_technische_freigabe` sagt, ob das Gerät überhaupt arbeiten kann.
3. **EP schreibt** ausschließlich Vorschlagswerte (`XXX_prio_vorschlag`, `XXX_geschutzte_mindestleistung_w` / `_a`) in HA-Variablen und über HTTP-API in interne HEMS-Variablen.
4. **HEMS** bildet daraus die `XXX_anforderung` (Binär: `input_boolean` ein / Regelbar: Sollleistung).
5. **HA-Automationen/Skripte** lesen `XXX_anforderung` und schalten/stellen die realen Geräte.
