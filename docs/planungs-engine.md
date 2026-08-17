# Planungs-Engine

## Ablauf eines Planungslaufs (`planner.py: Planner.run()`)

Ausgelöst **nur manuell** über `POST /api/plan/run` (siehe
[bekannte-luecken.md](bekannte-luecken.md#kein-automatischer-scheduler)):

1. Snapshot aller Collector (Mess-Rollen, Geräte, Prognose, Wetter).
2. `build_constraints()` — harte Grenzen je Gerät ([geraete.md](geraete.md)); `valid_from`/
   `valid_until` werden auf das **15-Minuten-Raster** abgerundet (`_floor_to_grid`, D-063).
3. **Klassifizierungs-Aufruf (D-055):** `load_ziele()` — user-definierte Ziele
   (Tab "Grenzen und Ziele", ohne Gewicht). Gibt es welche, baut
   `build_classification_context()` dieselbe Datenbasis wie der Plan-Aufruf (nur `objectives`
   durch `ziele` ersetzt), `build_classification_prompt()`/`build_classification_response_schema()`
   den Aufruf, `provider.generate()` liefert je Ziel-`id` ein Gewicht 0–100 %,
   `objectives_from_classification()` baut daraus die `Objective`-Liste. Scheitert dieser
   Aufruf, gilt der **gesamte** Planungslauf als gescheitert (`error="classification_error"`,
   kein stiller Fallback). Ohne konfigurierte Ziele entfällt der Aufruf ersatzlos
   (`objectives = []`).
4. `build_context()` (`plan_context.py`) — komprimierter KI-Kontext (Datenminimum, Eiserne Regel 12),
   inkl. der oben abgeleiteten `objectives`.
5. `planning_instruction()` + `build_data_block()` — Instruktion und Datenblock **getrennt**
   (D-062): die (editierbare) Instruktion geht in den System-Kanal des Anbieters, die Daten als
   User-Nachricht. `build_prompt()` liefert weiterhin die zusammengesetzte Form für UI,
   Persistenz und Hash. Der Prompt kann die Datenübergabe nicht umgehen.
6. `context_hash()` — SHA-256 über den quantisierten Kontext + Instruktion + Modellname (D-063).
   Stimmt er mit dem letzten **gültigen, noch laufenden** Plan überein, wird dieser
   wiederverwendet: **kein** KI-Aufruf, Audit-Eintrag `plan_reused`, Ergebnis mit `reused=true`.
7. `build_response_schema()` — Gemini-Response-Schema.
8. `provider.generate(data_block, schema, system=instruction)` — KI-Aufruf, ratenlimitiert.
   Meldet der Provider `sampling_dropped`, wird das als WARNING geloggt und in `ai_calls`
   vermerkt (D-063).
9. `CandidatePlan` zusammenbauen — **EP selbst** setzt `plan_id` (`uuid4().hex[:12]`), `valid_from`, `valid_until` (= Rasterzeit + `planning_interval_min`); das Modell liefert nur Geräte-Vorschläge samt `begruendung`/`angewandte_regeln`, die Konfidenz-**Teilnoten**, `unsicherheiten`, `reasoning`, `warnings`.
10. **Reparatur-Pass:** fehlen Pflichtfelder (`missing_suggestion_fields()`) und `ai_repair_missing` ist aktiv → ein gezielter Nachforder-Aufruf mit `build_repair_prompt()`; der reparierte Plan wird nur übernommen, wenn er die Lückenzahl **strikt** verringert.
11. `validate(plan, constraints, now=…, context=…, min_confidence=…)` — siehe
    [sicherheit-datenschutz.md](sicherheit-datenschutz.md).
12. Speichern in Tabelle `plans` (inkl. `prompt`, `context_json`, `response_json`,
    `context_hash`, `publish_blocked` — D-063) + Audit-Log (`plan_created`/`plan_rejected`).
13. Bei gültigem Plan, **ohne** `publish_blocked` und mit `publish_suggestions: true` →
    `suggestion_publisher.publish_suggestions()`. Ein am Konfidenz-Gate gescheiterter Plan
    liefert stattdessen ein `published`-Ergebnis mit Begründung (D-064).

Token-Zähler (`ai_call.tokens_in/out`) summieren Klassifizierungs- **und** Plan-Aufruf
(`_sum_tokens()`); beide Aufrufe werden einzeln in `ai_calls` protokolliert.

**Klassifizierung isoliert testen:** `Planner._run_classification_call()` bündelt den
Klassifizierungs-Kern (Kontext/Prompt/Schema/`generate()`/Fehlerpfad) als privaten Helfer,
den sowohl `run()` als auch `Planner.run_classification()` nutzen.
`run_classification()` (`POST /api/classification/run`, Button „Klassifizierung erzeugen“
im Plan-Tab) führt NUR diesen Klassifizierungs-Aufruf aus – ohne anschließenden Plan-Aufruf –
zum gezielten Testen von Zieldefinitionen/Klassifizierungs-Prompt. Liefert `ok=false` mit
`error="keine_ziele_konfiguriert"`, wenn keine Ziele angelegt sind.

Der Planner fängt **alle** Provider-Exceptions ab und wirft nie an den Aufrufer weiter;
DB-Schreibfehler sind mit `except sqlite3.Error: pass` abgesichert — ein Planungslauf
blockiert die Anlage nie (Eiserne Regel 13).

## KI-Provider-Abstraktion (`ai_provider.py`)

- Abstrakte Basisklasse `AIProvider.generate(prompt, response_schema, *, system=None)` —
  `system` ist die Instruktion (System-Kanal), `prompt` sind die Daten (D-062).
- `ProviderResponse.sampling_dropped` meldet, dass der Anbieter `temperature`/`seed` verworfen
  hat; der Planner protokolliert das (D-063).
- `AsyncRateLimiter` — gleitendes 60-s-Fenster, **wartet** statt zu fehlern
  ("Wartedrossel statt Fehlerflut") — kein Request wird verworfen, nur verzögert.
- `ProviderError`/`RateLimitError`-Exception-Hierarchie.

Seit D-056 gibt es **drei** austauschbare Anbieter, alle als schlanke aiohttp-REST-Clients
(kein SDK) hinter derselben Abstraktion. `main.py` baut per `resolve_active_provider()`
genau den Anbieter, der in `provider` gewählt ist — und nur, wenn dessen `api_key` gesetzt ist:

| Modul | Anbieter | Besonderheit |
|---|---|---|
| `gemini_provider.py` | Google Gemini | `responseSchema` + `generationConfig` (siehe unten) |
| `claude_provider.py` | Anthropic Claude | Messages-API, `output_config.format`; **keine** Sampling-Parameter (`temperature`/`seed` werden nicht gesendet) |
| `openai_provider.py` | OpenAI GPT | Chat-Completions, `response_format` (Strict-JSON-Schema); Retry ohne `temperature`/`seed` für Reasoning-Modelle wie `gpt-5` — der Fehlertext muss den Parameter **namentlich** nennen, ein generisches „unsupported“ reicht nicht mehr (D-063) |

`schema_convert.to_json_schema()` übersetzt das code-seitig gebaute **Gemini**-Antwortschema
(`build_response_schema()`) in Standard-JSON-Schema für Claude/OpenAI — es gibt bewusst nur
**eine** Schema-Quelle, die anderen beiden Formate sind davon abgeleitet.

## Gemini-Provider (`gemini_provider.py`)

- Direkter REST-Client (kein SDK) gegen
  `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`.
- API-Key im **Header** `x-goog-api-key` (nie in der URL — landet dadurch nie in
  Proxy-/Zugriffs-Logs).
- `generationConfig`: `responseMimeType: application/json`, `responseSchema`,
  optional `temperature`/`seed` und `thinkingConfig.thinkingBudget` (`ai_thinking_budget`,
  Default 0 = Thinking aus — bei Flash-Modellen ist es sonst aktiv und eine eigene
  Varianzquelle, D-063).
- Instruktion als `systemInstruction` (D-062), Daten als `contents[role=user]`.
- HTTP 429 → `RateLimitError`; andere ≥400 → `ProviderError` mit server-extrahierter
  Nachricht (`http_errors.read_error_body`).
- **Timeout-Falle:** aiohttps Total-Timeout wirft `asyncio.TimeoutError` = Pythons
  eingebautes `TimeoutError` seit 3.11 — das ist **kein** `aiohttp.ClientError` und
  `str(TimeoutError())` ist leer. Deshalb ein eigener `except TimeoutError`-Zweig mit
  synthetisierter Fehlermeldung (`gemini_provider.py:103-109`). Derselbe Trick taucht
  in `onecall_client.py`/`weather_client.py` auf — bei neuen HTTP-Clients dran denken.
- Default-Modell: `gemini-2.5-flash` — siehe [bekannte-luecken.md](bekannte-luecken.md#gemini-35-flash-hang)
  für die Begründung, `gemini-3.5-flash` **nicht** als Default zu verwenden.

## Determinismus-Absicherung (D-050)

Beobachtetes Problem: das Modell ließ gelegentlich Pflichtfelder aus (z. B. die
Heizstab-Max-Temperatur fehlte sporadisch). Ursache: das ursprüngliche Gemini-Schema
machte alle Gerätefelder optional, keine Temperatur-/Seed-Fixierung. Vierschichtige
Gegenmaßnahme (alle konfigurierbar):

1. **Schema-Struktur:** `devices` ist im Gemini-Schema ein **Objekt, keyed nach
   Gerätename** (nicht Array) — nur so lässt sich pro Gerät ein eigenes `required`
   (= exakter Schreibvertrag aus `plan_schema.suggestion_keys()`) plus
   `propertyOrdering` erzwingen.
2. **Determinismus:** `temperature` (Default 0.0) + fixer `seed` (Default 42) in
   `generationConfig` — nur gesetzt, wenn konfiguriert, sonst Provider-Default. **Gilt nur
   für Gemini und OpenAI**; Claude bekommt keine Sampling-Parameter. Reasoning-Modelle
   (`gpt-5`) lehnen sie ab, EP wiederholt dann ohne — sichtbar als Warnung und in
   `ai_calls.sampling_dropped` (D-063).
3. **Reparatur-Pass:** gezielter Ein-Versuch-Nachforder-Aufruf mit exakter Liste der
   fehlenden Felder (`ai_repair_missing`, Default an).
4. **Deterministische Auffüllung im Validator** (`_fill_missing_fields()`) als letzte
   Instanz — jedes fehlende Pflichtfeld wird aus dem aktuellen Ist-Zustand ergänzt
   (z. B. `freigabe` ← aktuelle technische Freigabe, Schutzleistung ← technisches
   Minimum oder 0, Extra-Feld ← aktueller Lesewert/Typ-Default), jede Auffüllung wird
   wie eine Klemmung geloggt.

## Stabilität der Werte (D-060 – D-064)

D-050 sicherte die **Vollständigkeit** der Felder. Die zweite Baustelle war die **Stabilität
der Werte**: bei gleicher Sachlage kamen unterschiedliche Vorschläge (Heizstab bei 80 °C
Warmwasser mal frei, mal gesperrt; Heizlüfter bei über 25 °C mal ein, mal aus). Ursachen und
Gegenmaßnahmen — alle **im** KI-Aufruf, nicht dahinter: nachgelagerte Dämpfung (Hysterese,
Mindesthaltezeit, Delta-Limit) ist bewusst verworfen, siehe D-060.

| Ursache | Gegenmaßnahme |
|---|---|
| Der Prompt war **nie zweimal derselbe String** (frische Zeitstempel, zappelnde Messwerte) — ein fixer `seed` konnte nichts reproduzieren | Kontext quantisieren: 15-Minuten-Raster für `valid_from`/`valid_until`, Zahlen auf fachliche Stufen (Leistung 10 W, Prozent 1, Temperatur 0,5 °C, kWh 0,1) |
| Kein Nachweis, ob zwei Läufe dieselbe Lage sahen | `context_hash()` über den quantisierten Kontext + Instruktion + Modell; `now` und `previous_plan` bleiben draußen (`_HASH_EXCLUDED_KEYS`) |
| Mehrfaches Auslösen erzeugte mehrfach etwas Anderes | Gleicher Hash + gültiger, laufender Vorplan ⇒ **Wiederverwendung ohne KI-Aufruf** |
| Absicht des Users nur als Nebenfeld im Datenblock | Freitext-Regeln je Gerät (`regeln`) und hausweit (`globale_regeln`) als eigener Block + Pflichtfelder `begruendung`/`angewandte_regeln` je Gerät |
| Sollwert als Messwert missverstanden | `rolle` je Zusatzwert (`ist`/`grenze`/`sollwert`), im Kontext samt Klartext |
| Abends keine Temperaturangabe für heute | `weather.kennzahlen` — unabhängig vom Slot-Fenster, einschließlich heute |
| Fehlender Sensor sah aus wie ein echter Wert | `veraltet: true` je Wert + `datenlage.frische_prozent`; der Prompt verlangt bei Unbekanntem die vorsichtige Variante |
| Grenzen nur als Prosa | `minimum`/`maximum` im Antwortschema (Prio 10–100, Schutzleistung im technischen Band, Zusatzwert-Grenzen) |
| Anweisung und Daten in einem Textkörper | System-Kanal je Anbieter (D-062) |
| Interne Denk-Phase der Flash-Modelle | `ai_thinking_budget` (Default 0) |
| Lauf nicht reproduzierbar, zwei Läufe nicht vergleichbar | `plans.prompt`/`context_json`/`response_json`/`context_hash` |
| Trend einer Temperatur unsichtbar | Warmwasser und Außentemperatur als **gemittelte** Mess-Rollen (D-061): steigende Speichertemperatur ohne Heizstableistung heißt „die Solarthermie lädt“ |

### Konfidenz (D-064)

`confidence` war ein freies INTEGER ohne Definition — als Grundlage eines Gates wertlos. Jetzt:

1. Das Modell liefert **vier Pflicht-Teilnoten** 0–100, jede mit Rubrik in der Schema-
   `description` und im Prompt (`plan_schema.CONFIDENCE_PARTS`): `datenlage`,
   `prognosesicherheit`, `regelklarheit`, `zielkonflikt`. Dazu `unsicherheiten` als
   Freitextliste.
2. **EP deckelt `datenlage`** gegen die gemessene Datenlage des Kontexts
   (`min(Modell, EP)`); die Abweichung wird wie eine Klemmung protokolliert.
3. **Aggregation als schwächstes Glied** (`aggregate_confidence` = Minimum, nicht Mittelwert —
   sonst rechnete eine klare Regel eine schlechte Datenlage weg).
4. Liegt das Ergebnis unter `min_confidence_percent`, setzt der Validator `publish_blocked`:
   der Plan bleibt gültig, gespeichert und sichtbar, wirkt aber nicht.

Liefert ein älteres Prompt-Template nur eine flache `confidence`, bleibt diese unangetastet.

## Kontextaufbau & Datenminimum (`plan_context.py`)

`_condense_state/_forecast/_weather/_constraint` kürzen Snapshots auf das Nötige
(Eiserne Regel 12). Wetter-Kondensierung verzweigt nach Quelle:

- **OneCall:** `_hourly_window_slots` (heute, ab jetzt, frühestens 6 Uhr, bis 21 Uhr
  Ortszeit) + `_daily_next_days_slots` (nächste 5 Tage ab morgen).
- **forecast3h `compact`:** 3-h-Schritte bis `forecast_horizon_h`.
- **forecast3h `full`:** komplette 5-Tage-Prognose.
- **Kennzahlen (D-062):** `weather_metrics()` verdichtet dieselben Rohdaten zusätzlich zu
  `temp_jetzt`, `temp_min_heute`, `temp_max_heute`, `temp_max_24h`, `temp_max_48h`,
  `pop_max_24h`, `wolken_mittel_heute` — unabhängig vom 6–21-Uhr-Fenster und **einschließlich
  heute**. Für Tageshöchst-/Tagestiefstwerte sind sie maßgeblich, nicht die Slot-Reihen.

**Zeitformate der Slots sind uneinheitlich** und stehen so im Prompt: OneCall-Slots tragen
naive **Ortszeit** (`_local_dt`), forecast3h-Slots die naive **UTC** aus dem OWM-Feld
`dt_txt`. Wer die Reihen vergleicht, muss das wissen.

Top-Level-Schlüssel des Kontexts: `now`, `valid_from`, `valid_until`, `state`, `forecast`,
`weather`, `devices`, `objectives`, `datenlage`, optional `globale_regeln` und
`previous_plan`.

Der Planungs-Prompt (`DEFAULT_PLANNING_PROMPT`) ist über die UI editierbar (Plan-Tab)
und in der DB persistiert (`config`-Tabelle, Key `PLANNING_PROMPT_KEY`) — überlebt
Neustarts **und** Addon-Updates ohne Git-Push. Der `Daten:`-Block wird davon
unabhängig immer code-seitig angehängt; das Response-Schema bleibt vollständig
code-kontrolliert; der Validator erzwingt harte Grenzen unabhängig vom Prompt-Inhalt
(Eiserne Regeln 10/11 — Freitext ist nie Steuerbefehl).
