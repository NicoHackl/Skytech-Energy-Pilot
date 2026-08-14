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

**Wirkung in EP:** ausschließlich das Gate für den Original-Schreibweg (D-052). Nur bei Quelle
`ep` schreibt EP einen KI-Vorschlag per HA-Service in die Original-Entität; bei `user`/`aus`
bleibt der Nutzerwert stehen und der Vorgang erscheint als `skipped` in Ergebnis/Audit/UI. Die
`sensor.ep_*_vorschlag`-Spiegelsensoren sind davon **nicht** betroffen — sie werden immer
geschrieben, der Vorschlag bleibt also auch im manuellen Modus sichtbar.

Bewusst **nicht** nachgebaut: `ems_pv_regelung_aktiv`, `hard_lockout` und das
`allowed_modes`-Typ-Gate des HEMS. Zusatz-Entitäten sind advisorisch und nicht HEMS-relevant
(D-047), `hard_lockout` ist ein PV-Notabwurf statt einer Nutzeraussage über die KI-Übernahme,
und `allowed_modes` steht in der HEMS-Addon-Config, die EP nicht kennt.

## Aktueller Implementierungsstand

**Die drei EP-Steuermodi (Manuell/Hybrid/Automatisch, D-009/D-020) sind weiterhin nicht
verdrahtet**; verdrahtet ist nur die HEMS-Modus-Achse oben. Der Ist-Zustand entspricht
ansonsten weiter **Beobachten**: EP schreibt `sensor.ep_*_vorschlag`-Werte, die der User selbst
per HA-Automation auswerten müsste (D-032/D-033). Es existiert:

- **Kein** Code, der User-Fixierungen als harte Nebenbedingung in den Validator einspeist
  (Hybrid ist der Kernfall und fehlt vollständig).
- **Kein** eigener EP-Steuermodus-Helfer — die Modus-Achse kommt komplett aus dem HEMS.
- **Kein** automatischer Übergabeweg an HEMS jenseits der `sensor.ep_*_vorschlag`-Werte
  (die "Beobachtete Konformität" in `plan_feedback.py` vergleicht nur, ob HEMS zufällig
  mit dem Vorschlag übereinstimmt — sie bestätigt nichts und lenkt nichts).

Das ist laut [roadmap.md](roadmap.md) Teil von Meilenstein **M3** und größtenteils
offen. Vor jeder Implementierung hier: prüfen, ob die alten Entscheidungen D-009/D-020
(siehe [design-entscheidungen.md](design-entscheidungen.md)) noch die gewünschte Mechanik beschreiben,
und `user-beispiele/` auf aktuellere Vorgaben prüfen (hat immer Vorrang). Insbesondere offen:
wie sich das dreiwertige EP-Vokabular (Manuell/Hybrid/Automatisch) zum dreiwertigen
HEMS-Vokabular (`auto`/`manuell`/`aus`) verhalten soll — beide dritten Werte decken sich nicht.
