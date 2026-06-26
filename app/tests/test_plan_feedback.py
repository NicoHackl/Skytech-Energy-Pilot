"""Tests für die Plan-Rückkopplung (reine Ableitung Vorschlag ↔ HEMS-Ist)."""

from datetime import UTC, datetime, timedelta

from energy_pilot.devices import BINARY, CONTROLLABLE, Device
from energy_pilot.plan_feedback import (
    ABWEICHEND,
    KEIN_PLAN,
    KONFORM,
    UNBEKANNT,
    derive_plan_feedback,
)

DEVICES = [
    Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt"),
    Device("heizlufter_1", "Heizlüfter 1", "heizlufter_1", BINARY, "watt"),
]

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def _latest(devices, *, ok=True, valid_from=None, valid_until=None):
    valid_from = valid_from or (NOW - timedelta(minutes=10)).isoformat()
    valid_until = valid_until or (NOW + timedelta(minutes=50)).isoformat()
    return {
        "ok": ok,
        "plan": {
            "plan_id": "p1",
            "valid_from": valid_from,
            "valid_until": valid_until,
            "devices": devices,
        },
    }


def _hems(devices):
    return {"status": {"pool_w": 1000.0, "current_deficit_w": 0.0, "devices": devices}}


def test_no_plan_returns_kein_plan():
    fb = derive_plan_feedback(None, DEVICES, _hems([]), now=NOW)
    assert fb["overall"] == KEIN_PLAN

    fb_rejected = derive_plan_feedback(_latest([], ok=False), DEVICES, _hems([]), now=NOW)
    assert fb_rejected["overall"] == KEIN_PLAN


def test_hems_offline_is_unknown():
    latest = _latest([{"name": "heizstab", "prio_vorschlag": 10}])
    fb = derive_plan_feedback(latest, DEVICES, None, now=NOW)
    assert fb["overall"] == UNBEKANNT
    assert "HEMS" in fb["reason"]


def test_conform_when_priority_and_schutz_match():
    latest = _latest(
        [
            {
                "name": "heizstab",
                "prio_vorschlag": 10,
                "geschutzte_mindestleistung_w_vorschlag": 800.0,
            }
        ]
    )
    hems = _hems(
        [{"type": "controllable", "id": "heizstab", "label": "Heizstab",
          "priority": 10, "eligible": True, "schutz_w": 800.4}]
    )
    fb = derive_plan_feedback(latest, DEVICES, hems, now=NOW)
    assert fb["overall"] == KONFORM
    dev = fb["devices"][0]
    assert dev["verdict"] == "konform"
    assert dev["matched"] is True
    statuses = {f["feld"]: f["status"] for f in dev["fields"]}
    assert statuses["prio_vorschlag"] == "match"
    assert statuses["geschutzte_mindestleistung_w_vorschlag"] == "match"


def test_divergent_priority():
    latest = _latest([{"name": "heizstab", "prio_vorschlag": 10}])
    hems = _hems(
        [{"type": "controllable", "id": "heizstab", "label": "Heizstab",
          "priority": 20, "eligible": True, "schutz_w": 0.0}]
    )
    fb = derive_plan_feedback(latest, DEVICES, hems, now=NOW)
    assert fb["overall"] == ABWEICHEND
    assert fb["devices"][0]["verdict"] == "abweichend"


def test_matched_by_label_when_id_differs():
    # HEMS-id weicht vom EP-Namen ab, aber das Label passt → Treffer über Label.
    latest = _latest([{"name": "heizstab", "prio_vorschlag": 10}])
    hems = _hems(
        [{"type": "controllable", "id": "hs_1", "label": "Heizstab",
          "priority": 10, "eligible": True, "schutz_w": 0.0}]
    )
    fb = derive_plan_feedback(latest, DEVICES, hems, now=NOW)
    assert fb["devices"][0]["matched"] is True
    assert fb["overall"] == KONFORM


def test_missing_device_is_unknown_not_divergent():
    latest = _latest([{"name": "heizstab", "prio_vorschlag": 10}])
    fb = derive_plan_feedback(latest, DEVICES, _hems([]), now=NOW)
    # Keine HEMS-Geräte vorhanden → Status nicht verfügbar.
    assert fb["overall"] == UNBEKANNT


def test_device_not_in_hems_marks_unknown():
    latest = _latest([{"name": "heizstab", "prio_vorschlag": 10}])
    hems = _hems(
        [{"type": "binary", "id": "heizlufter_1", "label": "Heizlüfter 1",
          "priority": 30, "eligible": True}]
    )
    fb = derive_plan_feedback(latest, DEVICES, hems, now=NOW)
    dev = fb["devices"][0]
    assert dev["matched"] is False
    assert dev["verdict"] == "unbekannt"
    assert fb["overall"] == UNBEKANNT


def test_out_of_window_caps_overall_to_unknown():
    latest = _latest(
        [{"name": "heizstab", "prio_vorschlag": 10}],
        valid_from=(NOW - timedelta(hours=2)).isoformat(),
        valid_until=(NOW - timedelta(hours=1)).isoformat(),
    )
    hems = _hems(
        [{"type": "controllable", "id": "heizstab", "label": "Heizstab",
          "priority": 10, "eligible": True, "schutz_w": 0.0}]
    )
    fb = derive_plan_feedback(latest, DEVICES, hems, now=NOW)
    assert fb["in_window"] is False
    assert fb["overall"] == UNBEKANNT
    assert "Gültigkeitsfenster" in fb["reason"]


def test_freigabe_soft_unknown_when_eligible_false():
    # Vorschlag „frei", HEMS nicht eligible → weich (kann technische Freigabe sein).
    latest = _latest([{"name": "heizlufter_1", "prio_vorschlag": 30, "freigabe_vorschlag": True}])
    hems = _hems(
        [{"type": "binary", "id": "heizlufter_1", "label": "Heizlüfter 1",
          "priority": 30, "eligible": False}]
    )
    fb = derive_plan_feedback(latest, DEVICES, hems, now=NOW)
    dev = fb["devices"][0]
    statuses = {f["feld"]: f["status"] for f in dev["fields"]}
    assert statuses["freigabe_vorschlag"] == "unbekannt"
    assert statuses["prio_vorschlag"] == "match"
    assert dev["verdict"] == "konform"
