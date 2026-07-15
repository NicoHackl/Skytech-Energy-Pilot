# Vorschläge: stabilere & plausiblere KI-Ergebnisse

> Ergänzung und Priorisierung zu [`longterm_plan.md`](./longterm_plan.md). Fokus auf zwei Ziele: **Stabilität über mehrere Aufrufe** und **Plausibilität** („als hätte ein Mensch geplant"). Basiert auf Code-Review (Stand `app/energy_pilot/`) und dem bestehenden Langzeitplan.
>
> **Leitsatz: Determinismus rahmt, KI füllt.**

## 0. Kernbefund

Der bestehende Langzeitplan beschreibt bereits die richtige Zielarchitektur (deterministischer Basisplan → KI liefert nur begrenzte Deltas → deterministische Glättung → HEMS-Dry-Run). Er ist aber **größtenteils noch nicht implementiert**, und ein paar besonders wirksame Stabilitäts-Tricks fehlen ganz. Zentrale These: **Stabilität darf nicht vom LLM erwartet werden – sie muss deterministisch erzwungen werden.** Das LLM liefert Strategie; die Determinismus-Schicht garantiert Ruhe.

## 1. Ist-Zustand im Code – warum die Ergebnisse heute schwanken

| Ursache | Fundstelle | Wirkung |
|---|---|---|
| Vorplan wird nie geladen | `planner.run()` (`planner.py:118-275`) nutzt `latest_plan()` (`planner.py:277-296`) nicht | Jeder Lauf startet bei Null, kein Anker → freies Neu-Erfinden |
| Delta-Limit/Hysterese fehlt | Validator Stage 5 = TODO (`validator.py:12-14`); D-021 (±20 %/±10 %) nur Spec | Nichts dämpft Lauf-zu-Lauf-Änderungen |
| Confidence-Gate tot | `min_confidence_percent=70` (`config.py:29`) wird nirgends gelesen | Unsichere KI-Pläne werden trotzdem veröffentlicht |
| Freshness-Gate fehlt | Validator Stage 4 = TODO | Veraltete/ungültige Messwerte → trotzdem neuer Plan |
| KI erfindet **alle** Werte aus verrauschten Mittelwerten | Prompt in `plan_context.py:361-403`; Kontext aus 1/15/60-min-Means (`roles.py:25-33`) | Mikro-Drift (z. B. 812 W vs. 819 W) kippt Prio/Freigabe |
| `temp=0`/`seed=42` verpuffen | `gemini_provider.py:74-86`, Prompt wechselt jeden Lauf (Zeitstempel + Live-Means, `plan_context.py:394-403`) | Kein identischer Prompt → kein identisches Ergebnis |
| Feedback nie zurückgeführt | `plan_feedback.py`/`hems_feedback` nur für Status-Sensoren (`hems_status_collector.py`) | System lernt nicht aus Plan-vs-Ist |
| Kein Basisplan, keine Bilanzprüfung | – | Keine ökonomisch/physikalisch plausible Untergrenze |

Was heute **schon** stabilisiert: nur die strukturelle Normalisierung im Validator (Clamp harter Grenzen, Prio-Renumbering 10/20/30…, Fallback-Fill – `validator.py:169-249`). Das glättet die **Struktur** einer Einzelantwort, nicht das **Verhalten über Läufe**.

## 2. Leitprinzip

**Determinismus rahmt, KI füllt.** Stabilität lebt in der deterministischen Schicht (Basisplan + Glättung + Gates), nicht im LLM. Die KI liefert Strategie, begrenzte Deltas und Erklärung. Kein KI-Urteil hebt je eine lokale oder HEMS-seitige Ablehnung auf (deckt sich mit `longterm_plan.md` Abschnitt 7).

## 3. Gruppe A – Stabilität über Aufrufe (höchste Priorität)

**A1 · Vorplan laden und in die Pipeline geben** *(Voraussetzung für alles Weitere)*
`run()` lädt `latest_plan()` und reicht ihn (a) an die Glättungsschicht und (b) kondensiert an die KI als `previous_plan`. Betrifft `planner.py` `run()`, `plan_context.build_context()`. → `longterm_plan.md` Abschn. 5 + 6/Schritt 6. **Aufwand gering, Hebel hoch.**

**A2 · Deterministische Anti-Flatter-Schicht (Validator Stage 5)** *(der eigentliche Stabilitätsgarant)*
- Delta-Clamp pro Lauf: Leistung ±20 %, Batterie ±10 % (D-021-Defaults, konfigurierbar).
- Hysterese auf Freigabewechsel: `freigabe` flippt erst nach **N=2 konsistenten Läufen** (Zähler persistieren).
- Mindesthaltezeit: Prio/Freigabe nicht erneut ändern innerhalb X min nach letzter Änderung.
- Prio-Wechsel nur bei **materiell** anderer Dringlichkeit (Totband auf `urgency`), nicht bei Zahlenrauschen.

Deterministisch, testbar, LLM-unabhängig. Betrifft `validator.py` (neue Stage) + kleine DB-Erweiterung für Zähler/letzte-Änderung. → `longterm_plan.md` Abschn. 6 (dort als Defaults spezifiziert).

**A3 · Eingangs-Quantisierung / Snapping** *(neu ggü. Langzeitplan)*
Die an die KI gegebenen Werte runden: Leistung auf 50–100 W, SOC auf 1–5 %, Prognosen auf grobe Stufen, Dringlichkeit in diskrete Bänder. Absolute `valid_from`/`valid_until` nicht hochpräzise in den reasoning-relevanten Datenblock; stattdessen gerundetes Fenster + „Zeit bis Deadline" in Stufen. **So verändern kleine Sensor-Schwankungen den Prompt nicht → gleicher Input → gleiche Antwort** (nutzt `temp=0`/`seed=42` endlich aus). Betrifft `plan_context._condense_*`.

**A4 · Confidence-Gate verdrahten** *(trivial)*
`min_confidence_percent` (`config.py:29`) tatsächlich lesen: `confidence < Schwelle` → letzten gültigen Plan halten bzw. Basisplan publizieren, keinen volatilen neuen. → `longterm_plan.md` Abschn. 6.

**A5 · Freshness-/Qualitäts-Gate (Validator Stage 4)**
Pro Signal Alter (`max_age_s`) und Qualität `good/degraded/invalid` prüfen. Kritisch veraltet/ungültig → konservativer Fallback **oder kein neuer Plan**, nie eine kreative KI-Schätzung. Setzt Zeitstempel-Mitführung im Collector voraus. → `longterm_plan.md` Abschn. 3 + 6.

**A6 · Lokaler Basisplan vor der KI** *(strukturelles Kernstück, größerer Umbau)*
Deterministischer Basisplan (`longterm_plan.md` Abschn. 4) minimiert bereits die Änderung ggü. Vorplan; die KI liefert nur **begrenzte Deltas** darauf (Abschn. 5). Das kappt strukturell, wie stark die KI destabilisieren kann, und ist zugleich der Fallback bei KI-Ausfall. Betrifft neues Modul (z. B. `baseplan.py`), `planner.run()`, Umstellung des Antwortschemas auf Deltas.

## 4. Gruppe B – Plausibilität / menschlich (Sinn für die Gegebenheiten)

**B1 · Kontinuität & Gedächtnis in den Kontext.** Vorplan (A1) + kurzer „was hat sich geändert"-Delta. Feedback zurückführen (`longterm_plan.md` Abschn. 8): letzter Plan vs. Ist aus `hems_feedback` → z. B. „PV-Prognose gestern +20 % zu hoch" → Sicherheitsabschlag. So lernt auch ein Mensch.

**B2 · Trend-Features statt Momentaufnahme.** PV steigend/fallend, Lasttrend, Restenergie PV heute, Prognosefehler/Unsicherheit (`longterm_plan.md` Abschn. 3). Ein Mensch plant aus dem Verlauf, nicht aus einem Messpunkt.

**B3 · Transparente Dringlichkeits-Formel.** `urgency = 0.4·deadline + 0.3·energy_need + 0.2·comfort_gap + 0.1·availability_risk` (`longterm_plan.md` Abschn. 3) deterministisch berechnen, diskretes Band an die KI. KI kommentiert/verschiebt strategisch, überschreibt keine harten Grenzen.

**B4 · Reason-Codes erzwingen.** Jede KI-Änderung braucht einen Reason-Code aus fester Liste (`longterm_plan.md` Abschn. 5: `reason_codes[]`, `strategy`). Änderung ohne gültigen Reason-Code → verwerfen. Ein menschlicher Plan hat pro Entscheidung einen Grund; unterdrückt willkürliches Flip-Flop.

**B5 · Physik-/Energiebilanz-Leitplanken.** Summe geplanter Lasten ≤ verfügbarer PV-Überschuss + Batterie + Netzlimit; keine diskretionäre Last in eine bekannte PV-Lücke; keine Freigabe bei Deadline-Konflikt. Gehört überwiegend in den Basisplan (A6) – deshalb macht „Basisplan zuerst" auch plausibler. Heute fehlt jede Ökonomie-/Bilanzprüfung.

## 5. Gruppe C – stabil bleiben über die Zeit (Prozess)

**C1 · Regressionstests mit festen Szenarien** (`longterm_plan.md` Phase 2). Golden-Szenarien inkl. fehlerhafter/veralteter Daten. Assertions: zwei Läufe auf quasi-gleichen Inputs → **keine** unnötigen Freigabe-/Prio-Wechsel; Basisplan sicher bei KI-Ausfall. Andocken an bestehende ~40 Tests in `app/tests/`.

**C2 · Stabilitäts-KPI + Shadow-Mode** (`longterm_plan.md` Phase 4 / Abschn. 11). KPI „Planstabilität zwischen Läufen" = Anzahl unnötiger Freigabe-/Prio-Wechsel pro Tag. KI-Variante im Schatten gegen Basisplan messen, bevor man ihr vertraut. A/B: Basisplan vs. Basisplan+KI.

**C3 · Optionaler Kritiker-Call nur bei Hochrisiko** (`longterm_plan.md` Abschn. 7). Zweiter kleiner KI-Call nur bei großer Abweichung/Freigabewechsel/vielen Clamps/schlechter Datenqualität. `{verdict, issues[], patches{}}`. Positives Urteil hebt nie eine lokale/HEMS-Ablehnung auf. Später, nicht zuerst.

## 6. Zuordnung zu `longterm_plan.md` (Lücken & Vorziehen)

| Empf. | Langzeitplan | Status im Code | Einordnung |
|---|---|---|---|
| A1 Vorplan laden | Abschn. 5/6 | ✅ umgesetzt (v0.0.50) | **erledigt** (Voraussetzung) |
| A2 Anti-Flatter | Abschn. 6 | Stage 5 = TODO | **vorziehen** |
| A3 Quantisierung | – | fehlt | **neu** |
| A4 Confidence-Gate | Abschn. 6 | Config tot | **vorziehen** (trivial) |
| A5 Freshness-Gate | Abschn. 3/6 | Stage 4 = TODO | **vorziehen** |
| A6 Basisplan | Abschn. 4/5 | fehlt | Phase 2/3 (groß, Kern) |
| B1 Feedback/Vorplan | Abschn. 8 | gespeichert, ungenutzt | mittel |
| B2 Trends | Abschn. 3 | teilweise (Aggregator) | mittel |
| B3 Urgency-Formel | Abschn. 3 | fehlt | mittel |
| B4 Reason-Codes | Abschn. 5 | fehlt | mittel |
| B5 Bilanz-Leitplanken | implizit | fehlt | mit A6 |
| C1/C2/C3 | Phase 2/4, Abschn. 7 | fehlt | später |

## 7. Vorgeschlagene Reihenfolge (Quick-Wins zuerst)

- **Stufe 0** (risikoarm, sofort spürbar): **A1 + A4 + A5 + A3**. Diese vier stabilisieren Lauf-zu-Lauf massiv, ohne Architekturumbau.
- **Stufe 1** (Anti-Flatter): **A2 + B4 + B3**.
- **Stufe 2** (Kern): **A6 Basisplan** + Schema auf Deltas (B5 fällt mit rein).
- **Stufe 3** (lernen/absichern): **B1 Feedback, C1 Tests, C2 Shadow/KPI, C3 Kritiker**.

## 8. Verifikation (sobald umgesetzt)

- **Doppellauf-Test:** zweimal `POST /api/plan/run` auf quasi-identischen Inputs → Diff der `plans`-Zeilen; Ziel: keine Prio-/Freigabe-Änderung.
- **Szenario-Tests** in `app/tests/` (fixe Snapshots), inkl. veralteter Daten → erwartet Fallback/kein Plan.
- **Manuell:** Live-Werte in HA um ±1–2 % variieren → Plan darf nicht kippen.
- **KPI-Log:** Freigabe-/Prio-Wechsel pro Tag aus `audit`-Tabelle beobachten.
