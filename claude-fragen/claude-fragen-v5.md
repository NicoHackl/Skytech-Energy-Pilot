# Claude-Fragen — v5 (Stand 18.06.2026)

> Fragen aus dem Wissen von [../user-beispiele/variablen-zugriff.txt](../user-beispiele/variablen-zugriff.txt) bzw. der strukturierten [../user-beispiele/variablen-zugriff.md](../user-beispiele/variablen-zugriff.md).
> **Aktualisiert 18.06.2026** nach der Überarbeitung der `.txt`: explizite Prefixe `ems_*` (EP liest) / `ep_*` (EP schreibt) sowie **Ampere-Varianten auch lesend** (`_a`). Dadurch geklärte Punkte stehen unten in **Abschnitt C**; betroffene A-Fragen sind neu zugeschnitten.
> Format wie gehabt: Antwort direkt unter die Frage schreiben; ich übernehme sie danach nach [../plan/entscheidungen.md](../plan/entscheidungen.md) und entferne sie in v6.
> Die geparkten B-Fragen aus [claude-fragen-v4.md](claude-fragen-v4.md) laufen hier unter B weiter.

---

## A — Aktuell projektrelevant (betrifft Namensschema & gelieferte HA-Config jetzt)

### A1 — Technische Werte wandern in den `ems_*`-Namensraum → meine gelieferten `ep_*`-Helfer kollidieren
Durch die `.txt`-Überarbeitung sind die vom User gepflegten technischen Werte jetzt **HEMS-Entitäten** (`ems_XXX_…`), die EP nur **liest** (siehe C1). Meine bisher gelieferten Helfer in [../claude-ha-config-dateien/](../claude-ha-config-dateien/) kollidieren damit **doppelt** — in Prefix **und** Suffix:

| meine aktuelle Datei | `.txt`-Schema (neu) |
|---|---|
| `input_boolean.ep_heizstab_freigabe` | `ems_heizstab_technische_freigabe` |
| `input_number.ep_heizstab_leistung_maximal` | `ems_heizstab_max_technisch_w` |
| `input_number.ep_batterie_ladeleistung_maximal` | `ems_batterie_max_technisch_w` |
| `input_boolean.ep_heizluefter_1_freigabe` | `ems_heizlufter_1_technische_freigabe` |

**Frage:** Sollen diese technischen Grenzwert-/Freigabe-Helfer **komplett in den HEMS-Namensraum** (`ems_*` + `.txt`-Suffixe) wandern und damit **aus meinen `ep_*`-Lieferdateien entfernt** werden (EP liest sie nur, HEMS/User besitzt sie)? Oder bleiben sie als **eigene `ep_*`-Helfer** auf EP-Seite, die der User pflegt (dann nur Suffix angleichen, Prefix `ep_` behalten)?

Antwort:

### A3 — EP-Schreibvertrag = nur Priorität + geschützte Mindestleistung?
Laut `.txt` schreibt EP **ausschließlich**: `ep_XXX_prio_vorschlag` und `ep_XXX_geschutzte_mindestleistung_w_vorschlag` / `_a_vorschlag`. Das spiegelt offenbar genau zwei der drei User-Eingaben (Priorität, reservierter Mindestwert) als Vorschlag wider.
Frühere Beispiele (CLAUDE.md / D-004/D-016) nannten EP-Vorschläge wie `ep_batterie_1_ziel_soc` oder die max. Ladeleistung als Vorschlag.
**Frage:** Ist der EP-Schreibvertrag damit endgültig reduziert auf **(a) Prioritäts-Vorschlag** und **(b) geschützte Mindestleistung**, und HEMS macht die eigentliche Sollwert-/SOC-Regelung? Sind die alten Vorschlags-Beispiele (`ziel_soc`, Ladeleistungs-Vorschlag) damit **überholt**?

Antwort:

### A4 — Binärverbraucher `ems_XXX_leistung_w` vs. „feste 1500 W, kein Helfer"
Die `.txt` sagt: EP liest für **Binärverbraucher** `ems_XXX_leistung_w`.
In D-017/D-018 (und meiner [input_number_ep.yaml](../claude-ha-config-dateien/input_number_ep.yaml)) habe ich für die Heizlüfter **keinen** Leistungs-Helfer angelegt, weil sie fest 1500 W haben.
**Frage:** Braucht **jeder** Binärverbraucher doch einen (festen, user-gepflegten) `ems_…_leistung_w`-Wert, damit EP die **Lastgröße** für die Energieplanung kennt? Falls ja: liegt dieser Wert HEMS-seitig (`ems_*`, vgl. A1) und ich muss nichts in meinen `ep_*`-Dateien anlegen?

Antwort:

### A5 — Schreibweg in V1: HEMS-Endpunkt vs. HA-Helfer (D-002)
Die `.txt` sagt: EP schreibt die Vorschläge „in HA-Variablen **und** über einen **HTTP-API-Endpunkt** in **interne Variablen des HEMS**".
D-002 hat aber V1 = **nur** HA-Helfer / `/api/set` festgelegt (direkter interner Variablen-/Plan-Endpunkt erst **Ebene 2** im HEMS-Repo).
**Frage:** Beschreibt die `.txt` das **Zielbild (Ebene 2)** oder schon V1? Welche Werte gehen als HA-Helfer, welche über den HEMS-Endpunkt — und ab welcher Stufe?

Antwort:

### A6 — Wann *wirken* die EP-Vorschläge in der HEMS-Regelung?
Die `.txt` sagt: HEMS bildet die `XXX_anforderung` aus den **vom User festgelegten Werten**; EP schreibt seine Vorschläge separat in HEMS-Variablen.
**Frage:** Ab wann greifen `ep_…_prio_vorschlag` / `ep_…_geschutzte_mindestleistung…_vorschlag` tatsächlich in die HEMS-Regelung ein — erst im **Shadow/Autopilot** bzw. abhängig vom **Steuermodus** ([../plan/12-steuermodi.md](../plan/12-steuermodi.md))? Im Modus „Vorschlagen" bleiben sie reine Anzeige?

Antwort:

### A7 — EP schlägt Priorität vor, liest die aktuelle Priorität aber nicht (Lücke?)
Laut Rollenliste **setzt der User die Priorität**, und EP schreibt `ep_XXX_prio_vorschlag`. In EPs **Leseliste** (`ems_*`) steht jedoch **kein** aktueller Prioritätswert (`ems_XXX_prio` o. ä.) — EP liest nur Leistung, Freigabe und min/max-Technik.
**Frage:** Ist das gewollt (EP braucht die aktuell gesetzte Priorität nicht als Ausgangsbasis), oder fehlt in der `.txt` ein `ems_XXX_prio`, das EP zum Vergleich/als Baseline lesen sollte?

Antwort:

---

## B — Geparkt / später

### B1 — Ampere-Achse jetzt **symmetrisch** (lesend + schreibend)
Die `.txt` führt `_a` jetzt **beidseitig**: lesend `ems_XXX_min_technisch_a` / `ems_XXX_max_technisch_a`, schreibend `ep_XXX_geschutzte_mindestleistung_a_vorschlag`. Die `_w`-Variante gilt für Geräte mit Watt-Sollwert, `_a` für Ampere-Sollwert (Wallbox/E-Auto). Kein Phase-1-Gerät nutzt Ampere.
**Frage (nur Bestätigung):** Schema mit paralleler `_w`/`_a`-Achse jetzt schon so festziehen, EP wählt je Gerät die passende Einheit? — Keine sofortige Aktion.

Antwort:

### B2 — Schreibweise/Umlaute der Suffixe & Prefixe
In der `.txt` stehen ASCII-Token ohne Umlaute: `geschutzte` (statt geschützte), `heizlufter` (statt Heizlüfter), dazu `technisch`, `ems_`/`ep_`. Regel 3 verlangt deutsche HA-Namen.
**Frage:** Entity-IDs bewusst ASCII (ohne Umlaute, wie HEMS) lassen und nur die `name:`-Anzeige mit Umlauten (`Heizlüfter`, `geschützte`)? Oder durchgängig normalisieren?

Antwort:

### B3 — Hybrid-Modus: fixierbare Felder pro Gerät *(aus v4 übernommen)*
Im Hybrid-Modus (D-009/D-020) fixiert der User Werte, die für die KI hart werden. Welche Felder sollen pro Gerät fixierbar sein? Ich lege bei M3 einen konkreten Vorschlag vor. → [../plan/12-steuermodi.md](../plan/12-steuermodi.md).

Antwort:

### B4 — Plan-JSON-Schema gemeinsam mit HEMS *(aus v4 übernommen)*
Sobald die HEMS-Plan-API (Ebene 2, D-002) ansteht: Schema-Version + Felder gemeinsam im HEMS-Repo pflegen. → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort:

---

## C — Durch die `.txt`-Überarbeitung geklärt (nur noch bestätigen → dann nach entscheidungen.md)

### C1 *(ehem. A2)* — Prefix-Domäne: `ems_` lesen / `ep_` schreiben
Die überarbeitete `.txt` prefixt **alle von EP gelesenen** technischen Werte mit `ems_` und **alle von EP geschriebenen** Vorschläge mit `ep_`.
**Meine Lesart:** Technische Grenzwerte/Freigaben sind **HEMS-Entitäten** (`ems_*`), die EP nur liest; EP-eigene Entitäten sind **ausschließlich** die `ep_*…_vorschlag`-Werte. Damit ist die alte Frage „`ep_` oder `ems_`?" beantwortet.
**Bestätigung (ja/nein), bevor ich es nach entscheidungen.md übernehme:**

Antwort:

---

## Erledigt / Verweis
- v4 hatte keine offenen A-Fragen; die geparkten v4-B-Fragen laufen hier als **B3/B4** weiter.
- **A2** der vorherigen v5-Fassung ist durch die `.txt`-Überarbeitung beantwortet → jetzt **C1** (nur Bestätigung).
