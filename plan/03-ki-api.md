# 03 · KI / API (AI-Provider)

> Austauschbare Anbindung an Sprachmodelle (OpenAI, Gemini) über eine eng begrenzte, projektspezifische Tool-Schnittstelle. Die KI orchestriert und erklärt – sie regelt nicht.

**Status:** Entwurf · **info.md-Bezug:** §5, §12, §19, §24

---

## Ziel & Abgrenzung

- Einheitliches **AI Provider Interface** mit austauschbaren Anbietern.
- Die KI arbeitet **nur** über klar definierte Funktionen und strukturierte Daten.
- **Geeignet** für die KI: Ziele interpretieren, Zielkonflikte bewerten, Daten/Werkzeuge auswählen, Planvarianten vergleichen, Plan erstellen, begründen, fehlende Daten erkennen, lokale Optimierungsengine aufrufen, Simulationen interpretieren.
- **Nicht geeignet:** direkte Gerätesteuerung, sekundenschnelle Regelung, Umgehung technischer Grenzen, Ausführung freien Codes, Änderung von Sicherheitsparametern, unkontrollierter Entitätszugriff.

> Grundregel: **Freie Textausgaben dürfen niemals direkt als Steuerbefehl verwendet werden.**

---

## Verwendete Services / Technologie

**Version 1:**
- **OpenAI API** (GPT-Modelle) – Function Calling, Structured Outputs.
- **Google Gemini API** – Function Calling.

**Spätere Erweiterungen (info.md §5):**
- Lokale Modelle über **Ollama**
- **OpenAI-kompatible** APIs
- Weitere Cloud-Anbieter (z. B. **Anthropic Claude** – sehr gut für Tool-/Function-Calling geeignet)
- Vollständig **lokale Planungslogik** ohne externes Sprachmodell

Modul: **AI Provider Interface** mit Unteradaptern (`OpenAI Provider`, `Gemini Provider`, …).

---

## Provider-Interface (Vorschlag)

Gemeinsamer Vertrag, den jeder Adapter erfüllt:

```text
plan(context, tools, objectives) -> structured_plan_candidate
- context:    verdichtete Zustands-/Prognosedaten (kein Rohdaten-Dump)
- tools:      Liste erlaubter Funktionen (Function/Tool Calling)
- objectives: harte Grenzen + gewichtete weiche Ziele
returns:      validierbarer Kandidatenplan (JSON nach Schema → 07)
```

Pro Provider zu kapseln: Authentifizierung, Endpunkt, Modellname, Tool-/Schema-Format, Token-/Kosten-Schätzung, Fehler-/Timeout-Verhalten, Retry.

---

## Agent-Tools (Function Calling)

Beispielhafte Tools (info.md §5), die die KI aufrufen darf – jeder Aufruf wird von der App geprüft und ausgeführt:

```text
get_current_energy_state()      get_user_objectives()
get_recent_energy_history()     get_current_plan()
get_energy_forecast()           calculate_candidate_plan()
get_device_constraints()        simulate_candidate_plan()
                                validate_candidate_plan()
                                submit_energy_plan()
                                explain_energy_plan()
```

Die Tools sind die **einzige** Brücke der KI zur Anlage. Das Modell erhält keinen direkten Zugriff auf Geräte oder interne APIs.

---

## Datenfluss & Datenschutz (Kurzfassung, Details → [08](08-sicherheit.md))

- An externe KI gehen **nur die für die Planung notwendigen** Daten – keine Namen, keine unnötigen Entitäten.
- Historie wird vor Übertragung **verdichtet** (→ [04](04-prognosen.md)).
- **API-Schlüssel** nur in geschütztem Speicher, nie in Logs/Plänen/Entitäten.
- Jede Anfrage protokolliert: Anbieter, Modell, Zeitpunkt, geschätzter Verbrauch.
- **Tages-/Monatslimits** konfigurierbar; bei Erreichen → lokaler/passiver Modus.
- Der Nutzer kann einsehen, **welche Daten** übermittelt wurden.

---

## Möglichkeiten in der Oberfläche (KI-Konfiguration)

- Anbieter, Modell, API-Schlüssel
- Timeout, maximale API-Aufrufe, Kostenlimit
- Datenfreigabe (Umfang der an die KI gesendeten Daten)
- **Testverbindung**

---

## Offene Entscheidungen

- [ ] Standardmodelle je Anbieter (z. B. OpenAI: welches GPT-Modell; Gemini: welches Modell)
- [ ] SDK vs. direkte HTTP-Aufrufe je Anbieter
- [ ] Strukturierte Ausgabe: native Structured Outputs / JSON-Mode vs. Tool-Call mit Schema
- [ ] Soll die HA-eigene LLM-API genutzt werden? (info.md bevorzugt eigene, enge Tool-Schnittstelle)
- [ ] Verhalten bei Tool-Call-Fehlern / Halluzination eines ungültigen Plans
- [ ] Anthropic Claude bereits in v1 als dritter Adapter aufnehmen oder erst später?

---

## Aufgaben / Umsetzung

- [ ] Provider-Interface (abstrakte Basis) definieren
- [ ] OpenAI-Adapter (Function Calling + Structured Outputs)
- [ ] Gemini-Adapter (Function Calling)
- [ ] Tool-Registry mit Validierung jedes Aufrufs
- [ ] Kontext-Builder (verdichtete, minimierte Eingabedaten)
- [ ] API-Nutzungs-/Kostenzähler + Limit-Logik
- [ ] Testverbindungs-Funktion für die UI

---

## Bezug zu anderen Plänen

- Was die KI plant → [05 · Planungs-Engine](05-planungs-engine.md)
- Eingabedaten/Prognosen → [04 · Prognosen](04-prognosen.md)
- Schlüssel, Limits, Datenschutz → [08 · Sicherheit](08-sicherheit.md)
- Konfigurations-UI → [09 · Benutzeroberfläche](09-benutzeroberflaeche.md)
- Planformat → [07 · Datenmodell](07-datenmodell.md)
