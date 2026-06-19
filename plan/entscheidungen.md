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
**Detail:** Da Entity-IDs ohnehin nur aus der Config stammen, ist die Allowlist Defense-in-Depth + Transparenzregister. Soft statt hart, weil eine Fehlkonfiguration der Allowlist den lokalen Anlagenbetrieb **nie** stören darf (Leitprinzip „Fallback blockiert nie"). Umsetzung: Modul `allowlist.py` (`EntityAllowlist`, `collect_entity_ids`), weicher Guard in `HAClient.get_state`, Persistenz in DB-Tabelle `allowlist` (Migration v3) + Audit beim Rebuild, Transparenz unter `GET /api/allowlist` und im Status-Tab. Geräte-IDs kommen nach der HEMS/Config-Discovery hinzu (`_discover_devices`), dann wird das komplette Register einmal persistiert. Doppel-Audits je Entität werden gedrosselt (kein Log-Spam pro Poll-Zyklus).
**Quelle:** Umsetzung „letzter M1-Baustein" (roadmap); Durchsetzungsgrad vom User auf **soft** festgelegt. → [01](01-homeassistant-integration.md), [08](08-validierung-sicherheit.md), [roadmap](roadmap.md) (M1)

## Noch offen (geparkt, siehe claude-fragen-v7)
- **v6-B1** Ampere-Varianten (`_a`) vorausschauend festziehen — nur Bestätigung. HEMS unterstützt Ampere bereits nativ pro Gerät via `output_unit: ampere` (Suffix `_a` + `min_umschaltzeit_s`).
- **v6-B2** Schreibweise/Umlaute der Suffixe (ASCII-Entity-IDs vs. Umlaut-Anzeige). HEMS-Evidenz: Entity-IDs durchgängig **ASCII ohne Umlaute** (`prioritat`, `geschutzte`, `anderung`).
- **v6-B3** (=v5-B1) Hybrid-Modus: fixierbare Felder pro Gerät — relevant ab M3.
- **v6-B4** (=v5-B2) Plan-JSON-Schema gemeinsam mit HEMS — Ebene 2 (M3). **Neu zu klären:** Suffix-Mapping beim späteren 1:1-Schreibweg (EP `prio_vorschlag` ↔ HEMS `prioritat`; `_vorschlag` entfällt HEMS-seitig).
