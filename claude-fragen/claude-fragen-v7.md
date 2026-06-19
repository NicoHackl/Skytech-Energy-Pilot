# Claude-Fragen — v7 (Stand 19.06.2026)

> Fortführung der geparkten B-Fragen aus [claude-fragen-v6.md](claude-fragen-v6.md). Die v6-A-Fragen sind beantwortet und nach [../plan/entscheidungen.md](../plan/entscheidungen.md) **D-034…D-037** übernommen.
> **Neu:** Ich habe jetzt **lokalen Zugriff auf das HEMS** ([../../SkytechHEMS/](../../SkytechHEMS/)) und konnte die offenen Punkte gegen den HEMS-Quellcode prüfen — bei B1/B2 liegt unten konkrete Evidenz, B4 hat einen neuen Unterpunkt.
> Format wie gehabt: Antwort direkt unter die Frage; ich übernehme sie danach nach entscheidungen.md und entferne sie in v8.

---

## B — Geparkt / später

### B1 — Ampere-Varianten (`_a`) jetzt schon festziehen?
Sowohl read (`ems_XXX_min/max_technisch_a`) als auch write (`ep_XXX_geschutzte_mindestleistung_a_vorschlag`) haben Ampere-Varianten. Kein Phase-1-Gerät nutzt Ampere (deutet auf Wallbox/E-Auto).
**HEMS-Evidenz (neu):** Das HEMS unterstützt Ampere bereits **nativ pro Gerät** über `output_unit: ampere` — dann erzeugt es genau die `_a`-Suffixe (`geschutzte_mindestleistung_a`, `min/max_technisch_a`, `max/min_anderung_pro_schritt_a`) und zusätzlich `min_umschaltzeit_s` (Phasenwechsel). Das `_a`-Schema ist also nicht spekulativ, sondern deckt sich 1:1 mit dem HEMS.
**Frage (nur Bestätigung):** Schema mit `_w`/`_a` jetzt schon so festziehen (EP wählt die Einheit pro Gerät analog HEMS `output_unit`)? — Keine sofortige Aktion.

Antwort:

### B2 — Schreibweise/Umlaute der Suffixe & Gerätenamen
Regel 3 verlangt deutsche HA-Namen; die `.txt` schreibt `geschutzte` (ohne ü), `heizlufter` (ohne ü), unsere YAMLs nutzen `heizluefter` (ue), das Plan-Doc teils `heizlüfter` (ü). Das ist aktuell **inkonsistent**.
**HEMS-Evidenz (neu):** Das HEMS verwendet in seinen Entity-IDs durchgängig **ASCII ohne Umlaute** und ohne ue-Ersatz: `prioritat`, `geschutzte_mindestleistung`, `anderung`, `abschaltverzogerung`. Der gerätespezifische Teil kommt aus dem frei konfigurierten `entity_prefix`.
**Frage:** Übernehmen wir die HEMS-Linie — **Entity-IDs ASCII ohne Umlaute** (also `heizlufter`/`geschutzte`/`prio`), nur die `name:`-Anzeige mit Umlauten — und ziehen das überall durch (auch `heizluefter` → `heizlufter`)? Oder bevorzugst du `ue`-Ersatz (`heizluefter`) bzw. echte Umlaute in der ID?

Antwort:

### B3 — Hybrid-Modus: fixierbare Felder pro Gerät *(aus v5/v6 übernommen)*
Im Hybrid-Modus (D-009/D-020) fixiert der User Werte, die für die KI hart werden. Welche Felder sollen pro Gerät fixierbar sein? Ich lege bei M3 einen konkreten Vorschlag vor. → [../plan/12-steuermodi.md](../plan/12-steuermodi.md).

Antwort:

### B4 — Plan-JSON-Schema & 1:1-Schreibweg gemeinsam mit HEMS *(aus v5/v6 übernommen)*
Sobald die HEMS-Plan-API (Ebene 2, D-002) ansteht: Schema-Version + Felder gemeinsam im HEMS-Repo pflegen. → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).
**Neuer Unterpunkt (HEMS-Abgleich):** Beim späteren 1:1-Schreibweg (D-032) sind die Suffixe **nicht** string-identisch. EP schreibt `ep_<p>_prio_vorschlag` / `…_freigabe_vorschlag` / `…_geschutzte_mindestleistung_<w|a>_vorschlag`; im HEMS heißen die Pendants `ems_<p>_prioritat` / `ems_<p>_freigabe` / `ems_<p>_geschutzte_mindestleistung_<w|a>` (ohne `_vorschlag`, `prio`→`prioritat`).
**Frage:** Soll der spätere HEMS-Endpunkt die EP-Vorschlagsnamen 1:1 annehmen und intern mappen — oder definieren wir die HEMS-Aufnahmevariablen mit eigenem `*_vorschlag`-Satz, getrennt von den User-`ems_*`-Werten? (Entscheidung erst zu M3 nötig.)

Antwort:

---

## Erledigt / Verweis
v6-A1…A4 → Decision Log **D-034…D-037** (erstmals gegen lokalen HEMS-Quellcode verifiziert). v5-A2…A6 → **D-029…D-033**.
