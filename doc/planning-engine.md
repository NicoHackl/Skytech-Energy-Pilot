# Planungs-Engine

## Ablauf eines Planungslaufs (`planner.py: Planner.run()`)

Ausgelöst **nur manuell** über `POST /api/plan/run` (siehe
[known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md#kein-automatischer-scheduler)):

1. Snapshot aller Collector (Mess-Rollen, Geräte, Prognose, Wetter).
2. `build_constraints()` — harte Grenzen je Gerät ([devices.md](devices.md)).
3. **Klassifizierungs-Aufruf (D-055):** `load_ziele()` — user-definierte Ziele
   (Tab "Grenzen und Ziele", ohne Gewicht). Gibt es welche, baut
   `build_classification_context()` dieselbe Datenbasis wie der Plan-Aufruf (nur `objectives`
   durch `ziele` ersetzt), `build_classification_prompt()`/`build_classification_response_schema()`
   den Aufruf, `provider.generate()` liefert je Ziel-`id` ein Gewicht 0–100 %,
   `objectives_from_classification()` baut daraus die `Objective`-Liste. Scheitert dieser
   Aufruf, gilt der **gesamte** Planungslauf als gescheitert (`error="classification_error"`,
   kein stiller Fallback). Ohne konfigurierte Ziele entfällt der Aufruf ersatzlos
   (`objectives = []`).
4. `build_context()` (`plan_context.py`) — komprimierter KI-Kontext (Datenminimum, Eiserne Regel 7),
   inkl. der oben abgeleiteten `objectives`.
5. `build_prompt()` — DB-gespeicherter Custom-Prompt (falls gesetzt) oder `DEFAULT_PLANNING_PROMPT`, **immer** ergänzt um einen code-generierten `Daten:`-JSON-Block (der Prompt kann die Datenübergabe nicht umgehen).
6. `build_response_schema()` — Gemini-Response-Schema.
7. `provider.generate()` — KI-Aufruf, ratenlimitiert.
8. `CandidatePlan` zusammenbauen — **EP selbst** setzt `plan_id` (`uuid4().hex[:12]`), `valid_from`, `valid_until` (= `now + planning_interval_min`); das Modell liefert nur Geräte-Vorschläge, `confidence`, `reasoning`, `warnings`.
9. **Reparatur-Pass:** fehlen Pflichtfelder (`missing_suggestion_fields()`) und `ai_repair_missing` ist aktiv → ein gezielter Nachforder-Aufruf mit `build_repair_prompt()`; der reparierte Plan wird nur übernommen, wenn er die Lückenzahl **strikt** verringert.
10. `validate()` — siehe [validation-safety.md](validation-safety.md).
11. Speichern in Tabelle `plans` + Audit-Log (`plan_created`/`plan_rejected`).
12. Bei gültigem Plan **und** `publish_suggestions: true` → `suggestion_publisher.publish_suggestions()`.

Token-Zähler (`ai_call.tokens_in/out`) summieren Klassifizierungs- **und** Plan-Aufruf
(`_sum_tokens()`); beide Aufrufe werden einzeln in `ai_calls` protokolliert.

Der Planner fängt **alle** Provider-Exceptions ab und wirft nie an den Aufrufer weiter;
DB-Schreibfehler sind mit `except sqlite3.Error: pass` abgesichert — ein Planungslauf
blockiert die Anlage nie (Eiserne Regel 8).

## KI-Provider-Abstraktion (`ai_provider.py`)

- Abstrakte Basisklasse `AIProvider.generate(prompt, response_schema)`.
- `AsyncRateLimiter` — gleitendes 60-s-Fenster, **wartet** statt zu fehlern
  ("Wartedrossel statt Fehlerflut") — kein Request wird verworfen, nur verzögert.
- `ProviderError`/`RateLimitError`-Exception-Hierarchie.

## Gemini-Provider (`gemini_provider.py`)

- Direkter REST-Client (kein SDK) gegen
  `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`.
- API-Key im **Header** `x-goog-api-key` (nie in der URL — landet dadurch nie in
  Proxy-/Zugriffs-Logs).
- `generationConfig`: `responseMimeType: application/json`, `responseSchema`,
  optional `temperature`/`seed` (siehe Determinismus unten).
- HTTP 429 → `RateLimitError`; andere ≥400 → `ProviderError` mit server-extrahierter
  Nachricht (`http_errors.read_error_body`).
- **Timeout-Falle:** aiohttps Total-Timeout wirft `asyncio.TimeoutError` = Pythons
  eingebautes `TimeoutError` seit 3.11 — das ist **kein** `aiohttp.ClientError` und
  `str(TimeoutError())` ist leer. Deshalb ein eigener `except TimeoutError`-Zweig mit
  synthetisierter Fehlermeldung (`gemini_provider.py:103-109`). Derselbe Trick taucht
  in `onecall_client.py`/`weather_client.py` auf — bei neuen HTTP-Clients dran denken.
- Default-Modell: `gemini-2.5-flash` — siehe [known-gaps-and-pitfalls.md](known-gaps-and-pitfalls.md#gemini-35-flash-hang)
  für die Begründung, `gemini-3.5-flash` **nicht** als Default zu verwenden.
- `provider`-Config erlaubt Schema-seitig `gemini|openai`, aber es existiert **kein**
  `openai_provider.py` — `main.py` baut bei `provider: openai` schlicht keinen
  Provider (fällt auf die "KI-Provider nicht konfiguriert"-Warnung zurück).

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
   `generationConfig` — nur gesetzt, wenn konfiguriert, sonst Provider-Default.
3. **Reparatur-Pass:** gezielter Ein-Versuch-Nachforder-Aufruf mit exakter Liste der
   fehlenden Felder (`ai_repair_missing`, Default an).
4. **Deterministische Auffüllung im Validator** (`_fill_missing_fields()`) als letzte
   Instanz — jedes fehlende Pflichtfeld wird aus dem aktuellen Ist-Zustand ergänzt
   (z. B. `freigabe` ← aktuelle technische Freigabe, Schutzleistung ← technisches
   Minimum oder 0, Extra-Feld ← aktueller Lesewert/Typ-Default), jede Auffüllung wird
   wie eine Klemmung geloggt.

## Kontextaufbau & Datenminimum (`plan_context.py`)

`_condense_state/_forecast/_weather/_constraint` kürzen Snapshots auf das Nötige
(Eiserne Regel 7). Wetter-Kondensierung verzweigt nach Quelle:

- **OneCall:** `_hourly_window_slots` (heute, ab jetzt, frühestens 6 Uhr, bis 21 Uhr
  Ortszeit) + `_daily_next_days_slots` (nächste 5 Tage ab morgen).
- **forecast3h `compact`:** 3-h-Schritte bis `forecast_horizon_h`.
- **forecast3h `full`:** komplette 5-Tage-Prognose.

Der Planungs-Prompt (`DEFAULT_PLANNING_PROMPT`) ist über die UI editierbar (Plan-Tab)
und in der DB persistiert (`config`-Tabelle, Key `PLANNING_PROMPT_KEY`) — überlebt
Neustarts **und** Addon-Updates ohne Git-Push. Der `Daten:`-Block wird davon
unabhängig immer code-seitig angehängt; das Response-Schema bleibt vollständig
code-kontrolliert; der Validator erzwingt harte Grenzen unabhängig vom Prompt-Inhalt
(Eiserne Regeln 5/6 — Freitext ist nie Steuerbefehl).
