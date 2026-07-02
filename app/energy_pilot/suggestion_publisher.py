"""Veröffentlichung der KI-Vorschlagswerte als HA-`sensor.ep_*`-Entitäten (M2-Schreibweg).

V1-Schreibweg (user-beispiele/variablen-zugriff.md §„Schreibweg — gestaffelt"): die
validierten Vorschlagswerte eines Plans werden **ausschließlich** als HA-Entitäten
geschrieben — reine Anzeige/Vorschläge, **keine** Steuerung und (noch) **keine** Übergabe
an HEMS (das ist M3). Der Schreibvertrag je Gerät stammt aus
`plan_schema.suggestion_keys` (D-030/D-034/D-037/D-035); hier werden nur die im Plan
tatsächlich gesetzten Felder geschrieben.

Trennung: `build_suggestion_entities()` ist rein (testbar, ohne IO); `publish_suggestions()`
schreibt über den HA-Client und fängt Fehler je Entität ab — die App blockiert nie
(Iron Rule 8).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from energy_pilot.logging_setup import log
from energy_pilot.plan_schema import SUGGESTION_FIELDS

if TYPE_CHECKING:
    from energy_pilot.devices import Device
    from energy_pilot.ha_client import HAClient

# Anzeigename je festem Vorschlagsfeld (Watt/Ampere teilen sich den Begriff, Einheit unten).
# Zusatz-Vorschläge (D-047) tragen Label/Einheit aus der jeweiligen Zusatz-Entität (Device.extras).
_FIELD_LABEL: dict[str, str] = {
    "prio_vorschlag": "Priorität",
    "freigabe_vorschlag": "Freigabe",
    "geschutzte_mindestleistung_w_vorschlag": "Geschützte Mindestleistung",
    "geschutzte_mindestleistung_a_vorschlag": "Geschützte Mindestleistung",
}

# Einheit (HA `unit_of_measurement`) je Feld; Prio/Freigabe sind einheitenlos.
_FIELD_UNIT: dict[str, str] = {
    "geschutzte_mindestleistung_w_vorschlag": "W",
    "geschutzte_mindestleistung_a_vorschlag": "A",
}


@dataclass
class SuggestionEntity:
    """Eine zu schreibende HA-Entität samt Zustand und Attributen."""

    entity_id: str
    state: str
    attributes: dict
    device: str
    field_name: str


@dataclass
class PublishResult:
    """Ergebnis eines Schreibvorgangs für Endpoint/UI/Audit."""

    ok: bool
    written: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "written": self.written,
            "failed": self.failed,
            "reason": self.reason,
        }


def _format_state(value: object) -> str:
    """Serialisiert einen Vorschlagswert als HA-Sensorzustand (String).

    Booleans → `on`/`off` (HA-idiomatisch, in Automationen via `is_state(..., 'on')`
    abfragbar); ganzzahlige Floats ohne Nachkommastelle (800.0 → „800").
    """
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def build_suggestion_entities(plan: dict, devices: list[Device]) -> list[SuggestionEntity]:
    """Leitet aus einem validierten Plan die zu schreibenden HA-Entitäten ab.

    Feste Felder: `sensor.ep_<entity_prefix>_<feld>` (das Feld endet auf `_vorschlag`).
    Zusatz-Vorschläge (D-047): `sensor.ep_<obj>_vorschlag` gemäß dem Namensschema der
    Zusatz-Entität (`DeviceExtra.suggestion_entity_id`), mit deren Label/Einheit. Diese
    Werte sind advisorisch (nur HA-Sensor, nie an das HEMS übergeben). `entity_prefix`/`label`
    stammen aus dem `Device`; fehlt das Gerät, dient der Name als Fallback-Prefix.
    """
    by_name = {device.name: device for device in devices}
    plan_id = plan.get("plan_id")
    valid_until = plan.get("valid_until")

    def _attrs(friendly: str, unit: str | None) -> dict:
        attributes: dict = {
            "friendly_name": friendly,
            "source": "Skytech Energy Pilot",
        }
        if unit:
            attributes["unit_of_measurement"] = unit
        if plan_id:
            attributes["plan_id"] = plan_id
        if valid_until:
            attributes["valid_until"] = valid_until
        return attributes

    entities: list[SuggestionEntity] = []
    for entry in plan.get("devices", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        device = by_name.get(name)
        prefix = device.entity_prefix if device is not None else name
        label = device.label if device is not None else name

        # Feste Vorschlagsfelder (Prio/Freigabe/Mindestleistung).
        for field_name in SUGGESTION_FIELDS:
            value = entry.get(field_name)
            if value is None:
                continue
            field_label = _FIELD_LABEL.get(field_name, field_name)
            entities.append(
                SuggestionEntity(
                    entity_id=f"sensor.ep_{prefix}_{field_name}",
                    state=_format_state(value),
                    attributes=_attrs(
                        f"{label} – {field_label} (Vorschlag)", _FIELD_UNIT.get(field_name)
                    ),
                    device=name,
                    field_name=field_name,
                )
            )

        # Dynamische Zusatz-Vorschläge (D-047): Sensorname/Label/Einheit aus der Zusatz-Entität.
        for extra in getattr(device, "extras", ()):
            if not extra.ai_suggestion:
                continue
            value = entry.get(extra.plan_field)
            if value is None:
                continue
            entities.append(
                SuggestionEntity(
                    entity_id=extra.suggestion_entity_id,
                    state=_format_state(value),
                    attributes=_attrs(
                        f"{label} – {extra.display_label} (Vorschlag)", extra.unit or None
                    ),
                    device=name,
                    field_name=extra.plan_field,
                )
            )
    return entities


async def publish_suggestions(
    ha_client: HAClient | None,
    plan: dict,
    devices: list[Device],
    *,
    logger: logging.Logger | None = None,
    db: sqlite3.Connection | None = None,
) -> PublishResult:
    """Schreibt die Vorschlagswerte eines validierten Plans als HA-Sensoren.

    Fehler je Entität werden gefangen (`written`/`failed`) – die Methode wirft nie
    (Iron Rule 8). Ohne HA-Client passiert nichts (klare Begründung im Ergebnis).
    Jeder Schreibvorgang wird als `suggestions_published` auditiert.
    """
    plan_id = plan.get("plan_id")
    entities = build_suggestion_entities(plan, devices)

    if ha_client is None:
        if logger is not None:
            log(logger, "warning", "Vorschläge nicht geschrieben (kein HA-Client)",
                plan_id=plan_id)
        return PublishResult(ok=False, reason="kein HA-Client konfiguriert")

    if not entities:
        return PublishResult(ok=True, reason="keine Vorschlagswerte im Plan")

    written: list[str] = []
    failed: list[dict] = []
    for entity in entities:
        try:
            await ha_client.set_state(entity.entity_id, entity.state, entity.attributes)
            written.append(entity.entity_id)
        except Exception as exc:  # kontrolliert: ein Fehler bricht den Lauf nie ab
            failed.append(
                {"entity_id": entity.entity_id, "error": str(exc).strip() or exc.__class__.__name__}
            )

    result = PublishResult(ok=not failed, written=written, failed=failed)
    _audit(db, plan_id, result)
    if logger is not None:
        log(
            logger,
            "info" if result.ok else "warning",
            "Vorschläge nach HA geschrieben" if result.ok else "Vorschläge teilweise geschrieben",
            context={"written": written, "failed": failed},
            plan_id=plan_id,
        )
    return result


def _audit(db: sqlite3.Connection | None, plan_id: object, result: PublishResult) -> None:
    if db is None:
        return
    detail = json.dumps({"written": result.written, "failed": result.failed}, ensure_ascii=False)
    try:
        db.execute(
            "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
            ("publisher", "suggestions_published", plan_id, detail),
        )
        db.commit()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert das Schreiben nie
        pass
