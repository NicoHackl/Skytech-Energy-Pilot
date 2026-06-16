# Claude-Fragen — v3 (Stand 16.06.2026) · ✅ A-FRAGEN BEANTWORTET / ARCHIVIERT

> **Status:** A-Fragen beantwortet und eingearbeitet → Decision Log [../plan/entscheidungen.md](../plan/entscheidungen.md) (D-025, D-026). Die B-Fragen wurden vom User als „noch zu früh" geparkt und laufen in [claude-fragen-v4.md](claude-fragen-v4.md) weiter. Diese Datei bleibt als Historie.

---

Offene Fragen von mir (Claude) an den User, nach **Wichtigkeit** geordnet.

- Beantwortete Fragen aus [claude-fragen-v2.md](claude-fragen-v2.md) sind in den Decision Log [../plan/entscheidungen.md](../plan/entscheidungen.md) (D-016…D-024) und die plan/-Dateien eingearbeitet — sie stehen hier **nicht mehr**.
- Beantwortung: Antwort direkt unter die Frage schreiben; ich übernehme sie nach entscheidungen.md und entferne sie in v4.

---

## A — Aktuell projektrelevant

### A1 — Default-Gemini-Modell *(deine Antwort in v2 war abgeschnitten: „… ich hätte an")*
Modellwahl ist in der Addon-Config änderbar (D-019). Welches **konkrete Gemini-Modell** soll der Default sein (passend zum Free-Tier ~10 req/min)? Wenn du keine Präferenz hast, schlage ich ein aktuelles, günstiges Gemini-Flash-Modell als Default vor. → [../plan/04-ki-provider.md](../plan/04-ki-provider.md).

Antwort: Such gerne eins aus, ich denke das gemini 3.5 flash gut passen sollte

### A2 — PV-Prognose-Sensor: Format/Attribut-Struktur
Du pflegst die PV-Sensoren selbst (mehrere möglich, D-018). Damit ich die vier Werte (Energie aktuelle Stunde / nächste Stunde / verbleibend heute / morgen) korrekt auslese: liegen die als **eigene Sensor-Entitäten** vor, oder als **Attribute** an einem Sensor? Magst du **ein Beispiel** eines solchen Sensors (Entitätsname + State/Attribute) hierher kopieren? → [../plan/06-prognosen.md](../plan/06-prognosen.md).

Antwort: der Wert ist direkt am Sensor, also State, nicht ein Attribut

---

## B — Noch nicht projektrelevant (später)

### B1 — Hybrid-Modus: fixierbare Felder pro Gerät
Im Hybrid-Modus (D-009/D-020) fixiert der User Werte, die für die KI hart werden. Welche Felder sollen pro Gerät fixierbar sein? Mein Vorschlag, sobald M3 näher rückt — fürs Erste keine Aktion nötig. → [../plan/12-steuermodi.md](../plan/12-steuermodi.md).

Antwort:

### B2 — Plan-JSON-Schema gemeinsam mit HEMS
Sobald die HEMS-Plan-API (Ebene 2, D-002) ansteht: Schema-Version + Felder gemeinsam im HEMS-Repo pflegen. Reine Vormerkung. → [../plan/03-api-schnittstelle-hems.md](../plan/03-api-schnittstelle-hems.md).

Antwort:

---

## Erledigt seit v2 (Verweis)
v2-Antworten → Decision Log **D-016…D-024**. Einzig **A4 (Gemini-Modell)** blieb wegen abgeschnittener Antwort offen → hier als **A1** weitergeführt.
