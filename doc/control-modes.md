# Steuermodi vs. Betriebsmodi

Zwei **getrennte Achsen** — nicht verwechseln.

## Achse 1: Steuermodi (WER steuert)

| Modus | User | KI/EP |
|---|---|---|
| **Manuell** | steuert alles | steuert nichts |
| **Hybrid** | fixiert bestimmte Werte/Gerätezustände | darf sie **nie** ändern, muss darum herum planen (harte Nebenbedingung) |
| **Automatisch** | Eingaben werden ignoriert | KI/EP-Werte haben **Vorrang** |

- **Hybrid ist der Kernfall:** vom User fixierte Werte werden zu zusätzlichen harten
  Nebenbedingungen für Planung/Validierung — ein Plan, der eine User-Fixierung
  verletzt, ist ungültig.
- **Geltung (D-020):** global=Hybrid → zusätzlich pro Gerät verfeinerbar (jedes Gerät
  unabhängig Manuell/Hybrid/Automatisch). global=Manuell oder Automatisch → gilt für
  **alle** Geräte, kein Per-Gerät-Override ("alles oder nichts").
- Technische harte Grenzen und HEMS-Doppelvalidierung bleiben in **jedem** Modus
  aktiv — "Automatisch" überschreibt nur Komfort-Eingaben des Users, nie
  Sicherheitsgrenzen.

## Achse 2: Betriebsmodi (WIE autonom gegenüber HEMS)

Einführungsreihenfolge: **Beobachten → Vorschlagen → Shadow Mode → Autopilot**

| Modus | Verhalten |
|---|---|
| Beobachten | nur Analyse, keine Pläne an HEMS |
| Vorschlagen | konkreter Plan + manuelle User-Bestätigung vor Übergabe |
| Shadow Mode | automatische Pläne generiert, aber nicht ausgeführt, Vergleich mit Realität |
| Autopilot | validierte Pläne automatisch an HEMS übergeben |

## Zusammenspiel

Der Betriebsmodus entscheidet, **ob/wie** ein Plan zu HEMS gelangt; der Steuermodus
entscheidet, **welche Werte** als fixiert vs. überschreibbar in die Planung eingehen.
Beispiel: Hybrid + Vorschlagen = User fixiert Min-SOC, KI plant darum, User bestätigt
den Plan, erst dann Übergabe.

## Aktueller Implementierungsstand

**Beide Achsen sind Stand jetzt nicht funktional verdrahtet.** Der tatsächliche
Ist-Zustand entspricht effektiv **Manuell + Beobachten**: EP schreibt
`sensor.ep_*_vorschlag`-Werte, die rein informativ sind — der User müsste sie selbst
per HA-Automation auswerten (D-032/D-033). Es existiert:

- **Kein** Code, der einen Steuermodus (Manuell/Hybrid/Automatisch) auswertet oder
  User-Fixierungen als harte Nebenbedingung in den Validator einspeist.
- **Kein** Per-Gerät-Steuermodus-Helfer.
- **Kein** automatischer Übergabeweg an HEMS jenseits der `sensor.ep_*_vorschlag`-Werte
  (die "Beobachtete Konformität" in `plan_feedback.py` vergleicht nur, ob HEMS zufällig
  mit dem Vorschlag übereinstimmt — sie bestätigt nichts und lenkt nichts).

Das ist laut [roadmap.md](roadmap.md) Teil von Meilenstein **M3** und größtenteils
offen. Vor jeder Implementierung hier: prüfen, ob die alten Entscheidungen D-009/D-020
(siehe [decisions-log.md](decisions-log.md)) noch die gewünschte Mechanik beschreiben,
und `user-beispiele/` auf aktuellere Vorgaben prüfen (hat immer Vorrang).
