# Claude-Fragen — v10 (Stand 26.06.2026)

> **STATUS:** v9 verarbeitet — **O2/O3 → Decision Log D-045** umgesetzt (v0.0.22): Pagination 1–5
> je Timeline + **verpflichtender Tages-Call-Budget-Schutz** (≤1000/Tag, UTC, persistent) sowie
> **Unwetter-Alerts** (vorerst nur Daten/Anzeige). **O1/O4/O5** sind **für die Zukunft geparkt**
> (siehe unten, Abschnitt Z). Die **B-Fragen aus [claude-fragen-v6.md](claude-fragen-v6.md)
> (B1–B4)** bleiben **weiterhin offen** und laufen hier unter B weiter.
> Format wie gehabt: Antwort direkt unter die Frage; ich übernehme sie danach nach
> [../plan/entscheidungen.md](../plan/entscheidungen.md) und entferne sie in v11.

---

## B — Geparkt / später (aus v6 weitergeführt)

### B1 — Ampere-Varianten (`_a`) = Vorgriff auf Ampere-Gerät?
Sowohl read (`ems_XXX_min/max_technisch_a`) als auch write (`ep_XXX_geschutzte_mindestleistung_a_vorschlag`)
haben Ampere-Varianten. Kein Phase-1-Gerät nutzt Ampere (deutet auf Wallbox/E-Auto). HEMS unterstützt
Ampere bereits nativ pro Gerät via `output_unit: ampere` (Suffix `_a` + `min_umschaltzeit_s`).
**Frage (nur Bestätigung):** `_a` ist vorausschauend; Schema jetzt schon so festziehen? — Keine sofortige Aktion.

Antwort:

### B2 — Schreibweise/Umlaute der Suffixe
In der `.txt` stehen `geschutzte` (ohne ü), `heizlufter` (ohne ü). Regel 3 verlangt deutsche HA-Namen.
HEMS-Evidenz: Entity-IDs durchgängig **ASCII ohne Umlaute** (`prioritat`, `geschutzte`, `anderung`).
**Frage:** Entity-IDs bewusst ASCII (wie HEMS) lassen und nur die `name:`-Anzeige mit Umlauten —
oder durchgängig normalisieren? (Betrifft auch `heizluefter` vs. `heizlufter`.)

Antwort:

### B3 — Hybrid-Modus: fixierbare Felder pro Gerät *(aus v5 übernommen)*
Im Hybrid-Modus (D-009/D-020) fixiert der User Werte, die für die KI hart werden. Welche Felder sollen
pro Gerät fixierbar sein? Konkreter Vorschlag kommt bei M3. → [../plan/12-steuermodi.md](../plan/12-steuermodi.md).

Antwort:

### B4 — Plan-JSON-Schema gemeinsam mit HEMS *(aus v5 übernommen)*
Sobald die HEMS-Plan-API (Ebene 2, D-002) ansteht: Schema-Version + Felder gemeinsam im HEMS-Repo pflegen.
**Neu zu klären:** Suffix-Mapping beim späteren 1:1-Schreibweg (EP `prio_vorschlag` ↔ HEMS `prioritat`;
`_vorschlag` entfällt HEMS-seitig). → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort:

---

## Z — One Call 4.0: für die Zukunft geparkt (keine sofortige Aktion)

> Diese drei Punkte wurden in v9 bewusst auf „später" gelegt; hier nur als Merkposten, **keine offene
> Frage**. Wenn einer davon konkret wird, kommt er als eigene Frage zurück.

- **O1 — `current`-Ist-Wetter:** vorerst **nicht** implementieren, für die Zukunft im Hinterkopf behalten.
- **O4 — mehrere Timelines gleichzeitig ans LLM:** vorerst **eine** Timeline; Zukunftsidee z.B.
  15-min-Timeline für ~3 h **plus** 1h-Timeline für ~2 Tage.
- **O5 — historische Daten (47 Jahre) für PV-Kalibrierung:** im aktuellen Scope **kein** Thema
  (geringer Einfluss); für **V2+** vorstellbar.
