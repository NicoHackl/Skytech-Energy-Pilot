# Claude-Fragen — v2 (Stand 16.06.2026) · ✅ BEANTWORTET / ARCHIVIERT

> **Status:** Beantwortet und eingearbeitet → Decision Log [../plan/entscheidungen.md](../plan/entscheidungen.md) (D-016…D-024) + plan/-Dateien. Einzig **A4 (Gemini-Modell)** blieb offen (Antwort abgeschnitten) und läuft in [claude-fragen-v3.md](claude-fragen-v3.md) weiter. Diese Datei bleibt als Historie.

---

Offene Fragen von mir (Claude) an den User, nach **Wichtigkeit** geordnet, aufgeteilt in **aktuell projektrelevant** und **noch nicht projektrelevant**.

- Beantwortete Fragen aus [claude-fragen-v1.md](claude-fragen-v1.md) sind **eingearbeitet** in den Decision Log [../plan/entscheidungen.md](../plan/entscheidungen.md) (D-001…D-015) und die plan/-Dateien — sie tauchen hier **nicht mehr** auf.
- Beantwortung wie bisher: Antwort direkt unter die Frage schreiben; ich übernehme sie dann nach entscheidungen.md und entferne sie in der nächsten Version (v3).

---

## A — Aktuell projektrelevant

### A1 — Phase-1-Helfer bestätigen
Ich habe einen Vorschlag für die HA-Helfer in [../claude-ha-config-dateien/](../claude-ha-config-dateien/) abgelegt (input_number/boolean/select/datetime, Geräte: Batterie 1, Heizstab, Heizlüfter 1/2). **Passt der Satz so?** Fehlt etwas (z.B. weitere Grenzwerte, Geräteindex-Schema), oder ist etwas zu viel? → [../plan/01-homeassistant-integration.md](../plan/01-homeassistant-integration.md).

Antwort: Ich habe die Config.yaml dateien angepasst und auch teilweise da Kommentare hinzugefüt

### A2 — Konkrete HA-Sensoren für PV-Prognose & Strompreis
Wie heißen die bestehenden Sensor-Entitäten, die ich in der Addon-Config als PV-Prognose und Strompreis hinterlegen können soll? (Brauche ich für M1/M2-Tests; Format/Einheit/Attribut-Struktur ist relevant.) → [../plan/06-prognosen.md](../plan/06-prognosen.md).

Antwort: Ich hinterlege die Sensoren für PV-Prognose dann selber in der Config, WICHTIG mache es so das ma von jedem sensor merhere pflegen kann (pv hat unterschiedliche ausrichtung), und als werte hätte ich vorgeschlagen, energie aktuelle stunde, energie nächste stunde, energie verbleibend heute, energie morgen. Für Strompreis lassen wir aktuell weg da ich aktuell keinen Dynamischen Stromtarif habe

### A3 — Wetterprognose in V1?
Du hast nur PV-Prognose + Strompreis genannt. Brauchst du in V1 zusätzlich eine **Wetterprognose** (eigener Sensor), oder reicht die PV-Prognose als Erzeugungsgrundlage? → [../plan/06-prognosen.md](../plan/06-prognosen.md).

Antwort: Wie schon in A2 gesagt, ich brauche aktuell nur Pv-Prognose

### A4 — Default-Gemini-Modell
Welches konkrete Gemini-Modell soll ich als Default voreinstellen (innerhalb deines Free-Tiers sinnvoll)? Falls unklar, schlage ich eines vor und mache es in der Addon-Config änderbar. → [../plan/04-ki-provider.md](../plan/04-ki-provider.md).

Antwort: Ja genau mache es änderbar in der config und ich hätte an

### A5 — Steuermodus global oder pro Gerät?
Soll der Steuermodus (Manuell/Hybrid/Automatisch) **global** für die ganze Anlage gelten oder **pro Gerät** einstellbar sein (z.B. Batterie Hybrid, Heizstab Automatisch)? Beeinflusst Datenmodell + UI. → [../plan/12-steuermodi.md](../plan/12-steuermodi.md).

Antwort: wohol als auch, wenn global hybrid steht kann man es noch pro gerät pflegen, wenn global manuell oder automatisch eingestellt ist muss ich entweder alls oder gar ncihts einstellen

---

## B — Noch nicht projektrelevant (später)

### B1 — Mindestkonfidenz & Delta-Limit *(in v1 als B3 offen geblieben)*
Konkrete Default-Werte für (a) Mindestkonfidenz für Auto-Übernahme und (b) maximale Planänderung pro Schritt (Delta-Limit). Vorschlag von mir, falls du keine Präferenz hast: Mindestkonfidenz 70 %, Delta-Limit z.B. ±20 % Leistung / ±10 % SOC-Ziel pro Planwechsel. Relevant ab M3/M5. → [../plan/08-validierung-sicherheit.md](../plan/08-validierung-sicherheit.md).

Antwort: übernimm vorerst deine Werte aber mache es wie so gut wie alles configurierbar in der Config des Addon/App

### B2 — Branch-Regel im HEMS-Repo
Sobald ich (Ebene 2, D-002) im **SkytechHEMS-Repo** arbeite: gilt dort dieselbe Regel „nur in `claude/main` committen/pushen"? Du hattest gesagt, du richtest paralleles lokales Arbeiten ein — gib mir kurz das OK zur Branch-Regel dort. → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort: gleiche Branch regel, nur in claude/main pushen

### B3 — Auth des externen iOS/Java-Backends
Für D-013: Das externe Backend soll bevorzugt **HA-Helfer** schreiben (z.B. `input_datetime.ep_eauto_abfahrtszeit`). Wie soll es sich gegenüber HA authentifizieren — über ein **Long-Lived Access Token** der HA-API? Oder willst du langfristig einen eigenen authentifizierten EP-Endpunkt? → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort: wir fangen mit eine LL-Token von HA an und evtel bauen wir es später noch um über einen eigen Endpunkt etc.

### B4 — CI-Coverage-Schwelle
Startwert für Test-Coverage als Qualitätsgate (Vorschlag: moderat starten, z.B. 60 %, später anheben). OK? → [../plan/11-tests-ci.md](../plan/11-tests-ci.md).

Antwort: ja das passt, und auch die Automatischen testes beim commit/push sollen nur laufen wenn allgemein auf claude/main gepushed wird

---

## Erledigt seit v1 (Verweis)
Alle A1–A7 und B1–B2, B4–B8 aus v1 sind beantwortet und in [../plan/entscheidungen.md](../plan/entscheidungen.md) als **D-001…D-015** dokumentiert. Einzige inhaltlich offen gebliebene v1-Frage war **B3 (Mindestkonfidenz/Delta-Limit)** → hier als **B1** weitergeführt.
