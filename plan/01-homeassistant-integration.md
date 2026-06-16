# 01 — Home-Assistant-Integration

## Zweck
EP läuft als eigenständiges HA-Addon mit Ingress-UI. Es liest freigegebene HA-Zustände (REST + WebSocket), stellt eigene Entitäten bereit und ist über die Addon-Config konfigurierbar.

## Addon-Grundlagen (an HEMS angelehnt)
- Container `skytech-energy-pilot`, Addon-Slug `skytech_energy_pilot`.
- Authentifizierung gegen HA-Core via automatisch bereitgestelltem `SUPERVISOR_TOKEN`.
- Ingress-Panel in der HA-Seitenleiste (Label „Energy Pilot").
- HA-Zugriff: REST-API für States/Services, **WebSocket-API** für fortlaufende Zustandsänderungen (Push).

## Namensschema EP-Entitäten
```
<DOMAIN>.ep_<GERÄTENAME>_<PREFIX>_<SUFFIX>
```
- Alle HA-Namen (Entitäten/Helfer) auf **Deutsch**.
- **Vorschlagswerte von EP:** Suffix `vorschlag`, bereitgestellt als `sensor.`-Entität (zusätzlich über versionierte API, siehe [03](03-api-schnittstelle-hems.md)).
- **Allgemeine Informationen:** Suffix `allgemeine_informationen`. Inhalte als **Attribute** am Sensor (Erweiterbarkeit; initial nicht zwingend nötig).
- Vergleich HEMS: dort `<domain>.ems_<prefix>_<suffix>` — bewusst paralleles Schema.

> **Entschieden (D-004):** Naming analog HEMS; `<PREFIX>`/`<SUFFIX>` dürfen ineinander übergehen. Reale Beispiele vom User:
> `sensor.ep_batterie_1_ziel_soc`, `sensor.ep_heizstab_freigabe`, `input_number.ep_speicher_soc_mindestwert_1`.

## Datenfluss HA-Host → EP
1. **Grenzwerte & allgemeine Geräteinformationen** werden über HA-(Helfer-)Entitäten nach Namensschema bereitgestellt.
2. **Fallback:** In der Addon-Oberfläche konfigurierbar — falls nach Namensschema keine Entität gefunden wird, kann ein fester Wert oder eine alternative Entität hinterlegt werden.
3. **Fremddaten** (kein eigenes Namensschema, da Drittanbieter-Integrationen): Entitätsnamen frei und in der Addon-Config-Seite pflegbar:
   - Strompreis (z.B. EPEX/Tibber/Awattar)
   - PV-Daten / PV-Prognose
   - Wetter
   Für diese Sensoren trägt der User in der Config den HA-Entitätsnamen ein, der die Information enthält.

## Datenfluss EP → HA / HEMS
- **Vorschlagswerte** über `sensor.`-Entitäten (Suffix `vorschlag`) **und** über die versionierte API (siehe [03](03-api-schnittstelle-hems.md)).
- Status-/Diagnose-Entitäten (siehe info.md §15): Status, aktuelle Strategie, aktiver Plan, Gültigkeit, nächste Planung, Konfidenz, Provider/Modell, erwartete PV/Netz/Kosten, letzter Fehler.
- Schalter/Select/Number für Steuerung (enabled, automatic_planning, mode, strategy, provider, Intervalle, Mindestkonfidenz).
- Actions (HA-Services): create_plan, simulate_plan, submit_plan, cancel_plan, recalculate_forecast, reset_learning_data.

## Anlegen der HA-Helfer (D-005)
- EP legt Helfer **nicht** automatisch an. Ich liefere fertige YAML-Pakete `<domain>_ep.yaml` in [../claude-ha-config-dateien/](../claude-ha-config-dateien/), die der User je Domain in seine HA-Config einfügt. Der User kuratiert diese Dateien mit (Stand: Kommentare/Anpassungen eingearbeitet).
- Vorlage/Format: [../user-beispiele/beispiel-config-yam.txt](../user-beispiele/beispiel-config-yam.txt).
- Für jede benötigte Helfer-Domäne (input_number, input_boolean, input_select, input_datetime) eine eigene Datei.

### Phase-1-Gerätemodell (präzisiert, D-016/D-017/D-018)
- **Batterie (E3DC):** immer Prio 1, immer freigegeben → nur `input_number.ep_batterie_ladeleistung_maximal`. Kein SOC-Helfer, keine Entladung, keine Freigabe.
- **Heizstab:** max. Leistung + max. Wassertemperatur (`input_number`), Freigabe (`input_boolean`).
- **Heizlüfter 1 & 2:** feste 1500 W → nur Freigabe (`input_boolean`), kein Leistungs-Helfer.
- **Steuerung/Planung:** globaler Steuermodus + Betriebsmodus + Strategie (`input_select`), EP-Schalter (`input_boolean`), Planungsparameter (`input_number`). Per-Gerät-Steuermodus-Helfer kommen mit M3 (D-020).
- **input_datetime** (E-Auto-Abfahrtszeit): erst spätere Ausbaustufe, auch Schreibpunkt für externes Backend (D-013/D-023).

## Prognose-/Preisdaten (D-006)
- PV-Prognose und Strompreis kommen über **bestehende HA-Sensoren** des Users; deren Entitätsnamen werden in der **Addon-Config** hinterlegt (kein Namensschema). Siehe [06](06-prognosen.md).

## Entity Allowlist
- EP liest **nur** explizit konfigurierte/freigegebene Entitäten (Sicherheitsprinzip, info.md §6.1, §13).
- Allowlist in Config + DB; jede gelesene Entität ist nachvollziehbar.

## Konfigurierbare Einlesegrößen (Auswahl)
PV-Leistung, Hausverbrauch, Netzpunktleistung, Netzbezug/-einspeisung, Batterieleistung, Batterie-SOC, max. Lade-/Entladeleistung, Verbraucherzustände, Soll-/Ist-Leistungen, Warmwassertemperatur, Wallbox/Fahrzeugstatus (später).

## Offene Punkte
- Vollständiger, vom User bestätigter Satz an Phase-1-Helfern (mein Vorschlag liegt in [../claude-ha-config-dateien/](../claude-ha-config-dateien/)).
- Setzt der externe iOS/Java-Backend-Schreibzugriff (D-013) bestimmte Helfer voraus (z.B. `input_datetime` Abfahrtszeit)? → siehe [../claude-fragen/](../claude-fragen/).
