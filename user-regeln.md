# Allgemein
Als Referenz für allgemeine Themen kann das Github Projekt Skytech HEMS verwendet werden
Es ist außerdem Esenziell wichtig das die beiden HA Addon´s zusammenarbeiten können, HEMS ist die Basis und der Energy Pilot ist die (optionale) KI Erweiterung
---
https://github.com/NicoHackl/SkytechHEMS
---

EP = (Skytech) Energy Pilot
HA = Homeassistant
(H)EMS = (Home) Energy Management System

# 02 Code
---
Code Variablen / Funktionen / Klassen etc. sind auf Englisch zu benennen
Kommentare sind auf Deutsch zu verfassen

**Tests**
Baue von Anfang an umfangreiche und sinnvolle automatische CI-Tests mit ein

**Logging**
- Baue von Anfang an ein umfangreiches, übersichtliches und von der EP-Addon Oberfläche aus einsehbares Logging ein
- Inkl. Möglichkeit die Logging Daten in einem Maschinenlesbaren format zu exportieren das eine KI/LLM (ChatGPT, Claude) diese Analysieren kann und daraus fehler finden und beheben kann

# 03 Homeassistant
---
## Entitäten und Helfer
**Allgemein**
Alle Name in Homeassistant (Enitäten/Helfer) sind auf deutsch zu benennen
**Nameschema**
<DOMAIN>.ep_<GERÄTENAME>_<PREFIX>_<SUFFIX>

---
**Suffix:**
Geräte Vorschlagswerte von EP: vorschlag
    Diese Entitäten sollen als "sensor." Entität in HA zu verfügung gestellt werden

Allgemeine Informationen: allgemeine_informationen


---
**Daten von HA Host -> EP**
Gernzwerte, allgemeine Geräteinformation, werden über HA-(Helfer) Entitäten bereit gestellt
Es soll aber ein Fallback in der Addon Oberfläche konfigurierbar sein, falls, nach Namenschema, keine Entiät gefunden wird
- Geräte Daten/Information

Sollen in der Addon Config Seite pflegbar sein, also das man da den HA Entiätsnamen Eintragen kann der die Information enthält, für die Sensoren gibt es dann kein Namenschema sonder sind frei wählbar, da drittanbieter Integrationen sich ja nicht an unser Namenschema halten z.b. EPEX Strompreis
- Strompreis
- PV Daten


**Vorschlagswerte von EP für HEMS**
Vorschlagswerte werden über sensor Entitäten an HA übermittelt und sollen auch über die versionierte API übermittelt werden

**Allgemeine Informationen**
Dieser Sensor enthält dann allgmeien Informationen (wird initial nicht benötigt) die für erweiterbarkeit verwendet werden kann
Informationen in diesem Sensor werden als Attribut an den Sensor übermittelt

