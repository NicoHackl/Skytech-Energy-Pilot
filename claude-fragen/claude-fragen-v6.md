# Claude-Fragen — v6 (Stand 19.06.2026)

> **STATUS (verarbeitet 19.06.2026):** A1–A4 beantwortet → Decision Log **D-034…D-037** (gegen lokalen HEMS-Quellcode verifiziert). Offene B-Fragen laufen in [claude-fragen-v7.md](claude-fragen-v7.md) weiter. Diese Datei bleibt als Q&A-Historie.

> Folgefragen aus der aktualisierten [../user-beispiele/variablen-zugriff.txt](../user-beispiele/variablen-zugriff.txt) (jetzt mit `ems_`/`ep_`-Prefixen, `freigabe_vorschlag`, Ampere-Varianten) und ihren in v5 beantworteten Punkten (→ [../plan/entscheidungen.md](../plan/entscheidungen.md) D-029…D-033).
> Format wie gehabt: Antwort direkt unter die Frage; ich übernehme sie danach nach entscheidungen.md und entferne sie in v7.
> Die geparkten B-Fragen aus [claude-fragen-v5.md](claude-fragen-v5.md) laufen hier unter B weiter.

---

## A — Aktuell projektrelevant

### A1 — Regelbarer Verbraucher: zusätzlich `ep_<name>_freigabe_vorschlag`?
In der `.txt` steht beim **regelbaren** Verbraucher zweimal `ep_XXX_prio_vorschlag` (Zeilen 44/45) — sieht nach Tippfehler aus. Beim **binären** Verbraucher gibt es `prio_vorschlag` **und** `freigabe_vorschlag`, und deine A3-Antwort nennt „prio, mindestleistung und **freigabe**".
**Frage:** Bekommt der regelbare Verbraucher **auch** ein `ep_<name>_freigabe_vorschlag` (also war eine der beiden `prio`-Zeilen eigentlich `freigabe_vorschlag`)? Dann schreibt EP für regelbare Geräte: `prio_vorschlag`, `freigabe_vorschlag`, `geschutzte_mindestleistung_w/a_vorschlag`.

Antwort: ja hab es angepasst, es ist prio, freigabe und geschütze_mindestleistung

### A2 — Heizstab max. Wassertemperatur: Übergabeweg an EP?
Das generische `ems_*`-Read-Schema kennt nur `leistung_w`, `technische_freigabe`, `min/max_technisch_w/a` — **keine** Temperatur. Der Heizstab hat aber eine **max. Wassertemperatur** als Grenze (D-016/Phase 1).
**Frage:** Wie liest EP diese Grenze? Als gerätespezifischen `ems_*`-Wert (z. B. `ems_heizstab_wasser_temperatur_maximal`) außerhalb des generischen Schemas — oder ist sie rein HEMS-intern und für EP **nicht** relevant?

Antwort: Da dieser Wert nicht für das HEMS relevant ist wird dieser auch nicht vom HEMS gestellt, das heißt des gibt (aktuell) zwei neue Enitäten
- input_number_ep_heizstab_max_temperatur -> dieser dient als max-grenzwert für den EP (EP nur lesen)
- input_number_ep_heizstab_max_temperatur_vorschlag -> dieser wert wird vom EP gesetzt und dient als vorschlag für die max heizstabtemperatur

> Nachträgliche Klärung (19.06.2026, → D-035): Nur der **Grenzwert** ist ein `input_number`-**Helfer** (user-gepflegt). Der **Vorschlag** ist — wie alle `ep_*_vorschlag` (D-030) — eine **EP-eigene `sensor.`-Entität**, kein Helfer.


### A3 — `ems_*`-Gerätehelfer: schon in HEMS, oder liefere ich ein `ems_*`-Template?
Laut D-029 sind alle technischen Gerätewerte `ems_*` (HEMS-Domäne). Ich habe die früheren `ep_*`-Gerätehelfer deshalb aus den [../claude-ha-config-dateien/](../claude-ha-config-dateien/) entfernt und nur noch als Kommentar dokumentiert.
**Frage:** Sind die `ems_*`-Gerätehelfer (`…_leistung_w`, `…_technische_freigabe`, `…_min/max_technisch_w/a`) im **HEMS-Repo schon definiert** — oder soll ich für dich ein **`ems_*`-Template-Paket** (`<domain>_ems.yaml`) als Vorlage mitliefern?

Antwort: Ja alle Enitäten/Helfer die mit <Domäne>.ems_ benannt sind sind im HEMS definiert und man muss dafür kein eigenes Schema anlegen

### A4 — Batterie: schreibt EP überhaupt einen Vorschlag?
Die Batterie ist immer **Prio 1** und immer **freigegeben** (D-016) → `prio_vorschlag`/`freigabe_vorschlag` wären konstant. Sie lädt nur PV-Überschuss.
**Frage:** Schreibt EP für die Batterie **gar keinen** `ep_*`-Vorschlag — oder z. B. eine `geschutzte_mindestleistung_w_vorschlag` (reservierte Mindest-Ladeleistung)? (Bestimmt, welche `sensor.ep_batterie_*`-Entitäten EP überhaupt anlegt.)

Antwort: ep_geschutzte_mindestleistung_w_vorschlag ist gut, der wird für die Batterie aktuell verwendet

---

## B — Geparkt / später

### B1 — Ampere-Varianten (`_a`) = Vorgriff auf Ampere-Gerät?
Sowohl read (`ems_XXX_min/max_technisch_a`) als auch write (`ep_XXX_geschutzte_mindestleistung_a_vorschlag`) haben jetzt Ampere-Varianten. Kein Phase-1-Gerät nutzt Ampere (deutet auf Wallbox/E-Auto).
**Frage (nur Bestätigung):** `_a` ist vorausschauend; Schema jetzt schon so festziehen? — Keine sofortige Aktion.

Antwort:

### B2 — Schreibweise/Umlaute der Suffixe
In der `.txt` stehen `geschutzte` (ohne ü), `heizlufter` (ohne ü). Regel 3 verlangt deutsche HA-Namen.
**Frage:** Entity-IDs bewusst ASCII (ohne Umlaute, wie HEMS) lassen und nur die `name:`-Anzeige mit Umlauten — oder durchgängig normalisieren? (Betrifft auch `heizluefter` vs. `heizlufter`.)

Antwort:

### B3 — Hybrid-Modus: fixierbare Felder pro Gerät *(aus v5 übernommen)*
Im Hybrid-Modus (D-009/D-020) fixiert der User Werte, die für die KI hart werden. Welche Felder sollen pro Gerät fixierbar sein? Ich lege bei M3 einen konkreten Vorschlag vor. → [../plan/12-steuermodi.md](../plan/12-steuermodi.md).

Antwort:

### B4 — Plan-JSON-Schema gemeinsam mit HEMS *(aus v5 übernommen)*
Sobald die HEMS-Plan-API (Ebene 2, D-002) ansteht: Schema-Version + Felder gemeinsam im HEMS-Repo pflegen. → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort:

---

## Erledigt / Verweis
v5-A2…A6 → Decision Log **D-029…D-033**. v5-A1 durch `.txt`-Aktualisierung selbst aufgelöst.
