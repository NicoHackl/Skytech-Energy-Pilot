"""EP-Status-Sensoren (M3): spiegelt HEMS-Verbindung + Plan-Rückkopplung nach HA.

Muster wie `suggestion_publisher`: reines `build_status_entities()` (testbar, ohne IO) +
fehlertolerantes `publish_status()`. Schreibt zwei Anzeige-Sensoren — kein Eingriff in HEMS:
- `sensor.ep_plan_status` — beobachtete Plan-Übereinstimmung (siehe `plan_feedback`),
- `sensor.ep_hems_verbindung` — HEMS-Erreichbarkeit + letzter Regelzyklus.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

from energy_pilot.logging_setup import log

if TYPE_CHECKING:
    from energy_pilot.ha_client import HAClient

# Lesbare Anzeige je Gesamtstatus (zusätzlich als Attribut; State bleibt der Schlüssel).
_OVERALL_LABEL: dict[str, str] = {
    "kein_plan": "Kein Plan",
    "unbekannt": "Unbekannt",
    "beobachtet_konform": "Beobachtet konform",
    "beobachtet_abweichend": "Beobachtet abweichend",
}


@dataclass
class StatusEntity:
    """Eine zu schreibende HA-Statusentität."""

    entity_id: str
    state: str
    attributes: dict


def _clean(attrs: dict) -> dict:
    """Entfernt None-Attribute (HA serialisiert sie sonst unnötig)."""
    return {k: v for k, v in attrs.items() if v is not None}


def build_status_entities(snapshot: dict, feedback: dict) -> list[StatusEntity]:
    """Leitet die beiden EP-Status-Entitäten aus Snapshot + Plan-Rückkopplung ab (rein)."""
    online = bool(snapshot.get("online"))
    conn_attrs = _clean(
        {
            "friendly_name": "EP – HEMS-Verbindung",
            "source": "Skytech Energy Pilot",
            "last_cycle_at": snapshot.get("last_cycle_at"),
            "cycle_count": snapshot.get("cycle_count"),
            "interval_s": snapshot.get("interval_s"),
            "pool_w": snapshot.get("pool_w"),
            "current_deficit_w": snapshot.get("current_deficit_w"),
            "global_mode": snapshot.get("global_mode"),
            "error": snapshot.get("last_error") or snapshot.get("error"),
        }
    )
    connection = StatusEntity(
        "sensor.ep_hems_verbindung", "online" if online else "offline", conn_attrs
    )

    overall = feedback.get("overall", "unbekannt")
    abweichungen = [
        d.get("name") for d in feedback.get("devices", []) if d.get("verdict") == "abweichend"
    ]
    plan_attrs = _clean(
        {
            "friendly_name": "EP – Plan-Status (beobachtet)",
            "source": "Skytech Energy Pilot",
            "label": _OVERALL_LABEL.get(overall, overall),
            "plan_id": feedback.get("plan_id"),
            "valid_until": feedback.get("valid_until"),
            "in_window": feedback.get("in_window"),
            "reason": feedback.get("reason") or None,
            "abweichungen": abweichungen or None,
        }
    )
    plan_status = StatusEntity("sensor.ep_plan_status", str(overall), plan_attrs)
    return [connection, plan_status]


async def publish_status(
    ha_client: HAClient | None,
    snapshot: dict,
    feedback: dict,
    *,
    logger: logging.Logger | None = None,
    db: sqlite3.Connection | None = None,
) -> dict:
    """Schreibt die EP-Status-Sensoren nach HA. Fehler je Entität werden gefangen
    (eiserne Regel 13); ohne HA-Client passiert nichts (klare Begründung)."""
    if ha_client is None:
        return {"ok": False, "written": [], "failed": [], "reason": "kein HA-Client konfiguriert"}

    written: list[str] = []
    failed: list[dict] = []
    for entity in build_status_entities(snapshot, feedback):
        try:
            await ha_client.set_state(entity.entity_id, entity.state, entity.attributes)
            written.append(entity.entity_id)
        except Exception as exc:  # kontrolliert: ein Fehler bricht den Lauf nie ab
            failed.append(
                {"entity_id": entity.entity_id, "error": str(exc).strip() or exc.__class__.__name__}
            )

    result = {"ok": not failed, "written": written, "failed": failed, "reason": ""}
    _audit(db, feedback.get("plan_id"), result)
    if logger is not None:
        log(
            logger,
            "info" if result["ok"] else "warning",
            "EP-Status nach HA geschrieben" if result["ok"] else "EP-Status teilweise geschrieben",
            context={"written": written, "failed": failed},
        )
    return result


def _audit(db: sqlite3.Connection | None, plan_id: object, result: dict) -> None:
    if db is None:
        return
    detail = json.dumps(
        {"written": result["written"], "failed": result["failed"]}, ensure_ascii=False
    )
    try:
        db.execute(
            "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
            ("status_publisher", "status_published", plan_id, detail),
        )
        db.commit()
    except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert das Schreiben nie
        pass
