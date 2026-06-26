"""Tests für den Status-Publisher (Entity-Erzeugung + fehlertolerantes Schreiben)."""

from energy_pilot.database import init_db
from energy_pilot.status_publisher import build_status_entities, publish_status

SNAPSHOT_ONLINE = {
    "online": True,
    "last_cycle_at": "2026-06-26 12:00:00",
    "cycle_count": 42,
    "interval_s": 1,
    "pool_w": 1500.0,
    "current_deficit_w": 0.0,
    "global_mode": "auto",
}

FEEDBACK = {
    "overall": "beobachtet_abweichend",
    "reason": "",
    "plan_id": "p1",
    "valid_until": "2026-06-26T13:00:00+00:00",
    "in_window": True,
    "devices": [
        {"name": "heizstab", "label": "Heizstab", "verdict": "abweichend", "fields": []},
        {"name": "heizlufter_1", "label": "Heizlüfter 1", "verdict": "konform", "fields": []},
    ],
}


class _FakeHA:
    def __init__(self, fail_for=None):
        self.calls = []
        self._fail_for = set(fail_for or ())

    async def set_state(self, entity_id, state, attributes=None):
        self.calls.append((entity_id, state, attributes))
        if entity_id in self._fail_for:
            raise RuntimeError("HTTP 500")
        return {"entity_id": entity_id, "state": state}


# -- Entity-Erzeugung (rein) ------------------------------------------------


def test_build_entities_online_and_feedback():
    by_id = {e.entity_id: e for e in build_status_entities(SNAPSHOT_ONLINE, FEEDBACK)}
    assert set(by_id) == {"sensor.ep_hems_verbindung", "sensor.ep_plan_status"}

    conn = by_id["sensor.ep_hems_verbindung"]
    assert conn.state == "online"
    assert conn.attributes["cycle_count"] == 42
    assert conn.attributes["pool_w"] == 1500.0

    plan = by_id["sensor.ep_plan_status"]
    assert plan.state == "beobachtet_abweichend"
    assert plan.attributes["plan_id"] == "p1"
    assert plan.attributes["abweichungen"] == ["heizstab"]


def test_build_entities_offline_has_offline_state():
    entities = build_status_entities({"online": False}, {"overall": "unbekannt"})
    by_id = {e.entity_id: e for e in entities}
    assert by_id["sensor.ep_hems_verbindung"].state == "offline"
    assert by_id["sensor.ep_plan_status"].state == "unbekannt"


def test_none_attributes_are_dropped():
    entities = build_status_entities({"online": True}, {"overall": "kein_plan"})
    plan = next(e for e in entities if e.entity_id == "sensor.ep_plan_status")
    # plan_id/valid_until fehlen → dürfen nicht als None-Attribute auftauchen.
    assert "plan_id" not in plan.attributes
    assert "abweichungen" not in plan.attributes


# -- Schreiben (async, fehlertolerant) --------------------------------------


async def test_publish_all_ok_and_audits():
    conn = init_db(":memory:")
    ha = _FakeHA()

    result = await publish_status(ha, SNAPSHOT_ONLINE, FEEDBACK, db=conn)

    assert result["ok"]
    assert set(result["written"]) == {"sensor.ep_hems_verbindung", "sensor.ep_plan_status"}
    audits = conn.execute(
        "SELECT COUNT(*) AS n FROM audit WHERE action='status_published'"
    ).fetchone()["n"]
    assert audits == 1
    conn.close()


async def test_publish_partial_failure_does_not_crash():
    ha = _FakeHA(fail_for={"sensor.ep_plan_status"})
    result = await publish_status(ha, SNAPSHOT_ONLINE, FEEDBACK)
    assert not result["ok"]
    assert result["written"] == ["sensor.ep_hems_verbindung"]
    assert result["failed"][0]["entity_id"] == "sensor.ep_plan_status"


async def test_publish_without_ha_client_is_noop():
    result = await publish_status(None, SNAPSHOT_ONLINE, FEEDBACK)
    assert not result["ok"]
    assert "HA-Client" in result["reason"]
