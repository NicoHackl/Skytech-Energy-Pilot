"""Tests für den Vorschlags-Publisher (Entity-Erzeugung + fehlertolerantes Schreiben)."""

from energy_pilot.database import init_db
from energy_pilot.devices import BINARY, CONTROLLABLE, Device, DeviceExtra
from energy_pilot.suggestion_publisher import build_suggestion_entities, publish_suggestions

# Heizstab mit aktivierter Zusatz-Entität (D-047): Vorschlags-Sensorname bleibt kompatibel zum
# früheren Hardcode (`sensor.ep_heizstab_max_temperatur_vorschlag`, ersetzt D-035).
_HEIZSTAB_EXTRA = DeviceExtra(
    read_entity_id="input_number.ep_heizstab_max_temperatur",
    ai_suggestion=True, label="Max. Wassertemperatur", unit="°C",
)
DEVICES = [
    Device("batterie", "Batterie", "batterie", CONTROLLABLE, "watt"),
    Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt", extras=(_HEIZSTAB_EXTRA,)),
    Device("heizlufter_1", "Heizlüfter 1", "heizlufter_1", BINARY, "watt"),
]


class _FakeHA:
    """HA-Client-Doppel: zeichnet set_state auf, kann gezielt fehlschlagen."""

    def __init__(self, fail_for=None):
        self.calls = []
        self._fail_for = set(fail_for or ())

    async def set_state(self, entity_id, state, attributes=None):
        self.calls.append((entity_id, state, attributes))
        if entity_id in self._fail_for:
            raise RuntimeError("HTTP 500")
        return {"entity_id": entity_id, "state": state}


def _plan(devices):
    return {"plan_id": "abc123", "valid_until": "2026-06-19T13:00:00+00:00", "devices": devices}


# -- Entity-Erzeugung (rein) ------------------------------------------------


def test_build_entities_controllable_all_fields():
    plan = _plan(
        [
            {
                "name": "heizstab",
                "prio_vorschlag": 10,
                "freigabe_vorschlag": True,
                "geschutzte_mindestleistung_w_vorschlag": 800.0,
                "extra_heizstab_max_temperatur_vorschlag": 55.0,
            }
        ]
    )
    by_id = {e.entity_id: e for e in build_suggestion_entities(plan, DEVICES)}

    assert set(by_id) == {
        "sensor.ep_heizstab_prio_vorschlag",
        "sensor.ep_heizstab_freigabe_vorschlag",
        "sensor.ep_heizstab_geschutzte_mindestleistung_w_vorschlag",
        "sensor.ep_heizstab_max_temperatur_vorschlag",  # aus der Zusatz-Entität (D-047)
    }
    assert by_id["sensor.ep_heizstab_prio_vorschlag"].state == "10"
    assert by_id["sensor.ep_heizstab_freigabe_vorschlag"].state == "on"
    leistung = by_id["sensor.ep_heizstab_geschutzte_mindestleistung_w_vorschlag"]
    assert leistung.state == "800"  # 800.0 -> "800"
    assert leistung.attributes["unit_of_measurement"] == "W"
    assert leistung.attributes["plan_id"] == "abc123"
    # Der Zusatz-Vorschlag trägt Einheit + Label der Zusatz-Entität.
    temp = by_id["sensor.ep_heizstab_max_temperatur_vorschlag"]
    assert temp.state == "55"
    assert temp.attributes["unit_of_measurement"] == "°C"
    temperatur = by_id["sensor.ep_heizstab_max_temperatur_vorschlag"]
    assert temperatur.attributes["unit_of_measurement"] == "°C"


def test_freigabe_false_is_off():
    plan = _plan([{"name": "heizlufter_1", "prio_vorschlag": 20, "freigabe_vorschlag": False}])
    by_id = {e.entity_id: e for e in build_suggestion_entities(plan, DEVICES)}
    assert by_id["sensor.ep_heizlufter_1_freigabe_vorschlag"].state == "off"


def test_battery_writes_only_present_field():
    plan = _plan([{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0}])
    ids = [e.entity_id for e in build_suggestion_entities(plan, DEVICES)]
    assert ids == ["sensor.ep_batterie_geschutzte_mindestleistung_w_vorschlag"]


def test_unknown_device_falls_back_to_name_as_prefix():
    plan = _plan([{"name": "fremd", "prio_vorschlag": 30}])
    entity = build_suggestion_entities(plan, DEVICES)[0]
    assert entity.entity_id == "sensor.ep_fremd_prio_vorschlag"
    assert "fremd" in entity.attributes["friendly_name"]


def test_none_fields_are_skipped():
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10, "max_temperatur_vorschlag": None}])
    ids = [e.entity_id for e in build_suggestion_entities(plan, DEVICES)]
    assert ids == ["sensor.ep_heizstab_prio_vorschlag"]


# -- Schreiben (async, fehlertolerant) --------------------------------------


async def test_publish_all_ok_and_audits():
    conn = init_db(":memory:")
    ha = _FakeHA()
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True}])

    result = await publish_suggestions(ha, plan, DEVICES, db=conn)

    assert result.ok
    assert set(result.written) == {
        "sensor.ep_heizstab_prio_vorschlag",
        "sensor.ep_heizstab_freigabe_vorschlag",
    }
    assert result.failed == []
    audits = conn.execute(
        "SELECT COUNT(*) AS n FROM audit WHERE action='suggestions_published'"
    ).fetchone()["n"]
    assert audits == 1
    conn.close()


async def test_publish_partial_failure_does_not_crash():
    ha = _FakeHA(fail_for={"sensor.ep_heizstab_freigabe_vorschlag"})
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True}])

    result = await publish_suggestions(ha, plan, DEVICES)

    assert not result.ok
    assert result.written == ["sensor.ep_heizstab_prio_vorschlag"]
    assert result.failed[0]["entity_id"] == "sensor.ep_heizstab_freigabe_vorschlag"
    assert result.failed[0]["error"]


async def test_publish_without_ha_client_is_noop():
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10}])
    result = await publish_suggestions(None, plan, DEVICES)
    assert not result.ok
    assert "HA-Client" in result.reason
    assert result.written == []


async def test_publish_empty_plan_is_ok():
    result = await publish_suggestions(_FakeHA(), _plan([]), DEVICES)
    assert result.ok
    assert result.written == []
    assert "keine" in result.reason.lower()
