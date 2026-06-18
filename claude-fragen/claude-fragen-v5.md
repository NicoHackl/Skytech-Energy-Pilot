# Claude-Fragen — v5 (Stand 17.06.2026)

> Neue Fragen aus dem Wissen von [../user-beispiele/variablen-zugriff.txt](../user-beispiele/variablen-zugriff.txt) bzw. der strukturierten [../user-beispiele/variablen-zugriff.md](../user-beispiele/variablen-zugriff.md).
> Format wie gehabt: Antwort direkt unter die Frage schreiben; ich übernehme sie danach nach [../plan/entscheidungen.md](../plan/entscheidungen.md) und entferne sie in v6.
> Die geparkten B-Fragen aus [claude-fragen-v4.md](claude-fragen-v4.md) laufen hier unter B weiter.

---

## A — Aktuell projektrelevant (betrifft Namensschema & gelieferte HA-Config jetzt)

### A1 — Suffix-Schema der technischen Grenzwert-Helfer weicht ab
Die `.txt` nennt für die vom User gepflegten technischen Werte:
`XXX_technische_freigabe`, `XXX_min_technisch_w`, `XXX_max_technisch_w`, `XXX_leistung_w`.
Meine gelieferten Helfer ([../claude-ha-config-dateien/](../claude-ha-config-dateien/)) heißen aktuell `ep_heizstab_freigabe`, `ep_heizstab_leistung_maximal` usw. — also **anderes Suffix-Schema**.
**Frage:** Soll ich auf das `.txt`-Schema umstellen (`…_technische_freigabe`, `…_min_technisch_w`, `…_max_technisch_w`)?

Antwort:

### A2 — Prefix-Domäne der technischen Werte: `ep_` oder `ems_`?
Diese technischen Grenzwerte/Freigaben sind laut `.txt` „**HEMS-Werte, die vom User gepflegt werden**", die EP nur **liest**.
**Frage:** Liegen sie als **HEMS-Entitäten** (`ems_*`, evtl. schon im HEMS vorhanden) vor, die EP einfach mitliest — oder soll ich sie weiter als eigene `ep_*`-Helfer ausliefern? (Falls `ems_*`: keine Duplikate in [../claude-ha-config-dateien/](../claude-ha-config-dateien/) nötig.)

Antwort:

### A3 — EP-Schreibvertrag = nur Priorität + geschützte Mindestleistung?
Laut `.txt` schreibt EP **ausschließlich**: `XXX_prio_vorschlag` und `XXX_geschutzte_mindestleistung_w` / `_a`.
Frühere Beispiele (CLAUDE.md) nannten EP-Vorschläge wie `ep_batterie_1_ziel_soc` oder max. Ladeleistung als Vorschlag.
**Frage:** Ist der EP-Schreibvertrag damit reduziert auf **(a) Prioritäts-Vorschlag** und **(b) geschützte Mindestleistung**, und HEMS macht die eigentliche Sollwert-/SOC-Regelung? Sind die alten Vorschlags-Beispiele damit überholt?

Antwort:

### A4 — Binärverbraucher `XXX_leistung_w` vs. „feste 1500 W, kein Helfer"
Die `.txt` sagt: EP liest für **Binärverbraucher** `XXX_leistung_w`.
In D-017/D-018 (und meiner [input_number_ep.yaml](../claude-ha-config-dateien/input_number_ep.yaml)) habe ich für die Heizlüfter **keinen** Leistungs-Helfer angelegt, weil sie fest 1500 W haben.
**Frage:** Braucht **jeder** Binärverbraucher doch einen (festen, user-gepflegten) `…_leistung_w`-Wert, damit EP die **Lastgröße** für die Energieplanung kennt? Dann lege ich pro Binärgerät einen `…_leistung_w`-Helfer an.

Antwort:

### A5 — Schreibweg in V1: HEMS-Endpunkt vs. HA-Helfer (D-002)
Die `.txt` sagt: EP schreibt die Vorschläge „in HA-Variablen **und** über einen **HTTP-API-Endpunkt** in **interne Variablen des HEMS**".
D-002 hat aber V1 = **nur** HA-Helfer / `/api/set` festgelegt (direkter interner Variablen-/Plan-Endpunkt erst **Ebene 2** im HEMS-Repo).
**Frage:** Beschreibt die `.txt` das **Zielbild (Ebene 2)** oder schon V1? Welche Werte gehen als HA-Helfer, welche über den HEMS-Endpunkt — und ab welcher Stufe?

Antwort: Es beschreibt den Sollzustand später, nicht jetzt am Anfang gleich, am Anfang werden nur Vorschlagswerte in HA-Helfer/Entiäten geschrieben und später dann zustäzlich direkt in HEMS Endpunkte/inter Variablen, und dann werden die werte exakt gleich geschrieben, bedeutet das es gleich viele Endpunkte wie HA-Helfer gibt

### A6 — Wann *wirken* die EP-Vorschläge in der HEMS-Regelung?
Die `.txt` sagt: HEMS bildet die `XXX_anforderung` aus den **vom User festgelegten Werten**; EP schreibt seine Vorschläge separat in HEMS-Variablen.
**Frage:** Ab wann greifen `…_prio_vorschlag` / `…_geschutzte_mindestleistung` tatsächlich in die HEMS-Regelung ein — erst im **Shadow/Autopilot** bzw. abhängig vom **Steuermodus** ([../plan/12-steuermodi.md](../plan/12-steuermodi.md))? Im Modus „Vorschlagen" bleiben sie reine Anzeige?

Antwort: Damit bracuhst du dich aktuell nicht beschäftigen, aktuell ist es nur wichtig das die vorschlagswerte in die entitäten ep_XXX_vorschlag geschrieben werden und dann werden die vorerst von mir selber in HA Automation verwendet und getestet, später soll es so sein das sie in HA lediglich der Übersichtlichkeit der Daten dienen (Dashboardnutzung etc.) und die eingetliche auswertung passiert dann im HEMS wenn die Vorschlagswerte über die API direkt in HEMS variablen geschrieben werden

---

## B — Geparkt / später

### B1 — `geschutzte_mindestleistung_a` (Ampere) = Vorgriff auf Ampere-Gerät?
Die Ampere-Variante deutet auf ein späteres Gerät mit Ampere-Sollwert (Wallbox/E-Auto). Kein Phase-1-Gerät nutzt Ampere.
**Frage (nur Bestätigung):** `_a` ist vorausschauend fürs spätere Ampere-Gerät; Schema jetzt schon so festziehen? — Keine sofortige Aktion.

Antwort:

### B2 — Schreibweise/Umlaute der Suffixe
In der `.txt` stehen `geschutzte` (ohne ü) und `heizlufter` (ohne ü). Regel 3 verlangt deutsche HA-Namen.
**Frage:** Entity-IDs bewusst ASCII (ohne Umlaute, wie HEMS) lassen und nur die `name:`-Anzeige mit Umlauten (`Heizlüfter`, `geschützte`)? Oder durchgängig normalisieren?

Antwort:

### B3 — Hybrid-Modus: fixierbare Felder pro Gerät *(aus v4 übernommen)*
Im Hybrid-Modus (D-009/D-020) fixiert der User Werte, die für die KI hart werden. Welche Felder sollen pro Gerät fixierbar sein? Ich lege bei M3 einen konkreten Vorschlag vor. → [../plan/12-steuermodi.md](../plan/12-steuermodi.md).

Antwort:

### B4 — Plan-JSON-Schema gemeinsam mit HEMS *(aus v4 übernommen)*
Sobald die HEMS-Plan-API (Ebene 2, D-002) ansteht: Schema-Version + Felder gemeinsam im HEMS-Repo pflegen. → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort:

---

## Erledigt / Verweis
v4 hatte keine offenen A-Fragen; die geparkten v4-B-Fragen laufen hier als **B3/B4** weiter.
