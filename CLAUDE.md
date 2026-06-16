# CLAUDE.md — Skytech Energy Pilot

> Kompakte Arbeitsgrundlage für mich (Claude). Vollständige Spezifikation: [info.md](info.md).
> Regeln in [user-regeln.md](user-regeln.md) haben **immer Vorrang** vor [info.md](info.md).

## Was ist das Projekt?
Skytech **Energy Pilot (EP)** = eigenständiges Home-Assistant-Addon. KI-gestützte, **vorausschauende strategische** Energieplanung (Horizont 24–48 h). EP plant, **HEMS regelt**. EP steuert **niemals** Geräte direkt.

- **HEMS** (Basis, Pflicht) = lokale Echtzeitregelung (1–2 s), PV-Überschussverteilung. Repo: https://github.com/NicoHackl/SkytechHEMS
- **EP** (optionale KI-Erweiterung) = Planung alle 15–60 min, liefert Rahmenvorgaben.
- Beide müssen zusammenarbeiten. EP ohne HEMS sinnlos; HEMS ohne EP voll funktionsfähig.

## Eiserne Regeln (nicht verhandelbar)
1. **Git:** committen/pushen **nur** in Branch `claude/main` — **auch im HEMS-Repo** (D-022). CI-Tests laufen nur auf `claude/main` (D-024).
2. **Sprache Code:** Variablen/Funktionen/Klassen **Englisch**, Kommentare **Deutsch**.
3. **Sprache HA-Entitäten/Helfer:** **Deutsch**.
4. **EP-Entitäten-Namensschema:** `<DOMAIN>.ep_<GERÄTENAME>_<PREFIX>_<SUFFIX>`
   - Vorschlagswerte von EP → Suffix `vorschlag`, als `sensor.` bereitgestellt.
   - Allgemeine Infos → Suffix `allgemeine_informationen` (als Sensor-**Attribute**, initial nicht nötig).
   - (HEMS-Pendant zum Vergleich: `<domain>.ems_<prefix>_<suffix>`.)
5. **KI = Orchestrator, kein Regler.** Freitext nie als Steuerbefehl. Nur Tool/Function-Calling mit strukturierten Ein-/Ausgaben.
6. **Sicherheit:** Jeder Plan wird **lokal** gegen JSON-Schema + harte Grenzen validiert, hat Ablaufzeit, vollständiges Audit-Log. Harte Grenzen nie durch KI änderbar. Kein API-Key in Logs/Entitäten. Kein von KI erzeugter Code wird ausgeführt.
7. **Datenminimum:** Nur nötige, verdichtete Daten an externe KI. Niemals die ganze HA-DB.
8. **Fallback:** Bei Cloud-/KI-Ausfall blockiert EP **nie** die Anlage; HEMS läuft lokal weiter.

## Steuermodi (user-regeln §04) — Langzeitziel, vollständig umzusetzen
Eigene Achse, getrennt von den Betriebsmodi (Beobachten→Vorschlagen→Shadow→Autopilot). Details: [plan/12-steuermodi.md](plan/12-steuermodi.md).
- **Manuell:** User steuert alles, KI nichts.
- **Hybrid:** User fixiert Werte → für KI **harte Vorgaben**, KI plant darum herum (darf sie nie ändern).
- **Automatisch:** KI/EP-Werte haben **Vorrang** vor User-Eingaben.
- **Geltung (D-020):** global=Hybrid → zusätzlich pro Gerät verfeinerbar; global=Manuell/Automatisch → gilt für alle (kein Per-Gerät-Override).
- Technische harte Grenzen + HEMS-Doppelvalidierung bleiben in allen Modi aktiv.

## Getroffene Entscheidungen (Quelle: plan/entscheidungen.md)
- **Sensorwerte:** Live übergeben; EP mittelt selbst über **1 / 15 / 60 min** parallel (keine Ereigniskopplung über Mittel). Gemittelt: Leistungs-/Flussgrößen. Letztwert: SOC, Temperaturen, Zeiten, Zustände. Langzeitprognose nutzt nur 60-min.
- **HEMS-Anbindung:** V1 nur über HA-Helfer/`/api/set`; später versionierte Plan-API **im HEMS-Repo** (dort darf ich dann auch committen, paralleles lokales Arbeiten wird eingerichtet).
- **KI-Provider:** Start **Google Gemini**, Default-Modell **`gemini-3.5-flash`** (Free, ~10 req/min → drosseln). Provider/Modell **in Addon-Config** umschaltbar. Keys nie in Logs/Entitäten.
- **V1-Verhalten:** KI liefert nur **Vorschlagswerte** (UI/Sensoren/Logs), keine Übernahme.
- **HA-Helfer:** werden **nicht** automatisch angelegt. Ich liefere fertige `<domain>_ep.yaml` in [claude-ha-config-dateien/](claude-ha-config-dateien/) (Vorlage: [user-beispiele/](user-beispiele/)).
- **Naming wie HEMS**, prefix/suffix dürfen verschwimmen. Beispiele: `sensor.ep_batterie_1_ziel_soc`, `sensor.ep_heizstab_freigabe`, `input_number.ep_speicher_soc_mindestwert_1`.
- **Prognose/Preis:** bestehende HA-Sensoren, Entitätsnamen in Addon-Config gepflegt.
- **Zielgewichtung:** in Addon-Config pflegbar, initial aus info.md §7.
- **Logging:** Auto-Export eines KI-lesbaren Bundles bei ERROR/CRITICAL.
- **CI:** muss u.a. HEMS↔EP-Zusammenspiel testen; Start-Coverage 60 %.
- **Leitprinzip Konfigurierbarkeit:** so gut wie **alles** in der Addon-Config einstellbar (Mindestkonfidenz 70 %, Delta-Limit ±20 %/±10 %, Provider/Modell, Intervalle, Gewichte, Sensor-Mappings …) — Defaults von mir, aber überschreibbar.
- **Externer Zugriff:** Start über HA **Long-Lived Token** (Backend schreibt HA-Helfer), eigener EP-Endpunkt evtl. später.

## ⚠️ Externer Zugriff im Hinterkopf behalten (D-013)
User will aus dem internen Netz über ein **iOS-Backend (Java auf Linux-Server)** bestimmte Daten **lesen/setzen** (z.B. **E-Auto-Abfahrtszeit** für Mindestladung). Architektur so wählen, dass externer Schreibzugriff (bevorzugt über HA-Helfer, ggf. später EP-API) sauber möglich ist.

## Tech-Stack (an HEMS angelehnt, bewusst kompatibel)
- Python 3.11, **aiohttp** Webserver, Ingress-Panel, SQLite. HA-Zugriff via `SUPERVISOR_TOKEN` (REST + WebSocket).
- Frontend: SPA (vanilla JS/CSS) wie HEMS, oder leichtes Framework — Entscheidung offen (siehe claude-fragen).

## EP ↔ HEMS Schnittstelle
- Primär: **versionierte interne REST-API** (`/api/v1/...`), unabhängig von einzelnen HA-Helfern.
- Zusätzlich: Vorschlagswerte als HA-`sensor.`-Entitäten (Suffix `vorschlag`).
- HEMS bietet bereits `/api/status`, `/api/controls`, `/api/set`, `/api/device_controls_schema` + post-cycle-script.

## Daten von HA → EP
- Grenzwerte/Geräteinfos: über HA-(Helfer-)Entitäten nach Namensschema; **Fallback in Addon-UI** konfigurierbar.
- Fremddaten (Strompreis EPEX, PV, Wetter): freie Entitätsnamen, in Addon-Config pflegbar (kein Namensschema, da Drittanbieter).

## Anfangs-Geräte (Phase 1) — präzisiert (D-016/D-017/D-018)
- **Batterie (E3DC):** immer Prio 1, immer freigegeben; **kein** SOC-Limit, **keine** Entladung (nur PV-Überschuss); nur **max. Ladeleistung** relevant.
- **Heizstab:** max. Leistung + max. Wassertemperatur, Freigabe.
- **Heizlüfter 1 & 2:** feste **1500 W** (binär) → nur Freigabe.
- **Strompreis/Wetter:** in V1 **raus** (kein dyn. Tarif). **PV-Prognose:** mehrere Sensoren pro Typ (Ausrichtungen, EP summiert), Werte: Energie akt. Stunde / nächste Stunde / verbleibend heute / morgen — **je im Sensor-State, kein Attribut**.
- **Später:** Wallbox/E-Auto, Wärmepumpe, dynamische Tarife.

## Betriebsmodi (Einführungsreihenfolge)
Beobachten → Vorschlagen → Shadow Mode → Autopilot.

## Querschnitt (von Anfang an)
- **Tests:** umfangreiche automatische CI-Tests von Beginn an.
- **Logging:** umfangreich, in EP-UI einsehbar, **maschinenlesbarer Export** (JSON) für KI-Fehleranalyse.

## Projektstruktur dieser Doku
- [info.md](info.md) — vollständige Spezifikation.
- [user-regeln.md](user-regeln.md) — verbindliche Regeln (Vorrang).
- [user-fragen.md](user-fragen.md) — Fragen des Users + meine Antworten.
- [plan/](plan/) — Aufteilung in Themenblöcke (HA, Backend, API, KI, Steuermodi …).
- [plan/entscheidungen.md](plan/entscheidungen.md) — **Decision Log**: alle beantworteten Design-Entscheidungen (Quelle der Wahrheit fürs „warum").
- [plan/roadmap.md](plan/roadmap.md) — Meilensteine.
- [claude-fragen/](claude-fragen/) — versionierte offene Fragen von mir an den User (beantwortete → entscheidungen.md).
- [claude-ha-config-dateien/](claude-ha-config-dateien/) — fertige `<domain>_ep.yaml` HA-Helfer-Pakete für den User.
- [user-beispiele/](user-beispiele/) — Vorlagen des Users (z.B. Helfer-YAML-Format).

## Arbeitsweise
- Vor Implementierung relevanten plan/-Block lesen. Offene Punkte in claude-fragen/ ergänzen statt raten.
- Doku kompakt halten; bei Widersprüchen user-regeln.md > info.md.
