# Claude-Fragen — v1 (Stand 16.06.2026) · ✅ BEANTWORTET / ARCHIVIERT

> **Status:** Vollständig beantwortet und eingearbeitet. Die Entscheidungen liegen jetzt im Decision Log [../plan/entscheidungen.md](../plan/entscheidungen.md) (D-001…D-015) und in den plan/-Dateien. Aktuelle offene Fragen: [claude-fragen-v2.md](claude-fragen-v2.md). Diese Datei bleibt nur als Historie erhalten.

---

Alle offenen Fragen von mir (Claude) an den User, nach **Wichtigkeit** geordnet und aufgeteilt in **aktuell projektrelevant** (blockiert/beeinflusst die nächsten Schritte) und **noch nicht projektrelevant** (später relevant). Beantwortete Fragen werden hier durchgestrichen/markiert und in [../user-fragen.md](../user-fragen.md) bzw. den plan/-Dateien eingearbeitet.

Versionierung: bei größeren Änderungen neue Datei `claude-fragen-v2.md` usw.; diese Datei bleibt als Historie erhalten.

---

## A — Aktuell projektrelevant

### A1 — HEMS-Plan-API: Wer baut den Empfangsendpunkt? *(höchste Priorität, blockiert M3)*
HEMS nimmt heute Werte über HA-Helfer + `/api/set` entgegen, hat aber keinen `/api/v1/strategy-plans`-Empfänger. Soll ich
(a) zunächst rein über Helfer/`/api/set` integrieren (schnell, HEMS unverändert) und
(b) später im **SkytechHEMS-Repo** einen versionierten Plan-Endpunkt ergänzen?
Darf ich überhaupt ins HEMS-Repo committen (gleiche `claude/main`-Regel dort?), oder nur EP-seitig arbeiten? → betrifft [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort: Für die erste lauffähige version nehmen wir nur mal HA Helfer/Entitäten, also (a) später bauen wir dann zusätzlich auf einen API Endpunkt in Skytech HEMS Repo um, dann darfst du auch in dem REPO was änder, das richtige ich dann so ein das du lokal in beiden paralel arbeiten kannst

### A2 — KI-Plan direkt vs. lokale Optimierungsengine in V1
info.md sieht die deterministische Optimierungsengine erst in Phase 6. Bestätigst du, dass die **KI in M2 den Plan direkt** erzeugt (gegen harte Grenzen geklemmt) und die Engine erst später kommt? Oder willst du die Engine früher? → [../plan/07-planning-engine.md](../plan/07-planning-engine.md), [../plan/04-ki-provider.md](../plan/04-ki-provider.md).

Die KI darf in der V1 schon vorschlagswerte liefer (diese können wir dann in der Addon/App oberfläche, HA-Sensoren, Logging sehen) aber die werte werden noch nicht übernommen. und langfristig soll es so sein das die 3 Modi vollständig implementiert sind die ich in user-regeln.md nachgetragen habe

### A3 — Mittelungsfenster konkret
Default ist 15 min (User-Antwort übernommen). Soll EP **mehrere Fenster gleichzeitig** vorhalten (z.B. 1/15/60 min) und welches geht an KI vs. Ereigniserkennung? Reicht dir vorerst ein einzelnes konfigurierbares 15-min-Fenster? → [../plan/05-daten-und-speicherung.md](../plan/05-daten-und-speicherung.md).

Antwort: Wir nehmen 1, 15 und 60 Minutenfenster, über die Mittelwerte machen wir keine Ereigniskopplung

### A4 — Entitäten-Namensschema: Feldbelegung
Schema ist `<DOMAIN>.ep_<GERÄTENAME>_<PREFIX>_<SUFFIX>`. Mir fehlt die genaue Bedeutung/Belegung von `<PREFIX>` neben `<GERÄTENAME>` und `<SUFFIX>`. Kannst du 3–4 reale Beispielnamen geben (z.B. für Batterie-Ziel-SOC, Heizstab-Freigabe), damit ich das Schema eindeutig implementiere? → [../plan/01-homeassistant-integration.md](../plan/01-homeassistant-integration.md).

Antwort: Grundlegend kannst du das namensschema wie beim HEMS nehmen. sensor.ep_batterie_1_ziel_soc, sensor.ep_heizstab_freigabe | Prefix und Suffix können da etwas miteinander verschwimmen sag ich mal

### A5 — Anlegen der HA-Helfer
Soll EP benötigte `input_*`-Helfer **automatisch anlegen** (wie HEMS es tut) oder legt der User sie manuell an und EP liest nur? → [../plan/01-homeassistant-integration.md](../plan/01-homeassistant-integration.md).

Antwort: Ich habe einen user-beispiele Ordner erstelle, da ist eine .txt Datei wie die yaml Dateien ausschauen sollen die ich dann einfach in Homeassistant in den jeweiligen domain order in der config einfüge, das beispiel wäre jetzt konkret für input_number. Das machen wir für alle Helfer Domänen so die benötigt werden. Die yaml dateien nennst du dann <domain>_ep.yaml und speicherst sie im ordner claude-ha-config-dateien ab

### A6 — Vorhandene Prognose-/Preis-Integrationen
Welche HA-Integrationen nutzt du bereits? PV-Prognose (Solcast/Forecast.Solar/…?), Wetter, Strompreis (Tibber/Awattar/EPEX/…?). Bestimmt, woran ich M1/M2 andocke. → [../plan/06-prognosen.md](../plan/06-prognosen.md).

Antwort: PV-Prognose und Strompreis kann ich über HA Sensoren bereits bereitstellen, diese will ich (wie angegben) in der Addon/App Config in HA pflegen bzw. hinterlegen

### A7 — KI-Provider/Modell-Defaults & Budget
Welche Default-Modelle (OpenAI/Gemini) und welches Tages-/Monats-Kostenlimit soll ich voreinstellen? Hast du bereits API-Keys für beide oder zunächst nur einen Provider? → [../plan/04-ki-provider.md](../plan/04-ki-provider.md).

Antwort: Ich habe aktuell einen gratis API Key für Gemini soweit ich weiß sind da ca 10 API Anfragen pro Minute erlaubt, damit möchte ich voerst starten, aber eben zukunftssicher das ich die Provider/Modelle dann wecheseln kann (auch am besten über Addon/App Config einstellbar)

---

## B — Noch nicht projektrelevant (später)

### B1 — UI-Stack
SPA in vanilla JS/CSS (wie HEMS, konsistent) oder leichtes Framework? Erst ab ausgebauter UI relevant. → [../plan/09-ui-ingress.md](../plan/09-ui-ingress.md).

Antwort: Ich würde am Anfang was einfaches/funktionales nehmen und später dann evtl. auf ein Framework gehen damit man die Oberfläche schöner gestallten kann. Aber zum start nimm die technik die du am sinnvollsten hältst

### B2 — Default-Zielgewichtung
Beispielgewichtung aus info.md §7 als Startwert übernehmen oder beim ersten Setup abfragen? Relevant ab M2/M4. → [../plan/07-planning-engine.md](../plan/07-planning-engine.md).

Antwort: Mach es als Punkt pflegbar in der Addon/App Config aber übernimm initial die Werte aus der info.md in diese Config

### B3 — Mindestkonfidenz & Delta-Limit
Konkrete Default-Werte für Mindestkonfidenz (Auto-Submit) und maximale Planänderung pro Schritt. Relevant ab M3/M5. → [../plan/08-validierung-sicherheit.md](../plan/08-validierung-sicherheit.md).

### B4 — Aufbewahrungsfristen & DB-Budget
Default-Retention für raw/agg/Pläne/Audit und max. SQLite-Größe im Container. Relevant ab M1+, unkritisch für Start. → [../plan/05-daten-und-speicherung.md](../plan/05-daten-und-speicherung.md).

Antwort: vorerst empfohlene Werte von dir das wir die Zeiten für die genaue Prognose etc. einhalten, und später können wir das über eine zusätzliche Config noch ausbauen

### B5 — Auth EP↔HEMS im Addon-Netz
Token, interner Hostname, mTLS? Relevant ab M3. → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort: Nimm das was du denkst das am besten funktioniert für HA Addons/Apps. ABER behalte im Hinterkopf (nimm das auch in die claude.md) das ich auf gewisse daten von meinem internen netzwerk aus über ein ios-Backend (Java läfut auf einem Linux Server) zugreifen will bzw. werte setzen will, ich denke da an sowas wie abfahrtzeit vom E-Auto für die einhaltung der Mindestladung etc.

### B6 — Fahrplan-Granularität
15-min-Slots über 24–48 h? Relevant ab Simulation/Optimierung (M4/M6). → [../plan/07-planning-engine.md](../plan/07-planning-engine.md).

Antwort: Die Datenspeicherung (wie auch schon in B4) etwas beschreiben machen wie von Anfang an so das es für 1,15,60 Minuten passt, natürlich wir die langzeitprognose nur auf die 60 Minuten summierung zugreifen

### B7 — Auto-Export von Logs bei Fehlern
Soll bei `ERROR`/`CRITICAL` automatisch ein KI-lesbares Log-Bundle erzeugt/benachrichtigt werden? Komfort, nicht blockierend. → [../plan/10-logging-observability.md](../plan/10-logging-observability.md).

Antwort: JA wenn es für mich als User die Fehlerbehandlung mit der KI zusammen leichter macht

### B8 — CI-Coverage-Schwelle
Ziel-Coverage für V1 und ob CI eigenständig oder an HEMS-Workflows angelehnt. Relevant sobald CI steht (M0+). → [../plan/11-tests-ci.md](../plan/11-tests-ci.md).

Antwort: So wie es am Sinnvollsten hälts, aber es soll am besten so sein das irgenwo schon das zusammenspiel zwischen HEMS und EP getestet wird

---

## Beantwortet / eingearbeitet
- **Live-Werte vs. Mittelwert** → beantwortet in [../user-fragen.md](../user-fragen.md): EP bekommt Live-Werte und bildet selbst gleitende Mittel (Default 15 min). Detailfrage zu mehreren Fenstern offen als **A3**.
