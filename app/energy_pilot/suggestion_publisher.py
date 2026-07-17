"""Veröffentlichung der KI-Vorschlagswerte als HA-`sensor.ep_*`-Entitäten (M2-Schreibweg).

V1-Schreibweg (user-beispiele/variablen-zugriff.md §„Schreibweg — gestaffelt"): die
validierten Vorschlagswerte eines Plans werden **ausschließlich** als HA-Entitäten
geschrieben — reine Anzeige/Vorschläge, **keine** Steuerung und (noch) **keine** Übergabe
an HEMS (das ist M3). Der Schreibvertrag je Gerät stammt aus
`plan_schema.suggestion_keys` (D-030/D-034/D-037/D-035); hier werden nur die im Plan
tatsächlich gesetzten Felder geschrieben.

**Ausnahme Original-Schreibweg (D-052):** ist bei einer Zusatz-Entität (D-047) „In Original
schreiben" aktiv (`DeviceExtra.should_write_original`), schreibt EP den Vorschlag zusätzlich
über einen HA-Service (`set_value`/`select_option`/`set_datetime`/`turn_on`/`turn_off`) in die
Original-Entität zurück. Das gilt **nur** für echte Helfer-Domänen; `sensor.*` bleibt immer
read-only, dort entsteht nur der `_vorschlag`-Sensor.

**Modus-Gate (D-057):** der Original-Schreibweg greift zusätzlich nur, wenn die Modus-Achse
für das Gerät die Quelle `ep` ergibt (`control_mode.resolve_source`) — im manuellen Modus
gehört der Wert dem User und wird nie überschrieben. Das Gate sitzt bewusst hier und nicht an
den Aufrufstellen: `publish_suggestions()` ist der einzige gemeinsame Nenner der beiden
Schreibpfade (`Planner.run()` und `Planner.publish_latest()`, der „Erneut schreiben"-Button).
Die `sensor.ep_*_vorschlag`-Spiegelsensoren bleiben ungegated — sie sind EP-eigene Ausgaben
und sollen den Vorschlag gerade auch im manuellen Modus sichtbar machen.

Trennung: `build_suggestion_entities()`/`build_original_writes()` sind rein (testbar, ohne
IO); `publish_suggestions()` liest die Modus-Quellen und schreibt über den HA-Client und fängt
Fehler je Entität ab — die App blockiert nie (Iron Rule 8).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from energy_pilot.control_mode import SOURCE_EP, SOURCE_OFF, read_sources
from energy_pilot.logging_setup import log
from energy_pilot.plan_schema import SUGGESTION_FIELDS

if TYPE_CHECKING:
    from energy_pilot.devices import Device, DeviceExtra
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
class OriginalWrite:
    """Ein Original-Schreibvorgang (D-052, „In Original schreiben") via HA-Service."""

    entity_id: str
    domain: str
    service: str
    data: dict
    device: str
    field_name: str


@dataclass
class PublishResult:
    """Ergebnis eines Schreibvorgangs für Endpoint/UI/Audit."""

    ok: bool
    written: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    # Modusbedingt übersprungene Original-Schreibvorgänge (D-057). Kein Fehler, sondern
    # korrektes Verhalten – deshalb ohne Einfluss auf `ok`. Ohne diese Liste wirkte ein
    # aktives „In Original schreiben" stumm wirkungslos.
    skipped: list[dict] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "written": self.written,
            "failed": self.failed,
            "skipped": self.skipped,
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


def _service_payload(extra: DeviceExtra, value: object) -> tuple[str, str, dict] | None:
    """Leitet Service/Domäne/Nutzdaten für den Original-Schreibweg (D-052) aus dem Typ ab.

    Domäne = `extra.domain` (der Service liegt HA-idiomatisch im selben Namensraum wie die
    Entität, z.B. `input_number.set_value`, `select.select_option`). `None` bei ungültigem
    Zahlenwert oder unbekanntem Typ (`auto`, nur bei `sensor.*` – dort greift der
    Original-Schreibweg wegen `is_writable_helper` ohnehin nie).
    """
    domain = extra.domain
    if extra.kind == "number":
        try:
            return domain, "set_value", {"value": float(value)}
        except (TypeError, ValueError):
            return None
    if extra.kind == "text":
        return domain, "set_value", {"value": str(value)}
    if extra.kind == "select":
        return domain, "select_option", {"option": str(value)}
    if extra.kind == "datetime":
        return domain, "set_datetime", {"datetime": str(value)}
    if extra.kind == "bool":
        return domain, ("turn_on" if bool(value) else "turn_off"), {}
    return None


def _skip_reason(source: str) -> str:
    """Klartext-Begründung, warum die Modus-Achse einen Original-Schreibvorgang sperrt."""
    if source == SOURCE_OFF:
        return "Modus aus (oder Modus nicht lesbar) – kein Schreiben in die Original-Entität"
    return "Modus manuell – der Nutzerwert bleibt stehen"


def build_original_writes(
    plan: dict, devices: list[Device], sources: dict[str, str]
) -> tuple[list[OriginalWrite], list[dict]]:
    """Leitet aus einem validierten Plan die Original-Schreibvorgänge ab (D-052/D-057).

    Nur für Zusatz-Entitäten mit `should_write_original` (aktives `write_original`, aktiver
    `ai_suggestion` **und** schreibbare Helfer-Domäne, kein `sensor.*`) **und** nur, wenn die
    Modus-Achse für das Gerät die Quelle `ep` ergibt (D-057).

    `sources` bildet `device.name -> 'aus' | 'user' | 'ep'` ab (`control_mode.read_sources`).
    Ein unbekanntes Gerät gilt als `aus` – lieber nicht schreiben als einen Nutzerwert
    überschreiben. Liefert `(writes, skipped)`; `skipped` trägt je gesperrter Entität
    `{entity_id, device, source, reason}` für UI und Audit.
    """
    by_name = {device.name: device for device in devices}
    writes: list[OriginalWrite] = []
    skipped: list[dict] = []
    for entry in plan.get("devices", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        device = by_name.get(name)
        if device is None:
            continue
        source = sources.get(name, SOURCE_OFF)
        for extra in device.extras:
            if not extra.should_write_original:
                continue
            value = entry.get(extra.plan_field)
            if value is None:
                continue
            payload = _service_payload(extra, value)
            if payload is None:
                continue
            if source != SOURCE_EP:
                skipped.append(
                    {
                        "entity_id": extra.read_entity_id,
                        "device": name,
                        "source": source,
                        "reason": _skip_reason(source),
                    }
                )
                continue
            domain, service, data = payload
            writes.append(
                OriginalWrite(
                    entity_id=extra.read_entity_id,
                    domain=domain,
                    service=service,
                    data=data,
                    device=name,
                    field_name=extra.plan_field,
                )
            )
    return writes, skipped


async def publish_suggestions(
    ha_client: HAClient | None,
    plan: dict,
    devices: list[Device],
    *,
    logger: logging.Logger | None = None,
    db: sqlite3.Connection | None = None,
) -> PublishResult:
    """Schreibt die Vorschlagswerte eines validierten Plans als HA-Sensoren.

    Zusätzlich (D-052): schreibt aktivierte `should_write_original`-Zusatzentitäten per
    HA-Service in ihre Original-Entität zurück (`build_original_writes`) – aber nur, wenn die
    Modus-Achse für das Gerät die Quelle `ep` ergibt (D-057). Gesperrte Schreibvorgänge landen
    in `skipped` und lassen `ok` unberührt (kein Fehler, sondern gewolltes Verhalten).

    Der Modus wird **frisch zum Schreibzeitpunkt** gelesen (`control_mode.read_sources`), nie
    aus einem Cache: ein veralteter Modus darf nie über einen Schreibvorgang entscheiden.

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

    # Modus nur lesen, wenn überhaupt ein Original-Schreibweg aktiv ist: sonst wären es
    # 1+N nutzlose HA-Abrufe je Lauf – plus eine irreführende „Modus nicht lesbar"-Warnung in
    # Anlagen, die „In Original schreiben" nie aktiviert haben.
    needs_modes = any(extra.should_write_original for d in devices for extra in d.extras)
    sources = await read_sources(ha_client, devices, logger=logger) if needs_modes else {}
    original_writes, skipped = build_original_writes(plan, devices, sources)

    if not entities and not original_writes and not skipped:
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

    for write in original_writes:
        try:
            await ha_client.call_service(write.domain, write.service, write.entity_id, write.data)
            written.append(write.entity_id)
        except Exception as exc:  # kontrolliert: ein Fehler bricht den Lauf nie ab
            failed.append(
                {"entity_id": write.entity_id, "error": str(exc).strip() or exc.__class__.__name__}
            )

    result = PublishResult(ok=not failed, written=written, failed=failed, skipped=skipped)
    _audit(db, plan_id, result)
    if logger is not None:
        log(
            logger,
            "info" if result.ok else "warning",
            "Vorschläge nach HA geschrieben" if result.ok else "Vorschläge teilweise geschrieben",
            context={"written": written, "failed": failed, "skipped": skipped},
            plan_id=plan_id,
        )
    return result


def _audit(db: sqlite3.Connection | None, plan_id: object, result: PublishResult) -> None:
    if db is None:
        return
    detail = json.dumps(
        {"written": result.written, "failed": result.failed, "skipped": result.skipped},
        ensure_ascii=False,
    )
    try:
        db.execute(
            "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
            ("publisher", "suggestions_published", plan_id, detail),
        )
        db.commit()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert das Schreiben nie
        pass
