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

## Die HEMS-Modus-Achse (implementiert, D-057)

**Nicht mit den drei EP-Steuermodi oben verwechseln.** Das HEMS führt eine eigene, bereits
produktive Modus-Achse mit eigenem Vokabular, die EP seit D-057 mitliest und respektiert:

| Wert | Bedeutung |
|---|---|
| `auto` | KI/EP — der EP-Vorschlag wird übernommen |
| `manuell` | normale Regeln — der vom User gepflegte Wert gilt |
| `aus` | Gerät nimmt nicht teil |

Helfer (HEMS-Domäne, EP **liest** nur, D-029): global `input_select.ems_regelmodus`, je Gerät
`input_select.ems_<prefix>_modus`. EP legt sie **nicht** an — ohne den globalen Helfer regelt
schon das HEMS nicht.

**Auflösung** (`control_mode.resolve_source`, portiert aus HEMS `Device.resolve_source`) — die
Reihenfolge ist bedeutungstragend, die Asymmetrie beabsichtigt:

1. global `aus` (oder Helfer fehlt/nicht lesbar) → Quelle `aus`
2. Gerät `aus` → `aus` (**gilt immer**, auch gegen global `auto`)
3. global `auto` → `ep` (**überstimmt** ein Gerät auf `manuell`; ein Gerät kann sich nur mit
   `aus` entziehen)
4. Gerät `auto` → `ep` (bei global `manuell`/`nur_*` entscheidet das Gerät)
5. sonst → `user`

**Wirkung:** EP veröffentlicht seine Vorschlagssensoren unabhängig vom Modus. HEMS liest sie bei
Quelle `ep`, aber nur mit passendem, gültigem `sensor.ep_plan_commit`; sonst greift feldweise der
Nutzerwert. Der optionale EP-Schreibweg in zusätzliche Original-Helfer bleibt bei `user`/`aus`
gesperrt und erscheint als `skipped` in Ergebnis/Audit/UI.

Bewusst **nicht** nachgebaut: `ems_pv_regelung_aktiv` und `hard_lockout`. HEMS bleibt die
autoritative Laufzeit-Sicherheit. `allowed_modes` kennt EP seit D-067 aus dem Vertrag als
Planungsinformation, die tatsächliche Durchsetzung bleibt aber im HEMS.

## Aktueller Implementierungsstand

Verdrahtet ist die HEMS-Modus-Achse oben. Im manuellen HEMS-Modus bleibt EP im Shadow-Betrieb;
eine HA-Automation zur Übertragung ist seit Commit-Vertrag D-067 nicht mehr nötig. Es existiert:

- **Kein** Code, der User-Fixierungen als harte Nebenbedingung in den Validator einspeist
  (Hybrid ist der Kernfall und fehlt vollständig).
- **Kein** eigener EP-Steuermodus-Helfer — die Modus-Achse kommt komplett aus dem HEMS.
- **Kein** automatisches Umschalten der HEMS-Modi. Die Übernahme eines Geräts in `auto` bleibt
  eine bewusste Entscheidung nach dem Shadow-Betrieb.

Das ist laut [roadmap.md](roadmap.md) Teil von Meilenstein **M3** und größtenteils
offen. Vor jeder Implementierung hier: prüfen, ob die alten Entscheidungen D-009/D-020
(siehe [design-entscheidungen.md](design-entscheidungen.md)) noch die gewünschte Mechanik beschreiben,
und `user-beispiele/` auf aktuellere Vorgaben prüfen (hat immer Vorrang). Insbesondere offen:
wie sich das dreiwertige EP-Vokabular (Manuell/Hybrid/Automatisch) zum dreiwertigen
HEMS-Vokabular (`auto`/`manuell`/`aus`) verhalten soll — beide dritten Werte decken sich nicht.
