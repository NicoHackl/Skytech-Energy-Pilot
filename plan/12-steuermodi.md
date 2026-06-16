# 12 — Steuermodi (User ↔ KI) & Betriebsmodi

Es gibt **zwei getrennte Achsen**. Nicht verwechseln.

## Achse 1 — Steuermodi (WER steuert) — verbindlich aus [../user-regeln.md](../user-regeln.md) §04
Langzeitziel (vollständig zu implementieren, siehe D-009):

| Modus | User | KI / EP |
|-------|------|---------|
| **Manuell** | steuert alles | steuert nichts |
| **Hybrid** | gibt gewisse Werte/Gerätestatus **fest** vor | darf diese Werte **nicht ändern** und **muss** mit ihnen weiterplanen |
| **Automatisch** | Eingaben werden ignoriert | KI/EP-Werte zählen, **Vorrang** vor User-Eingaben |

**Umsetzungskonsequenzen:**
- **Hybrid** ist der Kern: vom User fixierte Werte werden zu **zusätzlichen harten Vorgaben** für die Planung/Validierung (siehe [08](08-validierung-sicherheit.md)). Die KI plant um sie herum; ein Plan, der sie verletzt, ist ungültig.
- **Automatisch:** KI-Vorschlag setzt User-Eingabefelder außer Kraft (User-Werte bleiben Eingabe, werden aber nicht angewandt).
- **Manuell:** EP erstellt keine wirksamen Vorgaben (höchstens Anzeige/Beobachtung).
- Steuermodus wird als HA-Helfer (`input_select`, deutsch) und/oder Addon-Config geführt; der aktive Modus ist in Status-Entität + UI sichtbar.

### Geltungsbereich: global + pro Gerät (D-020)
- **Global = Hybrid** → zusätzlich **pro Gerät** verfeinerbar; jedes Gerät kann eigenständig Manuell/Hybrid/Automatisch sein.
- **Global = Manuell** **oder** **Automatisch** → gilt **für alle** Geräte; **kein** Per-Gerät-Override („alles oder nichts"). Per-Gerät-Auswahl ist dann in der UI deaktiviert/ignoriert.
- Datenmodell: ein globaler Steuermodus + optionaler Per-Gerät-Steuermodus, der **nur** bei global=Hybrid wirksam wird. Per-Gerät-Helfer kommen mit M3.

## Achse 2 — Betriebsmodi (WIE autonom an HEMS) — aus info.md §14
Einführungsreihenfolge / Reifegrad der Plan-Übergabe:
`Beobachten → Vorschlagen → Shadow Mode → Autopilot`
- **Beobachten:** nur Analyse, keine Pläne an HEMS.
- **Vorschlagen:** Plan + manuelle Bestätigung.
- **Shadow Mode:** automatische Pläne, nicht ausgeführt, Vergleich mit Realität.
- **Autopilot:** validierte Pläne automatisch an HEMS.

## Zusammenspiel der beiden Achsen
- Betriebsmodus bestimmt, **ob/wie** ein Plan HEMS erreicht; Steuermodus bestimmt, **welche Werte** in die Planung als fix/überschreibbar eingehen.
- Beispiel: *Hybrid + Vorschlagen* = User fixiert Mindest-SOC, KI plant darum, User bestätigt den Plan, erst dann Übergabe.
- **V1 (D-008):** faktisch *Manuell/Beobachten* mit **Vorschlagswerten** der KI (sichtbar in UI/Sensoren/Logs, keine Übernahme).

## Sicherheitsbezug
- Unabhängig vom Steuermodus bleiben **technische harte Grenzen** (info.md §7) und die HEMS-Doppelvalidierung immer aktiv. „Automatisch" hebt nur User-*Komfort*-Eingaben auf, niemals Sicherheitsgrenzen.

## Offene Punkte
- Genaues Mapping „welche Felder darf der User in Hybrid fixieren" (pro Gerät).
