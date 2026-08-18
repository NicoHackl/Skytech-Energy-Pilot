# D-067: HEMS-Planungsvertrag und interner Scheduler

## Status

Aktiv — 18.08.2026

## Kontext

Energy Pilot leitete Gerätefelder bislang aus Entity-Suffixen ab, betrachtete technische
Watt-Grenzen teilweise wie Messquellen und war für regelmäßige Planung von einer externen
HA-Automation abhängig. Freie KI-Begründungen konnten dadurch dem HEMS-Regelprinzip
widersprechen, insbesondere mit Netzbezug als Abschaltgrund oder unbelegten Temperatur- und
Solarthermieaussagen.

## Entscheidung

HEMS bleibt Quelle der Wahrheit für Geräte, Userinputs, technische Grenzen und Regelprinzip.
Sein Schema liefert additive, stabile Metadaten; EP liest den vollständigen Vertrag, gibt aber
nur planungsrelevante Werte an die KI. Tatsächliche Leistung beziehungsweise Schaltzeit ×
Nennleistung sind die einzigen automatisch abgeleiteten elektrischen Energiequellen.

Die Wärmeableitung heißt „nicht-elektrische thermische Nettobilanz". Ohne belegten elektrischen
Eintrag bleibt sie unbekannt. Ein Solarthermie-Proxy kombiniert bereinigten Rückblick,
PV-Rückblick/-Prognose und Wetter und trägt stets eine Datenqualitätsstufe.
Aus dem bereinigten Wärmeverlust, dem Proxy-Eintrag und der aktuellen Reserve entsteht zusätzlich
die erwartete Komfortreserve am Ende des Planungshorizonts. Diese Bilanz — nicht die bloße
Temperatur oder die Lücke zur Zieltemperatur — entscheidet über Heizstabfreigabe oder -sperre.

Ein EP-interner Scheduler läuft erst nach HEMS-Discovery und erstem Messsnapshot und danach im
konfigurierten Planungstakt. Planner-Läufe sind serialisiert. EP schreibt zuerst alle
Vorschlagssensoren und zuletzt `sensor.ep_plan_commit`; HEMS akzeptiert nur zum Commit passende,
noch gültige Vorschläge und fällt sonst feldweise auf Nutzerwerte zurück. Grenzwerte sind
read-only. Ein semantischer Validator blockiert Begründungen, die diese Fakten verletzen.

## Folgen

- Keine neue direkte HA-Sensorzuordnung ist für diese Ausbaustufe nötig.
- Ein Add-on-Neustart verliert keinen noch gültigen Plan; EP veröffentlicht ihn erneut.
- Ein teilweise geschriebener oder abgelaufener Plan kann HEMS nicht mehr beeinflussen.
- Solarthermie bleibt ohne direkten Kollektor-/Pumpensensor eine gekennzeichnete Schätzung.
- HEMS-Modi werden nicht automatisch umgeschaltet; Shadow-Betrieb und spätere Freigabe bleiben
  eine bewusste Betriebsentscheidung.
