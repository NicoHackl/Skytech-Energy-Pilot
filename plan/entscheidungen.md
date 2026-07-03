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
**⚠️ Präzisiert durch D-029/D-030:** Domäne nach Datenrichtung (`ems_*` lesen / `ep_*` schreiben); obige Beispiele sind als EP-Output **überholt** (gültige Beispiele dort).
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

## D-025 · Default-KI-Modell: Gemini 2.5 Flash (korrigiert)
**Entscheidung:** Default-Modell **`gemini-2.5-flash`**. In der Addon-Config änderbar (D-019).
**Detail:** Free-Tier-Rate-Limit (~10 req/min) weiterhin via Drossel beachten (D-007).
**Korrektur (2026-07-03):** Ursprünglich war `gemini-3.5-flash` als Default gesetzt (vom User
vorgeschlagen, per Websuche als „ab Google I/O Mai 2026 existent" angenommen). In der Praxis
lieferte diese Modell-ID keinen brauchbaren Lauf: der Aufruf hing „ewig" und wurde vom
HA-Ingress mit einer HTML-Fehlerseite abgebrochen (im Frontend als `SyntaxError: Unexpected
token '<'`). Mit `gemini-2.5-flash` funktioniert die Planung zuverlässig (vom User verifiziert).
Da die reale Nutzung Vorrang vor der (KI-)Doku hat, ist der Default auf die nachweislich
funktionierende ID umgestellt; wer `gemini-3.5-flash` testen will, kann es in der Addon-Config
setzen (Timeout-Obergrenze dafür auf 600 s angehoben).
**Quelle:** v3-A1 + Praxisbefund 2026-07-03. → [04](04-ki-provider.md)

## D-026 · PV-Prognose-Werte liegen im State, nicht als Attribut
**Entscheidung:** Die vier PV-Werte (Energie aktuelle Stunde / nächste Stunde / verbleibend heute / morgen) liegen jeweils **direkt im State** eigener Sensoren — **nicht** als Attribut. EP liest also je Wert eine eigene Sensor-Entität (mehrere pro Ausrichtung, EP summiert, D-018).
**Quelle:** v3-A2. → [06](06-prognosen.md)

---

## D-027 · Sensor-Zuordnung in der Addon-Konfiguration (nicht in der UI)
**Entscheidung:** Die Zuordnung der Mess-/Zustandsgrößen zu HA-Entitäten wird in der **Addon-Konfiguration** gepflegt (gleiche Seite wie das KI-Modell), über Optionen `entity_<rolle>` und `fallback_<rolle>`. Die Addon-Oberfläche zeigt die Zuordnung nur noch **lesend** an.
**Detail:** Vorteil — Änderung der Optionen startet das Addon neu, die Zuordnung wird beim Start sofort geladen, der Poller erfasst sofort. Behebt zugleich das Problem, dass über die UI gepflegte Werte nicht erschienen. `entity_map`-Tabelle bleibt für spätere Zwecke erhalten. Datenansicht aktualisiert sich automatisch (alle 10 s).
**Quelle:** User-Feedback M1 (16.06.2026). → [01](01-homeassistant-integration.md), [02](02-backend-architektur.md)

## D-028 · Build auf direktem Python-Basis-Image (kein HA-Basis-Image/s6)
**Entscheidung:** Dockerfile baut auf `python:3.11-slim` mit direktem `CMD ["python3","main.py"]` (wie Skytech HEMS), **ohne** `build.yaml`/HA-Basis-Image und **ohne** `run.sh`.
**Begründung:** Das HA-Basis-Image nutzt s6-overlay; dabei wurde `SUPERVISOR_TOKEN` nicht an den App-Prozess durchgereicht → `ha_configured=false`, keine Datenerfassung. Direkter Python-Start erbt die Container-Umgebung samt Token (verifiziert). Manifest auf das HEMS-Minimum reduziert (`homeassistant_api: true`; `hassio_api`/`auth_api`/`map` entfernt).
**Quelle:** M1-Debugging 16.06.2026 (Statusseite zeigte ha_configured=false). → Dockerfile, config.yaml

---

# Runde 4 (claude-fragen-v5) — Datenfluss/Variablenzugriff HEMS↔EP

> Quelle: [../user-beispiele/variablen-zugriff.txt](../user-beispiele/variablen-zugriff.txt) + strukturierte [../user-beispiele/variablen-zugriff.md](../user-beispiele/variablen-zugriff.md).

## D-029 · Namens-Domäne nach Datenrichtung: `ems_*` vs. `ep_*`
**Entscheidung:** Vom **User gepflegte technische Gerätewerte** (Grenzwerte, Freigaben, Ist-Leistung) liegen ausschließlich in der **HEMS-Domäne `ems_*`**; EP **liest** sie nur. **EP-Vorschlagswerte** liegen in der **EP-Domäne `ep_*`**; EP **schreibt** sie. Suffix der Vorschläge bleibt `…_vorschlag`.
**Detail:** Read-Schema (EP liest): Binär `ems_<name>_leistung_w`, `ems_<name>_technische_freigabe`; Regelbar `ems_<name>_technische_freigabe`, `ems_<name>_min_technisch_w`/`_a`, `ems_<name>_max_technisch_w`/`_a`. `technische_freigabe` = ob das Gerät aktuell überhaupt arbeiten kann.
**Folge:** Die bisher als `ep_*` ausgelieferten **Geräte-Grenzwerte/Freigaben** ([../claude-ha-config-dateien/](../claude-ha-config-dateien/)) gehören in `ems_*` (HEMS). EP-eigene Schalter/Planungsparameter bleiben `ep_*`. Ersetzt das frühere „HEMS-Pendant `ems_*` nur zum Vergleich".
**Quelle:** v5-A2. → [01](01-homeassistant-integration.md), [03](03-api-schnittstelle-hems.md), CLAUDE.md

## D-030 · EP-Schreibvertrag (Phase 1) = Priorität + geschützte Mindestleistung + Freigabe
**Entscheidung:** EP schreibt in Phase 1 **ausschließlich** diese Vorschläge: `ep_<name>_prio_vorschlag`, `ep_<name>_geschutzte_mindestleistung_w_vorschlag` / `_a_vorschlag` (regelbar) und `ep_<name>_freigabe_vorschlag` (binär).
**Detail:** Frühere Beispiele (`ep_batterie_1_ziel_soc`, max. Ladeleistung als Vorschlag o. ä.) sind als EP-Output **überholt**. Erweiterungen des Schreibvertrags kündigt der User über [../user-beispiele/](../user-beispiele/) an.
**Quelle:** v5-A3. → [01](01-homeassistant-integration.md), [07](07-planning-engine.md)

## D-031 · Jeder Binärverbraucher hat `ems_<name>_leistung_w` (Ist-Leistung)
**Entscheidung:** Die (Ist-)Leistung **jedes** Binärgeräts wird unter `input_number.ems_<name>_leistung_w` gepflegt; EP liest daraus die **Lastgröße** für die Energieplanung.
**Detail:** **Präzisiert D-017/D-018**: „feste 1500 W → kein Leistungs-Helfer" galt nur für EP-eigene `ep_*`-Helfer. Die Lastgröße existiert sehr wohl — als `ems_*`-Wert (HEMS-Domäne), nicht als EP-Helfer.
**Quelle:** v5-A4. → [01](01-homeassistant-integration.md), [07](07-planning-engine.md)

## D-032 · Schreibweg gestaffelt: erst HA-Helfer, später zusätzlich 1:1 HEMS-Endpunkte
**Entscheidung:** V1 schreibt EP die `ep_*`-Vorschläge **nur** in HA-Helfer/-Entitäten. **Später** zusätzlich **1:1** über HTTP-API direkt in interne HEMS-Variablen — **gleiche Werte, gleich viele Endpunkte wie HA-Helfer**.
**Detail:** Bestätigt/präzisiert D-002 (die `.txt` beschreibt den späteren Sollzustand, nicht V1).
**Quelle:** v5-A5. → [03](03-api-schnittstelle-hems.md), [roadmap](roadmap.md) (M3)

## D-033 · V1-Nutzung der Vorschläge: HA-Entitäten, User verdrahtet selbst; HEMS-Auswertung später
**Entscheidung:** Aktuell zählt nur, dass die Vorschläge in `ep_<name>_…_vorschlag`-Entitäten geschrieben werden. Der User verdrahtet sie **vorerst selbst** testweise in HA-Automationen. **Später** dienen die HA-Entitäten nur der **Übersicht/Dashboards**; die eigentliche **Auswertung passiert im HEMS**, sobald die Vorschläge per API direkt in HEMS-Variablen geschrieben werden.
**Detail:** Die Frage „wann wirken die Vorschläge / Abhängigkeit vom Steuermodus" ist damit für jetzt **zurückgestellt** (kommt mit der HEMS-Auswertung/M3).
**Quelle:** v5-A6. → [03](03-api-schnittstelle-hems.md), [12](12-steuermodi.md)

---

# Runde 5 (claude-fragen-v6) — Schreibvertrag/Gerätehelfer, mit HEMS-Quellenabgleich

> Erstmals gegen den **lokal vorliegenden HEMS-Quellcode** ([../../SkytechHEMS/](../../SkytechHEMS/)) verifiziert.

## D-034 · Regelbarer Verbraucher: Schreibvertrag = Priorität + Freigabe + geschützte Mindestleistung
**Entscheidung:** Regelbare Verbraucher erhalten — **wie binäre** — zusätzlich ein `ep_<name>_freigabe_vorschlag`. EP schreibt für regelbar somit: `ep_<name>_prio_vorschlag`, `ep_<name>_freigabe_vorschlag`, `ep_<name>_geschutzte_mindestleistung_w_vorschlag`/`_a_vorschlag`.
**Detail:** Die doppelte `prio_vorschlag`-Zeile in der `.txt` (Z.44/45) war ein Tippfehler; der User hat sie auf `freigabe_vorschlag` korrigiert. **Präzisiert D-030**: `freigabe_vorschlag` gilt jetzt für **binär und regelbar**.
**HEMS-Abgleich:** `_ctrl_items_controllable` (app/main.py) führt `ems_{p}_freigabe`, `ems_{p}_prioritat`, `ems_{p}_geschutzte_mindestleistung_{w|a}` — alle drei EP-Vorschläge haben ein HEMS-Pendant.
**Quelle:** v6-A1. → [01](01-homeassistant-integration.md), [03](03-api-schnittstelle-hems.md), [../user-beispiele/variablen-zugriff.md](../user-beispiele/variablen-zugriff.md)

## D-035 · Heizstab max. Wassertemperatur: zwei EP-eigene Entitäten (`ep_*`), nicht HEMS
**Entscheidung:** Die max. Wassertemperatur ist **nicht HEMS-relevant** und wird vom HEMS nicht gestellt. Stattdessen (aktuell) zwei **EP-Entitäten**:
- `input_number.ep_heizstab_max_temperatur` → harter **Grenzwert für EP**, den **EP nur liest**. **Helfer**, weil ihn der **User/externes Backend pflegt** (vom mir als `input_number` geliefert).
- `sensor.ep_heizstab_max_temperatur_vorschlag` → **EP schreibt** (Vorschlag für die max. Heizstabtemperatur). **EP-eigene `sensor.`-Entität** (kein Helfer), konsistent mit D-030 (alle `ep_*_vorschlag` = Sensoren).
**Detail:** Ein `ep_*`-Wert, den **EP liest** → **präzisiert D-029**: „`ep_*` = EP schreibt" gilt nicht ausnahmslos; die EP-Domäne kann auch user-/extern-gepflegte Grenzwerte enthalten, die EP liest (gleiches Muster wie die spätere `input_datetime.ep_eauto_abfahrtszeit`, D-013). Zugleich **gerätespezifische Erweiterung von D-030** (nur Heizstab). **HEMS-Abgleich:** kein Temperatur-Entity im HEMS — bestätigt.
**Quelle:** v6-A2. → [01](01-homeassistant-integration.md), [07](07-planning-engine.md), [../claude-ha-config-dateien/](../claude-ha-config-dateien/)

## D-036 · `ems_*`-Gerätehelfer sind HEMS-definiert; kein EP-Template, Discovery via `/api/device_controls_schema`
**Entscheidung:** Alle `<domain>.ems_*`-Helfer sind **im HEMS definiert**; EP legt dafür **kein eigenes Schema/Template** an.
**Detail:** HEMS erzeugt die `ems_*`-Entitäten **dynamisch pro konfiguriertem Gerät** aus `entity_prefix` + `class` (controllable/binary) + `output_unit` (watt/ampere) — sie sind **nicht statisch** (app/main.py `_ctrl_items_controllable`/`_ctrl_items_binary`). EP ermittelt die konkreten Entity-IDs daher zur Laufzeit über **`GET /api/device_controls_schema`**, statt sie zu raten. Bestätigt das Entfernen der `ep_*`-Gerätehelfer (D-029); in den `<domain>_ep.yaml` bleiben die `ems_*`-Werte nur als **Lese-Dokumentation**.
**Quelle:** v6-A3 (+ HEMS-Quellenabgleich [../../SkytechHEMS/app/main.py](../../SkytechHEMS/app/main.py)). → [01](01-homeassistant-integration.md), [03](03-api-schnittstelle-hems.md)

## D-037 · Batterie: einziger EP-Vorschlag = `geschutzte_mindestleistung_w_vorschlag`
**Entscheidung:** Für die Batterie schreibt EP **nur** `ep_batterie_geschutzte_mindestleistung_w_vorschlag` (reservierte Mindest-Ladeleistung). **Kein** `prio_vorschlag`/`freigabe_vorschlag` (immer Prio 1, immer freigegeben, D-016).
**Detail:** Mappt 1:1 auf HEMS `ems_batterie_geschutzte_mindestleistung_w` (Batterie = `controllable`; HEMS kennt nur die Klassen controllable/binary, keine eigene Batterieklasse).
**Quelle:** v6-A4. → [01](01-homeassistant-integration.md), [07](07-planning-engine.md)

## D-038 · Entity Allowlist: zentrales Register, **soft** durchgesetzt (Verstöße auditiert, nie blockiert)
**Entscheidung:** EP führt ein zentrales Register der freigegebenen Lese-Entitäten (info.md §6.1/§13). Es leitet sich **vollständig aus den drei bestehenden Config-Quellen** ab (Messgrößen-Rollen, Geräte-`ems_*`-Felder, PV-Prognosesensoren) — **keine** separate manuelle Allowlist-Pflege, keine Doppelpflege. Durchsetzung ist **soft**: ein Read auf eine nicht freigegebene Entität wird **protokolliert und auditiert** (`audit.action='allowlist_violation'`), aber **nicht blockiert**.
**Detail:** Da Entity-IDs ohnehin nur aus der Config stammen, ist die Allowlist Defense-in-Depth + Transparenzregister. Soft statt hart, weil eine Fehlkonfiguration der Allowlist den lokalen Anlagenbetrieb **nie** stören darf (Leitprinzip „Fallback blockiert nie"). Umsetzung: Modul `allowlist.py` (`EntityAllowlist`, `collect_entity_ids`), weicher Guard in `HAClient.get_state`, Persistenz in DB-Tabelle `allowlist` (Migration v3) + Audit beim Rebuild, Transparenz unter `GET /api/allowlist` und im Status-Tab. Geräte-IDs kommen nach der HEMS-Discovery hinzu (`rediscover_devices`); beim Start additiv, beim manuellen HEMS-Sync/Auto-Retry über `rebuild` (D-046) neu aufgebaut, dann persistiert. Doppel-Audits je Entität werden gedrosselt (kein Log-Spam pro Poll-Zyklus).
**Quelle:** Umsetzung „letzter M1-Baustein" (roadmap); Durchsetzungsgrad vom User auf **soft** festgelegt. → [01](01-homeassistant-integration.md), [08](08-validierung-sicherheit.md), [roadmap](roadmap.md) (M1)

## D-039 · Plan-Validierung: Struktur via `jsonschema`-Bibliothek, fachliche Grenzen im Validator
**Entscheidung:** Die **strukturelle** Plan-Prüfung (Form, Typen, `schema_version`) läuft über die `jsonschema`-Bibliothek gegen ein versioniertes `PLAN_JSON_SCHEMA`; die **fachliche** Prüfung gegen die harten Grenzen (Schreibvertrag je Gerät, Freigabe, Leistungs-/Temperaturgrenzen) macht der lokale Validator. Saubere Trennung Struktur ↔ Semantik statt eines handgerollten Schema-Prüfers.
**Detail:** Implementierungsentscheidung (M2-Basis). Module `plan_schema.py` (`PLAN_JSON_SCHEMA`, `SCHEMA_VERSION="1.0"`, `schema_errors`, `suggestion_keys`) und `validator.py` (`validate` → `ValidationResult`). `_w`/`_a`-Suffix wird je Gerät aus `output_unit` gewählt (deckt sich mit der noch zu bestätigenden v6-B1; EP-internes Schema, finale HEMS-Vertragsbestätigung bleibt B1/B4). Neue Laufzeit-Abhängigkeit `jsonschema` in `app/requirements.txt`.
**Quelle:** Umsetzung M2-Schritt „deterministische Basis". → [08](08-validierung-sicherheit.md), [07](07-planning-engine.md)

## D-040 · M2-Start = deterministische Basis; Validator-Stufen 1–3 jetzt, 4–6 später
**Entscheidung:** M2 beginnt mit der KI-freien, vollständig testbaren Basis (Constraint-Model, Objective-Manager, Plan-Schema, Validator) **vor** der Gemini-Anbindung — das Sicherheits-Gate existiert, bevor eine KI Pläne erzeugt (eiserne Regel 6). Der Validator implementiert die jetzt möglichen Pipeline-Stufen aus [08](08-validierung-sicherheit.md): **1 Schema, 2 harte Grenzen (klemmen/ablehnen), 3 Zeitlogik**.
**Detail:** **Bewusst verschoben** (Eingaben fehlen noch): Stufe 4 Datenaktualität, Stufe 5 Delta-Limit (braucht Vorplan), Stufe 6 Mindestkonfidenz (braucht KI-Konfidenz; `min_confidence_percent` liegt bereits in der Addon-Config). Module: `constraints.py`, `objectives.py`, `plan_schema.py`, `validator.py`; Transparenz unter `GET /api/constraints`, `/api/objectives`, `/api/plan/schema` + Tab „Grenzen & Ziele". Zielgewichte aus info.md §7 in Addon-Config (`objective_weights`, D-011).
**Quelle:** Umsetzung M2-Schritt „deterministische Basis" (roadmap M2, Punkte 1 & 4). → [roadmap](roadmap.md) (M2), [07](07-planning-engine.md), [08](08-validierung-sicherheit.md)

## D-041 · KI-Provider Gemini via REST/aiohttp; Single-Shot + `responseSchema`; EP besitzt Plan-Metadaten
**Entscheidung:** Die M2-Planung läuft über ein austauschbares `AIProvider`-Interface (`generate(prompt, response_schema) -> ProviderResponse`). Erster Provider ist **Gemini über die REST-API per aiohttp** (kein SDK, Muster wie `hems_client.py`). Die KI wird **einmal je Lauf** (Single-Shot) mit einem **verdichteten, freigegebenen** Kontext (Datenminimum, eiserne Regel 7) aufgerufen und liefert **strukturiertes JSON** (`generationConfig.responseSchema`). Die **Plan-Metadaten** (`plan_id`, `valid_from`, `valid_until`, `provider`, `model`) setzt **EP selbst** — nie das Modell; das Modell liefert nur Geräte-Vorschläge, `confidence`, `reasoning`, `warnings`. Danach prüft der lokale `validator.py` (D-040), bevor etwas sichtbar/persistiert wird.
**Detail:** Module `ai_provider.py` (Basis + `AsyncRateLimiter`: Wartedrossel statt Fehlerflut, Default 10/min), `gemini_provider.py` (`GeminiProvider`; Schlüssel per Header `x-goog-api-key`, nie in URL/Log), `plan_context.py` (`build_context`/`build_prompt`/`build_response_schema` — Gemini-OpenAPI-Subset, **nicht** das `PLAN_JSON_SCHEMA` mit `const`/`additionalProperties`), `planner.py` (`Planner.run` → Validierung → DB). Gültigkeitsfenster `valid_until = jetzt + planning_interval_min`. Neue Config-Schlüssel `api_key` (Schema `password`, autom. maskiert über `SECRET_KEYS`), `ai_request_timeout_s`, `ai_rate_limit_per_min`. Persistenz: `ai_calls` (Tokens/Kosten), neue Tabelle `plans` (Migration v4), `audit` (`plan_created`/`plan_rejected`). Endpunkte `POST /api/plan/run`, `GET /api/plan`, `GET /api/ai/test`; Plan-Tab inkl. Transparenz „an KI gesendete Daten". **Bewusst V1:** nur Vorschlagswerte, **kein** Schreiben nach HA, **kein** Scheduler; agentischer Tool-Loop (info.md §5) + OpenAI-Provider später nachrüstbar (Abstraktion vorhanden). Exakte Gemini-Modell-ID bleibt config-getrieben (Default `gemini-2.5-flash`, korrigiert von `gemini-3.5-flash`, D-025).
**Quelle:** Umsetzung M2-Schritt „KI-Provider + Planning-Engine" (roadmap M2, Punkte 2 & 3); Ausrichtung per User-Entscheidung (Umfang „Plan erzeugen + anzeigen", REST/aiohttp, Single-Shot). → [04](04-ki-provider.md), [07](07-planning-engine.md), [08](08-validierung-sicherheit.md), [roadmap](roadmap.md) (M2)

## D-042 · Wettervorhersage direkt im EP über OpenWeatherMap; Koordinaten aus HA-Zone
**Entscheidung:** Die Wettervorhersage wird **direkt im EP** über die OpenWeatherMap-„5 day / 3 hour forecast"-API abgerufen (eigene externe Quelle, **nicht** über HA-Sensoren wie die PV-Prognose D-006). Damit korrigiert diese Entscheidung die frühere Annahme „Wetter in V1 nicht benötigt" ([06](06-prognosen.md)) auf User-Vorgabe. Längen-/Breitengrad kommen aus einer **HA-Zone** (`zone.*`, Attribute `latitude`/`longitude`); der API-Schlüssel und alle Parameter (`units`, `lang`, `refresh_min`) werden in der Addon-Config-Gruppe `weather` gepflegt. Der Schlüssel geht als Query-Param `appid` (OWM kennt keine Header-Auth) und wird **nie geloggt** (Iron Rule 6 — URL wird nie mit Schlüssel protokolliert).
**Detail:** Module `weather.py` (Config-Parsing + Dataclasses `WeatherConfig`/`WeatherForecast`/`WeatherSlot`), `weather_client.py` (`OpenWeatherClient` via aiohttp, Muster wie `gemini_provider.py`; Normalisierung auf energierelevante Felder: temp/feels_like/clouds/pop/wind_speed/humidity/rain_3h/snow_3h/condition), `weather_collector.py` (`WeatherCollector` löst die Zone auf, drosselt OWM-Aufrufe selbst auf `refresh_min`, Default 30 min). Die Zone wird als Lese-Entität in die Soft-Allowlist aufgenommen (D-038). Endpunkt `GET /api/weather`, Wetter-Block im Prognose-Tab, Diagnose um `weather_*` ergänzt. **Bewusst V1:** Daten **nur EP-intern** (UI/API) — **noch nicht** als HA-Sensor und **nicht** über die HEMS-API; ohne API-Schlüssel bleibt der Abruf inaktiv (Iron Rule 8). **Offen:** Einspeisung in den KI-Planungskontext (`plan_context.py`) und Detail-Defaults → claude-fragen-v8 (W1–W6).
**Quelle:** User-Vorgabe (OpenWeatherMap direkt im EP, Zone für Koordinaten, Schlüssel in HA-App-Config, vorerst nur EP-intern). → [06](06-prognosen.md)

## D-043 · Wetter im KI-Planungskontext (Detailgrad config-umschaltbar) + editierbarer Planungs-Prompt
**Entscheidung:** (1) Die Wetterprognose fließt jetzt in den KI-Kontext ein (beantwortet **W1**). Der **Detailgrad ist in der Addon-Config umschaltbar** (`weather.llm_detail`): `compact` (Default) = je 3-Stunden-Schritt nur Temperatur/Bewölkung/Niederschlagswahrscheinlichkeit, gekürzt auf `forecast_horizon_h` (Datenminimum, Iron Rule 7); `full` = komplette 5-Tage-Prognose mit allen Feldern. (2) Der **Planungs-Prompt ist in der EP-Oberfläche editierbar** (Plan-Tab), persistiert in der bestehenden `config`-KV-Tabelle → übersteht Neustart **und** Add-on-Update, kein Git-Push nötig. Der `Daten:`-Block wird immer code-seitig angehängt, das Antwort-Schema bleibt code-kontrolliert und der Validator erzwingt die harten Grenzen unabhängig vom Prompt (Iron Rules 5/6).
**Detail:** `plan_context.py`: `_condense_weather(weather, *, horizon_h, detail)`, `build_context(..., weather, horizon_h, weather_detail)`, Instruktion als Konstante `DEFAULT_PLANNING_PROMPT`, `build_prompt(context, template=None)` (Template oder Default + immer Datenblock). Neues Modul `settings.py` (KV über `config`-Tabelle, `PLANNING_PROMPT_KEY`). `planner.py` liest `weather_collector`-Snapshot + Custom-Prompt. Endpunkte `GET/POST /api/prompt` (leer ⇒ Reset, auditiert mit Länge). UI: Textarea + „Speichern"/„Auf Standard zurücksetzen". Config: `weather.llm_detail` (Default `compact`, schema `list(compact|full)?`).
**Quelle:** User-Vorgabe (Wetter ans LLM; Detailgrad in Addon-Config wählbar; Prompt über die App-Oberfläche editierbar statt Git-Push/Update). → [06](06-prognosen.md), [07](07-planning-engine.md)

## D-044 · One Call API 4.0 als umschaltbare Wetterquelle (opt-in); per-Timeline-Refresh; erste Seite
**Entscheidung:** Neben der bestehenden „5 day / 3 hour forecast"-API (D-042) gibt es jetzt die **OpenWeatherMap One Call API 4.0** als **opt-in-Alternative**, umschaltbar in der Addon-Config über `weather.source` (`forecast3h` = **Default**, abo-/schlüsselfrei; `onecall` = One Call 4.0, Abo „One Call by Call" nötig). Bei `onecall` werden die **Timelines 15min/1h/1day** über getrennte Endpunkte abgerufen, **je einzeln aktivierbar** mit **eigenem Refresh-Intervall** (`weather.onecall.enable_*` / `refresh_*`). Es wird je Abruf **nur die erste Seite** geholt (1 bezahlter Call/Timeline/Refresh — Kosten-/Budget-Schutz; keine Pagination). Welche **eine** Timeline in den KI-Kontext fließt, ist konfigurierbar (`weather.onecall.llm_timeline`, Default `1h`; 15min/1h auf `forecast_horizon_h` gekürzt, 1day vollständig). Damit ist **W2** beantwortet („genauere Möglichkeit mit 15/60-min-Vorhersagen"). Zusätzlich **W3**: forecast3h-Default-Refresh **30 → 60 min**.
**Detail:** Neue Module `onecall_client.py` (`OneCallClient`, Muster wie `weather_client.py`; Endpunkte `/timeline/<res>`; Normalisierung auf energierelevante Felder, daily mit `temp_min/max`) und `OneCallCollector` in `weather_collector.py` (per-Timeline-Drosselung + isolierte Fehler je Timeline, Iron Rule 8; geteilte Zonenauflösung `resolve_zone_coords`). Neue Dataclasses `OneCallConfig`/`OneCallSlot`/`OneCallTimeline` (`weather.py`); `WeatherConfig` um `source`+`onecall` erweitert. `main.py` wählt Client/Collector nach `source`; beide Collector teilen die Schnittstelle (`snapshot`/`test_fetch`/…), `snapshot` trägt jetzt `"source"`. `plan_context._condense_weather` verzweigt auf `source`. Schlüssel nur als Query-Param `appid`, nie im Log (Iron Rule 6, geteilter `raise_for_owm_status`). UI zeigt je aktivierter Timeline eine eigene Tabelle. **Bewusst (noch) nicht:** kein `current`-Ist-Wetter, keine Pagination/Tiefen-Horizont, keine Alerts, kein Tages-Call-Budget-Zähler, keine HA-Sensoren/HEMS-Übergabe → [../claude-fragen/claude-fragen-v9.md](../claude-fragen/claude-fragen-v9.md) (O1–O5).
**Quelle:** User-Vorgabe (One Call API 4.0 integrieren; 15min/1h/1day abrufbar; per-Intervallplan eigene Abrufintervalle in der App-Config; Umschalter 3h5day ↔ One Call 4.0). Geklärt: forecast3h bleibt Default, llm_timeline konfigurierbar, nur erste Seite je Timeline. → [06](06-prognosen.md)

## D-045 · One Call 4.0: paginierte Calls je Timeline (1–5) + Pflicht-Tages-Call-Budget; Unwetter-Alerts aufgenommen
**Entscheidung:** (1) **O2 — Pagination + Budget:** Je One-Call-Timeline (15min/1h/1day) sind nun **1–5 paginierte Seiten** je Refresh wählbar (`weather.onecall.pages_15min/1h/1day`, Default 1 = erste Seite). Jede Seite folgt dem `next`-Cursor und ist ein eigener **bezahlter** Call. **Zwingend** (User: „GANZ WICHTIG / MUSS") ist ein **harter Schutz gegen Überschreiten von 1000 Calls/Tag**: ein konfigurierbares **Tages-Call-Budget** (`weather.onecall.daily_call_budget`, Default **1000** = OWM-Freikontingent), das über **alle** bezahlten One-Call-Anfragen (Timelines **und** Alerts) gilt, in **UTC** gezählt wird (Reset um Mitternacht, deckt sich mit OWM) und **persistent** über den KV-Speicher (`config`-Tabelle, `/data`) geführt wird — damit umgeht auch ein **Neustart-Loop** das Limit nicht. Erschöpft ⇒ weitere Abrufe werden **übersprungen** (Iron Rule 8 — EP blockiert nie), **einmalig** auditiert (`onecall_budget_exhausted`) und im UI angezeigt; auch „Wetter testen" bucht gegen dasselbe Budget. (2) **O3 — Alerts:** Behördliche Unwetterwarnungen werden **aufgenommen** (`weather.onecall.enable_alerts`, **Default an**; eigener Refresh `refresh_alerts`, Default 30 min), **vorerst nur als Daten/Anzeige** — **keine** Einspeisung in die Planung. Begründung User: Zukunftsaspekt, z.B. Batterieladung bei drohendem Gewitter (möglicher Stromausfall) priorisieren.
**Detail:** Neues Modul `onecall_budget.py` (`calls_today`/`remaining`/`consume`, UTC-Tag, KV über `settings.py`). `onecall_client.py`: `fetch_timeline(..., max_calls)` paginiert (folgt `next`) und liefert `(Timeline, calls_used)`; neue `fetch_alerts`/`parse_alerts` + `OneCallAlert`-Dataclass (`weather.py`). `OneCallCollector` (`weather_collector.py`) ist Budget-Autorität: pro Timeline `max_calls = min(pages, remaining)`, danach `consume(calls_used)`; Alerts als eigener gedrosselter Slot (1 Call); `snapshot` um `daily_call_budget`/`calls_today`/`budget_remaining`/`budget_exhausted`/`alerts*` erweitert; `main.py` reicht die DB durch. Config (`config.yaml`) `weather.onecall` um `pages_*`, `daily_call_budget`, `enable_alerts`, `refresh_alerts` ergänzt; Version `0.0.22`. **Geparkt (keine Aktion):** O1 `current`-Ist-Wetter, O4 mehrere Timelines gleichzeitig ans LLM, O5 historische Daten (alle Zukunft/V2+).
**Quelle:** v9-O2/O3 (claude-fragen-v9). → [06](06-prognosen.md), [../claude-fragen/claude-fragen-v10.md](../claude-fragen/claude-fragen-v10.md)

## D-046 · Geräte-Discovery nur noch über das HEMS (kein Config-Fallback) + Auto-Retry + manueller HEMS-Sync
**Entscheidung:** Die Geräte werden **ausschließlich** aus dem HEMS-Kontrollschema (`/api/device_controls_schema`, D-036) erkannt; der bisherige **Geräte-Fallback in der Addon-Config** (`devices`) wird **ersatzlos entfernt**. Begründung des Users: Ist das HEMS nicht verfügbar, kann es die EP-Vorschläge ohnehin nicht verarbeiten – ein Fallback, der EP „am Leben hält", während der einzige Konsument (HEMS) fehlt, bringt nichts (Leitsatz „EP ohne HEMS sinnlos"). Die HEMS-Namenskonvention (`name`/`entity_prefix`) wird **1:1** übernommen; EP-eigene Erzeugnisse bleiben `ep_*` (D-029).
**Detail:** `devices.discover(hems_client, logger)` liefert nur noch `hems` | `none` (kein `devices_from_config` mehr). Weil Home Assistant **keine Addon-Startreihenfolge garantiert**, kann das HEMS beim EP-Start noch nicht erreichbar sein – sonst liefe EP dauerhaft ohne Geräte (Discovery ist ein Start-Hook, keine Dauerschleife). Daher zwei Ergänzungen: (1) **Auto-Retry** im Webserver – bleibt die Start-Discovery ohne Geräte, wird sie im Hintergrund **bis zu 5×** im Abstand von **30 s** wiederholt (`DISCOVERY_RETRY_ATTEMPTS`/`DISCOVERY_RETRY_DELAY_S`), Abbruch beim ersten Erfolg, sauberer Task-Abbruch beim Shutdown. (2) **Manueller HEMS-Sync** – Button „Geräte von HEMS neu laden" im HEMS-Tab → `POST /api/hems/rediscover`. Beide nutzen die gemeinsame `rediscover_devices(app)`, die zusätzlich die Allowlist per **`EntityAllowlist.rebuild`** (statt additivem `register_all`) neu aufbaut, damit `ems_*`-Entitäten umbenannter/entfernter Geräte nicht als Leichen im Register bleiben. Entfernt: Config-Schlüssel `devices` inkl. `config.yaml`-Schema; Version `0.0.26`.
**Quelle:** User-Vorgabe (Geräte komplett vom HEMS ziehen; Config-Fallback bringt bei HEMS-Ausfall nichts; 5×30 s Auto-Retry + manueller HEMS-Refresh-Button im HEMS-Tab). → [01](01-homeassistant-integration.md), [03](03-api-schnittstelle-hems.md), [roadmap](roadmap.md)

## D-047 · Konfigurierbare Zusatz-Entitäten je Gerät (generalisiert & ersetzt den Heizstab-Hardcode D-035)
**Entscheidung:** Zu jedem vom HEMS importierten Gerät kann der User im **Geräte-Tab** beliebige **Zusatz-Entitäten** pflegen — Werte, die EP **zusätzlich** zu den HEMS-`ems_*`-Feldern (und den Standard-Vorschlägen Prio/Freigabe/Mindestleistung) liest. Je Eintrag: (1) die zu lesende **Entity-ID** (frei, z.B. `input_number.min_soc_auto`); (2) eine **Checkbox „KI liefert Vorschlagswert"** — ist sie aktiv, erzeugt die KI zusätzlich einen **HA-Sensor** nach festem Namensschema `sensor.ep_<obj>_vorschlag`, wobei `<obj>` = object_id der Quell-Entität ohne führendes `ep_` (`input_number.min_soc_auto` → `sensor.ep_min_soc_auto_vorschlag`; `input_number.ep_heizstab_max_temperatur` → `sensor.ep_heizstab_max_temperatur_vorschlag`, kein `ep_ep_`); (3) ein **Freitextfeld**, das der KI Bedeutung und Verwendung/Interpretation des Werts erklärt. Diese Vorschläge sind **advisorisch**: sie werden **nur als HA-Sensor** bereitgestellt und **nicht an das HEMS** übergeben (das HEMS kennt sie nicht) — sie unterliegen daher **keiner harten Grenze/Klemmung** (der Freitext steuert die KI). Auch **ohne** aktivierten Vorschlag wird der Wert gelesen und der KI als Kontext übergeben. Damit wird der bisher **hardcodierte** Heizstab-Sonderfall (**D-035**, max. Wassertemperatur) **abgelöst**: er wird beim ersten HEMS-Sync **einmalig als editierbare Zusatz-Entität geseedet** (Namensschema/Verhalten identisch, nun frei umkonfigurier-/löschbar).
**Detail:** Datenmodell `DeviceExtra` (`devices.py`) mit Ableitungen `object_id`/`read_key` (`extra_<obj>`, kollisionsfrei zu `ems_*`)/`plan_field` (`extra_<obj>_vorschlag`)/`suggestion_entity_id`; als `Device.extras` nach der Discovery gemergt. Persistenz `device_extras.py` + Tabelle `device_extras` (**Migration 6**): `load_extras`/`apply_extras`/`upsert_extra`/`delete_extra`/`suggestion_conflict` (verhindert kollidierende Vorschlags-Sensoren) + `seed_defaults` (Heizstab-Default, einmalig über KV-Marker, auch nach User-Löschung kein Re-Seed). Read-Weg: `read_fields` hängt die Extras an (Collector **und** Allowlist erhalten sie automatisch, single source of truth); `DeviceCollector.snapshot` blendet sie aus den Standard-`fields` aus (separater Editor). KI-Weg: `constraints.ConstraintExtra` trägt den Lesewert; `plan_schema.suggestion_keys` fügt die aktivierten `extra_*_vorschlag`-Felder dem Schreibvertrag hinzu, `DeviceSuggestion.extras`-Dict + `plan_to_dict`-Flattening + `PLAN_JSON_SCHEMA.patternProperties ^extra_.*_vorschlag$`; `planner._assemble_plan` übernimmt die dynamischen Felder; `plan_context` liefert je Gerät `zusatzwerte` (Wert + Freitext) und ergänzt das Gemini-Antwort-Schema dynamisch; `suggestion_publisher` schreibt `sensor.ep_<obj>_vorschlag` mit Label/Einheit der Zusatz-Entität. Entfernt: `is_heizstab`/`max_water_temp` (constraints), festes `max_temperatur_vorschlag` (plan_schema/validator-Klemmung/publisher/plan_context/UI). Web: `GET /api/devices` liefert je Gerät `extras`; `POST`/`DELETE /api/devices/extras` (Validierung Gerät/Entity-ID/Kollision), Übernahme ohne HEMS-Reload via `reapply_device_extras`. UI: Zusatz-Entitäten-Editor im Geräte-Tab (Entity + Checkbox + Freitext + optional Label/Einheit); Auto-Refresh pausiert beim Tippen. Version `0.0.28`.
**Quelle:** User-Vorgabe (Zusatz-Entitäten pro HEMS-Gerät im Geräte-Tab konfigurierbar; Entity + Checkbox „KI-Vorschlag" → `sensor.ep_<entität>_vorschlag`; Freitext für die KI; Wert nur als HA-Sensor, nicht ans HEMS; Heizstab-Max.-Temp nicht mehr hardcodieren). → [01](01-homeassistant-integration.md), [05](05-daten-und-speicherung.md), [07](07-planning-engine.md), [09](09-ui-ingress.md)

## D-048 · Zusatz-Entitäten: alle HA-Domänen + typ-/attributabhängige Behandlung
**Entscheidung:** Die Zusatz-Entitäten (D-047) sind nicht auf `input_number` beschränkt, sondern akzeptieren **beliebige HA-Domänen** — insbesondere `sensor`, `input_number`, `input_boolean`, `input_datetime`, `input_text`. EP liest den Wert **typgerecht** und die KI liefert einen **typgerechten** Vorschlagswert (`sensor.ep_<obj>_vorschlag`). Der Datentyp folgt der Domäne: `input_number`/`number` → Zahl; `input_boolean`/`switch`/`binary_sensor` → Bool; `input_datetime` → Datum/Uhrzeit als String; `input_text`/`text` → Text; nicht gelistete (v.a. `sensor`) → **auto** (Zahl bei numerischem Zustand, sonst Text). **Zusätzlich gelesene Attribute (User-Vorgabe):** bei `input_number` gehen `min`/`max` als **Ober-/Untergrenze an die KI** und **klemmen** den Vorschlag; bei `input_datetime` bestimmen `has_date`/`has_time` das **erwartete String-Format** (`YYYY-MM-DD HH:MM:SS` / nur Datum / nur Uhrzeit), das der KI mitgegeben wird. Andere Typen (Bool/Datum/Text) laufen ungeklemmt durch (advisorisch, D-047).
**Detail:** `DeviceExtra.domain`/`kind`/`capture_attrs` leiten Typ + mitzulesende Attribute aus der Domäne ab (`devices._DOMAIN_KIND`); `ReadField.capture_attrs` trägt die Attributnamen. `device_collector.parse_by_kind` interpretiert den Zustand typgerecht (`parse_bool`/`safe_float`/`parse_text`, auto = Zahl-sonst-Text) und `_read_field` erfasst zusätzlich die deklarierten Attribute; Readings-Record ist jetzt `{value, source, attrs}`. `constraints.ConstraintExtra` trägt `kind` (auto → number/text nach Wert) + `min`/`max`/`has_date`/`has_time`. `plan_context`: `zusatzwerte` liefern `typ`, `untergrenze`/`obergrenze` (input_number) bzw. `format` (input_datetime); `build_response_schema` setzt den Gemini-Typ je `kind` (`_KIND_TO_GEMINI`: NUMBER/BOOLEAN/STRING) und schreibt Grenzen/Format in die Feldbeschreibung. `plan_schema.PLAN_JSON_SCHEMA` erlaubt für `extra_*_vorschlag` nun `number|boolean|string`. `validator` klemmt number-Zusätze auf `[min,max]`. UI (`/api/devices` → `extras` mit `kind`/`domain`/`attrs`): Geräte-Tab zeigt Typ + Grenzen/Format, Wert-/Plan-Anzeige typgerecht (Bool→Ja/Nein, String direkt). Version `0.0.29`.
**Quelle:** User-Vorgabe (grundsätzlich alle Domänen, v.a. sensor/input_number/input_boolean/input_datetime/input_text; bei input_number min/max als Ober-/Untergrenze an die KI; bei input_datetime has_date/has_time beachten). → [01](01-homeassistant-integration.md), [05](05-daten-und-speicherung.md), [07](07-planning-engine.md), [09](09-ui-ingress.md)

## D-049 · Zusatz-Entitäten: input_select mit Auswahlpool als KI-Wertemenge
**Entscheidung:** Zusätzlich zu den bisherigen Domänen (D-048) sind auch **`input_select`** (und die HA-`select`-Entität) als Zusatz-Entität konfigurierbar. Die im Select **verfügbaren Optionen** (`options`-Attribut) werden der KI als **Wertepool** übergeben. Ist für die Entität ein Vorschlagswert gefordert (`ai_suggestion`), **muss** die KI **genau eine** dieser Optionen als Vorschlag wählen. Der aktuelle Zustand (die gewählte Option) geht wie bei den anderen Typen als Kontext + Freitext an die KI.
**Detail:** `DeviceExtra.kind` = `select` für `input_select`/`select`; `capture_attrs` liest zusätzlich `options`. `constraints.ConstraintExtra.options` trägt den Pool (`_as_options`: Liste → Tuple[str]). `plan_context`: `zusatzwerte[].optionen` listet den Pool; `build_response_schema` setzt für Select-Felder `{"type": "STRING", "enum": options}` (Gemini erzwingt so die Auswahl) plus Optionen in der Feldbeschreibung. Der `validator` ist die Absicherung: ein Vorschlag außerhalb des Pools wird **verworfen** (Feld aus dem Plan entfernt, als Klemmung protokolliert) statt den ganzen Plan abzulehnen – konsistent mit der advisorischen Natur (D-047, nur HA-Sensor). UI (`/api/devices` → `extras.attrs.options`): Geräte-Tab zeigt die Optionen je Select-Zusatzentität. Version `0.0.30`.
**Quelle:** User-Vorgabe (zusätzlich input_select; verfügbare Auswahlwerte als Wertepool an die KI; wenn Vorschlagswert gefordert, wählt die KI genau einen daraus). → [01](01-homeassistant-integration.md), [07](07-planning-engine.md), [09](09-ui-ingress.md)

## Bestätigt aus v8 (keine eigene D-Nummer)
- **W4** Koordinatenquelle: `zone.home` bleibt Default (unverändert, vgl. D-042) — kein globaler HA-Standort-Fallback.
- **W5** Behaltene Wetterfelder reichen (nur Solar/PV-relevant); keine Windrichtung o.ä.
- **W6** Wetter als HA-Sensor bzw. über HEMS-API bleibt **optionaler späterer Meilenstein** (zwei Unterpunkte HA + API) — keine sofortige Aktion.

## Noch offen (geparkt, siehe claude-fragen-v6/-v10)
- **v9-O2/O3 erledigt → D-045** (Pagination 1–5 + Pflicht-Tages-Call-Budget; Unwetter-Alerts aufgenommen). **Geparkt für Zukunft/V2+:** **O1** `current`-Ist-Wetter, **O4** mehrere Timelines gleichzeitig ans LLM, **O5** historische Daten — fortgeführt in [../claude-fragen/claude-fragen-v10.md](../claude-fragen/claude-fragen-v10.md). **(v8-W1/W2/W3 → D-043/D-044; W4–W6 bestätigt.)**
- **v6-B1** Ampere-Varianten (`_a`) vorausschauend festziehen — nur Bestätigung. HEMS unterstützt Ampere bereits nativ pro Gerät via `output_unit: ampere` (Suffix `_a` + `min_umschaltzeit_s`).
- **v6-B2** Schreibweise/Umlaute der Suffixe (ASCII-Entity-IDs vs. Umlaut-Anzeige). HEMS-Evidenz: Entity-IDs durchgängig **ASCII ohne Umlaute** (`prioritat`, `geschutzte`, `anderung`).
- **v6-B3** (=v5-B1) Hybrid-Modus: fixierbare Felder pro Gerät — relevant ab M3.
- **v6-B4** (=v5-B2) Plan-JSON-Schema gemeinsam mit HEMS — Ebene 2 (M3). **Neu zu klären:** Suffix-Mapping beim späteren 1:1-Schreibweg (EP `prio_vorschlag` ↔ HEMS `prioritat`; `_vorschlag` entfällt HEMS-seitig).
