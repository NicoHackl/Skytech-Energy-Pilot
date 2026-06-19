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
- **Domänen-Trennung nach Datenrichtung (D-029):** vom **User gepflegte technische Gerätewerte → `ems_*`** (HEMS-Domäne, EP **liest** nur); **EP-Vorschlagswerte → `ep_*`** (EP **schreibt**). Vollständiges Read-/Write-Schema + Zugriffsmatrix: [../user-beispiele/variablen-zugriff.md](../user-beispiele/variablen-zugriff.md).
- **Vorschlagswerte von EP:** Suffix `…_vorschlag`, bereitgestellt als `sensor.`-Entität (später zusätzlich 1:1 über HEMS-API, D-032). **Schreibvertrag Phase 1 (D-030/D-034):** `prio_vorschlag` + `freigabe_vorschlag` (**binär und regelbar**), `geschutzte_mindestleistung_w_vorschlag`/`_a_vorschlag` (regelbar + Batterie, D-037). Gerätespezifisch: `ep_heizstab_max_temperatur_vorschlag` (D-035).
- **Allgemeine Informationen:** Suffix `allgemeine_informationen`. Inhalte als **Attribute** am Sensor (Erweiterbarkeit; initial nicht zwingend nötig).

> **Entschieden (D-004/D-029):** Naming analog HEMS; `<PREFIX>`/`<SUFFIX>` dürfen ineinander übergehen. Reale Beispiele:
> EP liest `ems_heizstab_technische_freigabe`, `ems_heizlüfter_1_leistung_w`, `ems_heizstab_max_technisch_w`; EP schreibt `sensor.ep_heizstab_prio_vorschlag`, `sensor.ep_heizlüfter_1_freigabe_vorschlag`. (Frühere `ep_…_ziel_soc`-Beispiele überholt, D-030.)

## Datenfluss HA-Host → EP
1. **Grenzwerte & allgemeine Geräteinformationen** werden über HA-(Helfer-)Entitäten nach Namensschema bereitgestellt.
2. **Fallback:** In der **Addon-Konfiguration** pflegbar (Optionen `fallback_<rolle>`) — falls keine gültige Entität gefunden wird, greift der feste Wert (D-027).
3. **Mess-/Zustandsgrößen-Zuordnung** (PV-Leistung, Hausverbrauch, SOC, …): erfolgt über Addon-Optionen `entity_<rolle>` (D-027), **nicht** in der Addon-Oberfläche. Die UI zeigt die Zuordnung nur lesend.
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

### Phase-1-Gerätemodell (präzisiert, D-016/D-017/D-018; Domäne D-029/D-031)
> Geräte-Grenzwerte/Freigaben/Ist-Leistung sind **`ems_*`** (HEMS-Domäne), EP **liest** sie nur — **nicht** von EP als Helfer geliefert (D-029). **Die `ems_*`-Helfer sind im HEMS definiert (D-036)** und werden dort dynamisch pro Gerät aus `entity_prefix`/`class`/`output_unit` erzeugt; EP ermittelt die konkreten Entity-IDs zur Laufzeit über `GET /api/device_controls_schema` (siehe [03](03-api-schnittstelle-hems.md)).
- **Batterie (E3DC):** immer Prio 1, immer freigegeben → relevanter Grenzwert nur max. Ladeleistung (`ems_batterie_max_technisch_w`). Kein SOC-Helfer, keine Entladung, keine Freigabe. EP schreibt nur `sensor.ep_batterie_geschutzte_mindestleistung_w_vorschlag` (D-037).
- **Heizstab (regelbar):** `ems_heizstab_technische_freigabe`, `ems_heizstab_min_technisch_w`/`max_technisch_w` (alle `ems_*`, EP liest). **Max. Wassertemperatur (D-035):** nicht HEMS-relevant → EP liest den Grenzwert `input_number.ep_heizstab_max_temperatur` (**Helfer**, von mir geliefert, da user-gepflegt) und schreibt `sensor.ep_heizstab_max_temperatur_vorschlag` (**EP-Sensor**, kein Helfer — alle `ep_*_vorschlag` sind Sensoren, D-030).
- **Heizlüfter 1 & 2 (binär, feste 1500 W):** `ems_<name>_leistung_w` (Ist-Leistung, D-031) + `ems_<name>_technische_freigabe`. EP liest beides.
- **EP-eigene Helfer (`ep_*`, von mir geliefert):** globaler Steuermodus + Betriebsmodus + Strategie (`input_select`), EP-Schalter (`input_boolean`), Planungsparameter (`input_number`). Per-Gerät-Steuermodus-Helfer kommen mit M3 (D-020).
- **input_datetime** (E-Auto-Abfahrtszeit): erst spätere Ausbaustufe, auch Schreibpunkt für externes Backend (D-013/D-023).

## Prognose-/Preisdaten (D-006)
- PV-Prognose und Strompreis kommen über **bestehende HA-Sensoren** des Users; deren Entitätsnamen werden in der **Addon-Config** hinterlegt (kein Namensschema). Siehe [06](06-prognosen.md).

## Entity Allowlist (D-038)
- EP liest **nur** explizit konfigurierte/freigegebene Entitäten (Sicherheitsprinzip, info.md §6.1, §13).
- Register leitet sich vollständig aus den drei Config-Quellen ab (Messgrößen-Rollen, Geräte-`ems_*`, PV-Prognose) — keine separate Pflege.
- **Soft durchgesetzt:** ein Read außerhalb der Allowlist wird protokolliert/auditiert (`audit.action='allowlist_violation'`), aber **nicht blockiert** (Fehlkonfiguration darf den Betrieb nie stören).
- Allowlist in Config + DB (Tabelle `allowlist`); jede gelesene Entität ist nachvollziehbar. Transparenz: `GET /api/allowlist` + Status-Tab. Modul `allowlist.py`, Guard in `ha_client.py`.

## Konfigurierbare Einlesegrößen (Auswahl)
PV-Leistung, Hausverbrauch, Netzpunktleistung, Netzbezug/-einspeisung, Batterieleistung, Batterie-SOC, max. Lade-/Entladeleistung, Verbraucherzustände, Soll-/Ist-Leistungen, Warmwassertemperatur, Wallbox/Fahrzeugstatus (später).

## Offene Punkte
- Vollständiger, vom User bestätigter Satz an Phase-1-Helfern (mein Vorschlag liegt in [../claude-ha-config-dateien/](../claude-ha-config-dateien/)).
- Setzt der externe iOS/Java-Backend-Schreibzugriff (D-013) bestimmte Helfer voraus (z.B. `input_datetime` Abfahrtszeit)? → siehe [../claude-fragen/](../claude-fragen/).
