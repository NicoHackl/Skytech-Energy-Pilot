# Entscheidungen (Decision Log)

Zentrale, dauerhafte Ablage aller **beantworteten** Design-Entscheidungen (aus [../claude-fragen/](../claude-fragen/) + [../user-fragen.md](../user-fragen.md)). Quelle der Wahrheit für „warum ist etwas so". Offene Fragen bleiben in `claude-fragen/claude-fragen-vN.md`; sobald beantwortet, wandern sie hierher.

Format: **ID · Thema · Entscheidung · Begründung/Detail · betroffene plan-Dateien.**

---

## D-001 · Sensorwerte: Live + interne Mittelung
**Entscheidung:** User übergibt **Live-Werte**; EP bildet selbst gleitende Mittel.
**Detail:** Fenster **1 / 15 / 60 min** parallel (D-003). Gemittelt: Leistungs-/Flussgrößen. Letztwert: SOC, Temperaturen, Zeiten, Zustände.
**Quelle:** user-fragen.md, A3. → [02](02-backend-architektur.md), [05](05-daten-und-speicherung.md)

## D-002 · HEMS-Anbindung: erst Helfer, später API
**Entscheidung:** V1 integriert **nur über HA-Helfer/Entitäten** (`/api/set`); danach zusätzlich ein **versionierter Plan-Endpunkt im SkytechHEMS-Repo**.
**Detail:** Ich darf später auch im **HEMS-Repo** ändern; der User richtet ein, dass lokal in beiden Repos parallel gearbeitet werden kann. Branch-Regel `claude/main` gilt sinngemäß auch dort (in v2 zu bestätigen).
**Quelle:** A1. → [03](03-api-schnittstelle-hems.md), [roadmap](roadmap.md) (M3)

## D-003 · Mittelungsfenster 1/15/60 min, keine Ereigniskopplung
**Entscheidung:** Drei feste Fenster **1, 15, 60 min**. Über die Mittelwerte erfolgt **keine** Ereigniserkennung/-kopplung.
**Detail:** Langzeitprognose greift nur auf die **60-min**-Verdichtung zu (D-012).
**Quelle:** A3, B6. → [02](02-backend-architektur.md), [05](05-daten-und-speicherung.md), [07](07-planning-engine.md)

## D-004 · Entitäten-Namensschema wie HEMS
**Entscheidung:** Naming analog HEMS; `<PREFIX>`/`<SUFFIX>` dürfen ineinander übergehen.
**Beispiele:** `sensor.ep_batterie_1_ziel_soc`, `sensor.ep_heizstab_freigabe`, `input_number.ep_speicher_soc_mindestwert_1`.
**Quelle:** A4. → [01](01-homeassistant-integration.md)

## D-005 · HA-Helfer per vorgefertigten YAML-Dateien
**Entscheidung:** EP legt Helfer **nicht** selbst an. Ich liefere fertige YAML-Pakete, die der User in die HA-Config je Domain einfügt.
**Detail:** Dateien heißen `<domain>_ep.yaml` und liegen in [../claude-ha-config-dateien/](../claude-ha-config-dateien/). Vorlage: [../user-beispiele/beispiel-config-yam.txt](../user-beispiele/beispiel-config-yam.txt) (input_number). Für jede benötigte Helfer-Domäne eine Datei.
**Quelle:** A5. → [01](01-homeassistant-integration.md)

## D-006 · Prognose/Preis als HA-Sensoren via Addon-Config
**Entscheidung:** PV-Prognose und Strompreis liefert der User über **bestehende HA-Sensoren**, deren Entitätsnamen in der **Addon-Config** hinterlegt werden (kein Namensschema, da Drittanbieter).
**Quelle:** A6. → [01](01-homeassistant-integration.md), [06](06-prognosen.md)

## D-007 · KI-Provider: Start Gemini (Free), Provider/Modell wechselbar
**Entscheidung:** Start mit **Google Gemini** (Gratis-Key, ~10 Anfragen/min). Provider + Modell **in der Addon-Config umschaltbar**, zukunftssicher (OpenAI usw.).
**Detail:** Rate-Limit (~10 req/min) respektieren: Aufruf-Drossel/Budget-Logik. API-Keys nur in Addon-Config, nie in Logs/Entitäten.
**Quelle:** A7. → [04](04-ki-provider.md)

## D-008 · V1: KI liefert nur Vorschlagswerte (keine Übernahme)
**Entscheidung:** In V1 erzeugt die KI bereits **Vorschlagswerte**, sichtbar in Addon-UI, HA-Sensoren und Logging. Werte werden **noch nicht** übernommen/ausgeführt.
**Quelle:** A2. → [07](07-planning-engine.md), [roadmap](roadmap.md) (M2)

## D-009 · Drei Steuermodi als Langzeitziel (user-regeln §04)
**Entscheidung:** Langfristig vollständige Umsetzung der drei **Steuermodi**: **Manuell** (nur User), **Hybrid** (User fixiert Werte → für KI **harte** Vorgaben, KI plant darum herum), **Automatisch** (KI-Werte haben Vorrang vor User-Eingaben).
**Detail:** Eigene Achse, getrennt von den Betriebsmodi (Beobachten/Vorschlagen/Shadow/Autopilot). Siehe [12](12-steuermodi.md).
**Quelle:** A2 + user-regeln.md §04. → [12](12-steuermodi.md), [07](07-planning-engine.md), [08](08-validierung-sicherheit.md)

## D-010 · UI: einfach/funktional starten, Framework später
**Entscheidung:** Start mit einfacher, funktionaler Technik (von mir gewählt: server-gerenderte SPA via aiohttp, vanilla JS/CSS wie HEMS), später optional Framework für schönere Oberfläche.
**Quelle:** B1. → [09](09-ui-ingress.md)

## D-011 · Zielgewichtung in Addon-Config, init aus info.md
**Entscheidung:** Weiche Zielgewichtungen sind in der **Addon-Config** pflegbar; initial mit den Werten aus info.md §7 vorbelegt.
**Quelle:** B2. → [07](07-planning-engine.md)

## D-012 · Datenhaltung von Anfang an für 1/15/60 min
**Entscheidung:** Speicherstruktur von Beginn an so, dass 1/15/60-min-Verdichtung passt. Langzeitprognose nutzt nur 60-min-Summierung.
**Detail (Default-Retention, empfohlen, später per Config erweiterbar):** raw ~6 h · 1-min-agg ~7 Tage · 15-min-agg ~90 Tage · 60-min-agg ~13 Monate · Pläne/Audit ~13 Monate.
**Quelle:** B4, B6. → [05](05-daten-und-speicherung.md)

## D-013 · Auth EP↔HEMS: pragmatisch + Vorbereitung externes Backend
**Entscheidung:** Für EP↔HEMS die für HA-Addons übliche/beste Variante (interner Supervisor-Proxy/Token, interner Hostname).
**WICHTIG (Hinterkopf):** User will aus dem internen Netz über ein **iOS-Backend (Java auf Linux-Server)** auf bestimmte Daten zugreifen bzw. Werte **setzen** (z.B. **Abfahrtszeit E-Auto** für Einhaltung der Mindestladung). Architektur so wählen, dass ein externer Schreibzugriff (vorzugsweise über HA-Helfer, ggf. später EP-API) sauber möglich ist.
**Quelle:** B5. → [03](03-api-schnittstelle-hems.md), CLAUDE.md

## D-014 · Auto-Export von Logs bei ERROR/CRITICAL
**Entscheidung:** Bei `ERROR`/`CRITICAL` automatisch ein KI-lesbares Log-Bundle erzeugen/benachrichtigen, sofern es die gemeinsame Fehlerbehandlung mit der KI erleichtert.
**Quelle:** B7. → [10](10-logging-observability.md)

## D-015 · CI testet HEMS↔EP-Zusammenspiel
**Entscheidung:** CI-Umfang nach Sinnhaftigkeit; **mindestens** das Zusammenspiel HEMS↔EP wird (gegen Mock-HEMS / Vertragstests) getestet.
**Quelle:** B8. → [11](11-tests-ci.md)

---

# Runde 2 (claude-fragen-v2)

## D-016 · Batteriespeicher (E3DC): immer Prio 1, kein SOC-Limit, keine Entladung
**Entscheidung:** Die Batterie wird **aktuell** immer mit **Priorität 1** behandelt und ist **immer freigegeben**. Daher **kein** min/max-SOC-Helfer und **kein** Freigabe-Schalter. **Entladeleistung** geht (aktuell) **nicht** in die Berechnung ein — EP regelt nur PV-**Überschuss**. Relevanter Grenzwert: nur **maximale Ladeleistung**.
**Detail:** Gerät ist ein E3DC-Speicher (`ep_batterie_ladeleistung_maximal`, ohne Index).
**Quelle:** A1 (YAML-Kommentare). → [01](01-homeassistant-integration.md), [07](07-planning-engine.md)

## D-017 · Heizlüfter 1 & 2: feste Leistung 1500 W
**Entscheidung:** Beide Heizlüfter haben **feste 1500 W** → **kein** `input_number` für Leistung. Es bleibt je ein **Freigabe**-Schalter (binäre Last, vgl. HEMS `BinaryDevice`).
**Quelle:** A1 (YAML-Kommentare). → [01](01-homeassistant-integration.md), [07](07-planning-engine.md)

## D-018 · Datenquellen: nur PV-Prognose (Multi-Sensor), Strompreis vorerst raus
**Entscheidung:** **Strompreis entfällt vorerst** (kein dynamischer Tarif beim User). **PV-Prognose:** je Typ **mehrere Sensoren** pflegbar (mehrere PV-Ausrichtungen → EP summiert). Erwartete Werte je Sensor: **Energie aktuelle Stunde, Energie nächste Stunde, Energie verbleibend heute, Energie morgen**.
**Quelle:** A2, A3. → [06](06-prognosen.md), [01](01-homeassistant-integration.md)

## D-019 · Gemini-Modell in Addon-Config wählbar
**Entscheidung:** Modellwahl in der Addon-Config änderbar (bestätigt). **Konkretes Default-Modell noch offen** (Antwort abgeschnitten) → v3.
**Quelle:** A4. → [04](04-ki-provider.md)

## D-020 · Steuermodus: global **und** pro Gerät
**Entscheidung:**
- Global = **Hybrid** → pro Gerät zusätzlich verfeinerbar (Gerät kann Manuell/Hybrid/Automatisch sein).
- Global = **Manuell** oder **Automatisch** → gilt für **alle** Geräte (kein Per-Gerät-Override, „alles oder nichts").
**Quelle:** A5. → [12](12-steuermodi.md)

## D-021 · Mindestkonfidenz & Delta-Limit: Defaults, aber konfigurierbar
**Entscheidung:** Vorerst meine Vorschlagswerte (Mindestkonfidenz **70 %**, Delta-Limit **±20 % Leistung / ±10 % SOC-Ziel** pro Planwechsel), **alles in der Addon-Config konfigurierbar**.
**Quelle:** B1. → [08](08-validierung-sicherheit.md)

## D-022 · HEMS-Repo: gleiche Branch-Regel
**Entscheidung:** Auch im SkytechHEMS-Repo **nur in `claude/main`** committen/pushen.
**Quelle:** B2. → [03](03-api-schnittstelle-hems.md)

## D-023 · Externes iOS/Java-Backend: Start mit HA Long-Lived Token
**Entscheidung:** Externer Zugriff beginnt über ein **HA Long-Lived Access Token** (Backend schreibt HA-Helfer). Eigener authentifizierter EP-Endpunkt evtl. später.
**Quelle:** B3. → [03](03-api-schnittstelle-hems.md)

## D-024 · CI: Coverage-Start 60 %, Tests nur auf `claude/main`
**Entscheidung:** Coverage-Qualitätsgate startet bei **60 %** (später anheben). Automatische CI-Tests bei commit/push laufen **nur**, wenn auf **`claude/main`** gepusht wird.
**Quelle:** B4. → [11](11-tests-ci.md)

---

# Runde 3 (claude-fragen-v3)

## D-025 · Default-KI-Modell: Gemini 3.5 Flash
**Entscheidung:** Default-Modell **`gemini-3.5-flash`** (vom User vorgeschlagen; per Websuche bestätigt: existiert seit Google I/O Mai 2026). In der Addon-Config änderbar (D-019).
**Detail:** Free-Tier-Rate-Limit (~10 req/min) weiterhin via Drossel beachten (D-007). Exakte Modell-ID bei Implementierung gegen die aktuelle Gemini-API gegenprüfen.
**Quelle:** v3-A1. → [04](04-ki-provider.md)

## D-026 · PV-Prognose-Werte liegen im State, nicht als Attribut
**Entscheidung:** Die vier PV-Werte (Energie aktuelle Stunde / nächste Stunde / verbleibend heute / morgen) liegen jeweils **direkt im State** eigener Sensoren — **nicht** als Attribut. EP liest also je Wert eine eigene Sensor-Entität (mehrere pro Ausrichtung, EP summiert, D-018).
**Quelle:** v3-A2. → [06](06-prognosen.md)

---

## D-027 · Sensor-Zuordnung in der Addon-Konfiguration (nicht in der UI)
**Entscheidung:** Die Zuordnung der Mess-/Zustandsgrößen zu HA-Entitäten wird in der **Addon-Konfiguration** gepflegt (gleiche Seite wie das KI-Modell), über Optionen `entity_<rolle>` und `fallback_<rolle>`. Die Addon-Oberfläche zeigt die Zuordnung nur noch **lesend** an.
**Detail:** Vorteil — Änderung der Optionen startet das Addon neu, die Zuordnung wird beim Start sofort geladen, der Poller erfasst sofort. Behebt zugleich das Problem, dass über die UI gepflegte Werte nicht erschienen. `entity_map`-Tabelle bleibt für spätere Zwecke erhalten. Datenansicht aktualisiert sich automatisch (alle 10 s).
**Quelle:** User-Feedback M1 (16.06.2026). → [01](01-homeassistant-integration.md), [02](02-backend-architektur.md)

## Noch offen (geparkt, siehe claude-fragen-v4)
- **B1** Hybrid-Modus: fixierbare Felder pro Gerät — vom User als „zu früh" geparkt (relevant ab M3).
- **B2** Plan-JSON-Schema gemeinsam mit HEMS — Vormerkung für Ebene 2 (M3).
