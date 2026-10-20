"""Tests für den Vorschlags-Publisher (Entity-Erzeugung + fehlertolerantes Schreiben)."""

from energy_pilot import suggestion_publisher
from energy_pilot.control_mode import HA_GLOBAL_MODE, device_mode_entity
from energy_pilot.database import init_db
from energy_pilot.devices import BINARY, CONTROLLABLE, Device, DeviceExtra
from energy_pilot.http_errors import HTTPStatusError
from energy_pilot.suggestion_publisher import (
    INTERFACE_ENTITY,
    build_original_writes,
    build_suggestion_entities,
    publish_suggestions,
)

# Modus-Achse (D-057): Quelle je Gerät, wie sie `control_mode.read_sources` liefert.
_EP = {"heizstab": "ep", "batterie": "ep", "heizlufter_1": "ep"}

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
    """HA-Client-Doppel: zeichnet set_state/call_service auf, kann gezielt fehlschlagen.

    Bedient zusätzlich die Modus-Helfer (D-057). Default ist global `auto` (= KI/EP), damit die
    Tests zum Original-Schreibweg den Schreibfall prüfen; `global_mode`/`device_modes` stellen
    die Modus-Achse gezielt um. Ein nicht hinterlegter Helfer wirft HTTP 404 – wie HA bei einer
    unbekannten Entität.
    """

    def __init__(self, fail_for=None, global_mode="auto", device_modes=None):
        self.calls = []
        self.service_calls = []
        self.removed = []
        self._fail_for = set(fail_for or ())
        self._states = {}
        if global_mode is not None:
            self._states[HA_GLOBAL_MODE] = global_mode
        for prefix, mode in (device_modes or {}).items():
            self._states[device_mode_entity(prefix)] = mode

    async def get_state(self, entity_id):
        if entity_id in self._fail_for:
            raise HTTPStatusError(service="Home Assistant", status=500, reason="Server Error")
        if entity_id not in self._states:
            raise HTTPStatusError(service="Home Assistant", status=404, reason="Not Found")
        return {"entity_id": entity_id, "state": self._states[entity_id]}

    async def set_state(self, entity_id, state, attributes=None):
        self.calls.append((entity_id, state, attributes))
        if entity_id in self._fail_for:
            raise RuntimeError("HTTP 500")
        return {"entity_id": entity_id, "state": state}

    async def remove_state(self, entity_id):
        self.removed.append(entity_id)
        return True

    async def call_service(self, domain, service, entity_id, data=None):
        self.service_calls.append((domain, service, entity_id, data))
        if entity_id in self._fail_for:
            raise RuntimeError("HTTP 500")
        return {"entity_id": entity_id}


def _plan(devices):
    return {
        "schema_version": "1.0",
        "plan_id": "abc123",
        "valid_from": "2026-06-19T12:00:00+00:00",
        "valid_until": "2026-06-19T13:00:00+00:00",
        "devices": devices,
    }


# -- Entity-Erzeugung (rein) ------------------------------------------------


def _iface(entities):
    return next(e for e in entities if e.entity_id == INTERFACE_ENTITY)


def test_build_entities_controllable_all_fields():
    """D-069: feste Felder in der einen Schnittstelle, Zusatz-Vorschlag als eigener Sensor."""
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
    entities = build_suggestion_entities(plan, DEVICES)
    by_id = {e.entity_id: e for e in entities}

    assert set(by_id) == {
        INTERFACE_ENTITY,
        "sensor.ep_heizstab_max_temperatur_vorschlag",  # aus der Zusatz-Entität (D-047)
    }
    iface = by_id[INTERFACE_ENTITY]
    assert iface.state == "heizstab"
    attrs = iface.attributes
    assert attrs["heizstab_prio"] == 10
    assert attrs["heizstab_freigabe"] is True
    assert attrs["heizstab_geschutzte_mindestleistung_w"] == 800.0
    assert attrs["heizstab_label"] == "Heizstab"
    assert attrs["plan_id"] == "abc123"
    assert attrs["valid_from"] == "2026-06-19T12:00:00+00:00"
    assert attrs["valid_until"] == "2026-06-19T13:00:00+00:00"
    assert attrs["schnittstelle_version"] == 1
    assert not any(key.endswith("_vorschlag") for key in attrs)
    # Der Zusatz-Vorschlag trägt Einheit + Label der Zusatz-Entität.
    temp = by_id["sensor.ep_heizstab_max_temperatur_vorschlag"]
    assert temp.state == "55"
    assert temp.attributes["unit_of_measurement"] == "°C"


def test_freigabe_false_bleibt_bool():
    plan = _plan([{"name": "heizlufter_1", "prio_vorschlag": 20, "freigabe_vorschlag": False}])
    assert _iface(build_suggestion_entities(plan, DEVICES)).attributes[
        "heizlufter_1_freigabe"] is False


def test_mehrere_geraete_in_einer_entitaet():
    plan = _plan([
        {"name": "heizstab", "prio_vorschlag": 10},
        {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
    ])
    entities = build_suggestion_entities(plan, DEVICES)
    assert [e.entity_id for e in entities] == [INTERFACE_ENTITY]
    iface = entities[0]
    assert iface.state == "heizstab,batterie"
    assert iface.attributes["batterie_geschutzte_mindestleistung_w"] == 3000.0
    assert "batterie_prio" not in iface.attributes


def test_unknown_device_falls_back_to_name_as_prefix():
    plan = _plan([{"name": "fremd", "prio_vorschlag": 30}])
    iface = _iface(build_suggestion_entities(plan, DEVICES))
    assert iface.state == "fremd"
    assert iface.attributes["fremd_prio"] == 30
    assert iface.attributes["fremd_label"] == "fremd"


def test_none_fields_are_skipped():
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10, "max_temperatur_vorschlag": None}])
    attrs = _iface(build_suggestion_entities(plan, DEVICES)).attributes
    assert attrs["heizstab_prio"] == 10
    assert "heizstab_freigabe" not in attrs


def test_ohne_feste_felder_keine_schnittstelle():
    plan = _plan([{"name": "heizstab", "extra_heizstab_max_temperatur_vorschlag": 55.0}])
    ids = [e.entity_id for e in build_suggestion_entities(plan, DEVICES)]
    assert ids == ["sensor.ep_heizstab_max_temperatur_vorschlag"]


# -- Schreiben (async, fehlertolerant) --------------------------------------


async def test_publish_all_ok_and_audits(monkeypatch):
    monkeypatch.setattr(suggestion_publisher, "_legacy_removed", False)
    conn = init_db(":memory:")
    ha = _FakeHA()
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True}])

    result = await publish_suggestions(ha, plan, DEVICES, db=conn)

    assert result.ok
    assert result.written == [INTERFACE_ENTITY]
    assert result.failed == []
    # Genau ein Schreibvorgang, kein Commit-Marker mehr (Vertrag 2.0).
    assert [call[0] for call in ha.calls] == [INTERFACE_ENTITY]
    # Alte Entitäten aus Vertrag 1.0 werden einmal je Prozess entfernt.
    assert "sensor.ep_plan_commit" in ha.removed
    assert "sensor.ep_heizstab_prio_vorschlag" in ha.removed
    audits = conn.execute(
        "SELECT COUNT(*) AS n FROM audit WHERE action='suggestions_published'"
    ).fetchone()["n"]
    assert audits == 1
    conn.close()

    ha2 = _FakeHA()
    await publish_suggestions(ha2, plan, DEVICES)
    assert ha2.removed == []  # nur einmal je Prozess


async def test_publish_failure_does_not_crash():
    ha = _FakeHA(fail_for={INTERFACE_ENTITY})
    plan = _plan([{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True}])

    result = await publish_suggestions(ha, plan, DEVICES)

    assert not result.ok
    assert result.written == []
    assert result.failed[0]["entity_id"] == INTERFACE_ENTITY
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


# -- Original-Schreibweg (D-052, „In Original schreiben") -------------------


def _devices_with_write_original(extra):
    return [Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt", extras=(extra,))]


def test_build_original_writes_number_maps_to_set_value():
    extra = DeviceExtra(
        read_entity_id="input_number.ep_heizstab_max_temperatur",
        ai_suggestion=True, write_original=True,
    )
    plan = _plan([{"name": "heizstab", "extra_heizstab_max_temperatur_vorschlag": 55.0}])
    writes, skipped = build_original_writes(plan, _devices_with_write_original(extra), _EP)
    assert skipped == []
    assert len(writes) == 1
    w = writes[0]
    assert w.entity_id == "input_number.ep_heizstab_max_temperatur"
    assert (w.domain, w.service, w.data) == ("input_number", "set_value", {"value": 55.0})


def test_build_original_writes_bool_maps_to_turn_on_off():
    extra = DeviceExtra(
        read_entity_id="input_boolean.eco_modus", ai_suggestion=True, write_original=True,
    )
    plan_on = _plan([{"name": "heizstab", "extra_eco_modus_vorschlag": True}])
    plan_off = _plan([{"name": "heizstab", "extra_eco_modus_vorschlag": False}])
    devices = _devices_with_write_original(extra)
    assert build_original_writes(plan_on, devices, _EP)[0][0].service == "turn_on"
    assert build_original_writes(plan_off, devices, _EP)[0][0].service == "turn_off"


def test_build_original_writes_select_maps_to_select_option():
    extra = DeviceExtra(
        read_entity_id="input_select.modus", ai_suggestion=True, write_original=True,
    )
    plan = _plan([{"name": "heizstab", "extra_modus_vorschlag": "Eco"}])
    w = build_original_writes(plan, _devices_with_write_original(extra), _EP)[0][0]
    assert (w.domain, w.service, w.data) == ("input_select", "select_option", {"option": "Eco"})


def test_build_original_writes_skips_sensor_source():
    # sensor.* ist grundsätzlich read-only: should_write_original ist False, egal was gesetzt ist.
    extra = DeviceExtra(read_entity_id="sensor.x", ai_suggestion=True, write_original=True)
    plan = _plan([{"name": "heizstab", "extra_x_vorschlag": 1.0}])
    # Kein Schreibweg und auch kein „gesperrt"-Hinweis: sensor.* ist gar kein Kandidat.
    assert build_original_writes(plan, _devices_with_write_original(extra), _EP) == ([], [])


def test_build_original_writes_skips_without_flag():
    extra = DeviceExtra(read_entity_id="input_number.x", ai_suggestion=True, write_original=False)
    plan = _plan([{"name": "heizstab", "extra_x_vorschlag": 1.0}])
    assert build_original_writes(plan, _devices_with_write_original(extra), _EP) == ([], [])


# -- Modus-Gate (D-057) ----------------------------------------------------


def _writable_extra():
    return DeviceExtra(
        read_entity_id="input_number.ep_heizstab_max_temperatur",
        ai_suggestion=True, write_original=True,
    )


def _temp_plan():
    return _plan([{"name": "heizstab", "extra_heizstab_max_temperatur_vorschlag": 55.0}])


def test_build_original_writes_blocked_when_source_user():
    """Manueller Modus: der Nutzerwert bleibt stehen, der Vorgang landet in `skipped`."""
    devices = _devices_with_write_original(_writable_extra())
    writes, skipped = build_original_writes(_temp_plan(), devices, {"heizstab": "user"})
    assert writes == []
    assert len(skipped) == 1
    assert skipped[0]["entity_id"] == "input_number.ep_heizstab_max_temperatur"
    assert skipped[0]["source"] == "user"
    assert "manuell" in skipped[0]["reason"].lower()


def test_build_original_writes_blocked_when_source_off():
    devices = _devices_with_write_original(_writable_extra())
    writes, skipped = build_original_writes(_temp_plan(), devices, {"heizstab": "aus"})
    assert writes == []
    assert skipped[0]["source"] == "aus"


def test_build_original_writes_unknown_device_is_blocked():
    """Fehlt die Quelle zu einem Gerät, gilt fail-safe 'aus' – nie schreiben."""
    devices = _devices_with_write_original(_writable_extra())
    writes, skipped = build_original_writes(_temp_plan(), devices, {})
    assert writes == []
    assert skipped[0]["source"] == "aus"


async def test_publish_manual_mode_writes_sensor_but_not_original():
    """Der Kern von D-057: Vorschlag sichtbar, Original unangetastet, `ok` bleibt True."""
    devices = _devices_with_write_original(_writable_extra())
    ha = _FakeHA(global_mode="manuell", device_modes={"heizstab": "manuell"})

    result = await publish_suggestions(ha, _temp_plan(), devices)

    assert result.ok  # modusbedingtes Überspringen ist kein Fehler
    assert ha.service_calls == []  # nichts in die Original-Entität geschrieben
    assert "sensor.ep_heizstab_max_temperatur_vorschlag" in result.written  # Vorschlag sichtbar
    assert result.failed == []
    assert result.skipped[0]["entity_id"] == "input_number.ep_heizstab_max_temperatur"


async def test_publish_global_auto_overrides_device_manual():
    """HEMS-Asymmetrie: global `auto` erzwingt KI, ein Gerät auf `manuell` kann nicht vetoen."""
    devices = _devices_with_write_original(_writable_extra())
    ha = _FakeHA(global_mode="auto", device_modes={"heizstab": "manuell"})

    result = await publish_suggestions(ha, _temp_plan(), devices)

    assert result.skipped == []
    assert [c[2] for c in ha.service_calls] == ["input_number.ep_heizstab_max_temperatur"]


async def test_publish_device_off_vetoes_global_auto():
    """Der Per-Gerät-Kill `aus` gilt immer – auch gegen global `auto`."""
    devices = _devices_with_write_original(_writable_extra())
    ha = _FakeHA(global_mode="auto", device_modes={"heizstab": "aus"})

    result = await publish_suggestions(ha, _temp_plan(), devices)

    assert ha.service_calls == []
    assert result.skipped[0]["source"] == "aus"


async def test_publish_device_auto_under_global_manual_writes():
    """Bei global `manuell` entscheidet das Gerät: `auto` => KI-Übernahme."""
    devices = _devices_with_write_original(_writable_extra())
    ha = _FakeHA(global_mode="manuell", device_modes={"heizstab": "auto"})

    result = await publish_suggestions(ha, _temp_plan(), devices)

    assert result.skipped == []
    assert len(ha.service_calls) == 1


async def test_publish_missing_device_mode_helper_falls_through_to_user():
    """Fehlender Geräte-Helfer (HTTP 404) verhält sich wie im HEMS: Durchfall auf 'user'."""
    devices = _devices_with_write_original(_writable_extra())
    ha = _FakeHA(global_mode="manuell")  # kein Geräte-Modus hinterlegt => 404

    result = await publish_suggestions(ha, _temp_plan(), devices)

    assert ha.service_calls == []
    assert result.skipped[0]["source"] == "user"


async def test_publish_missing_global_mode_helper_blocks_everything():
    """Ohne globalen Helfer gilt 'aus' (wie HEMS `st.get(...) or "aus"`) – nie schreiben."""
    devices = _devices_with_write_original(_writable_extra())
    ha = _FakeHA(global_mode=None, device_modes={"heizstab": "auto"})

    result = await publish_suggestions(ha, _temp_plan(), devices)

    assert ha.service_calls == []
    assert result.skipped[0]["source"] == "aus"


async def test_publish_ha_error_on_mode_read_blocks_write():
    """Ein kaputtes HA (500) sperrt den Schreibweg – fail-safe, kein Überschreiben."""
    devices = _devices_with_write_original(_writable_extra())
    ha = _FakeHA(fail_for={HA_GLOBAL_MODE}, device_modes={"heizstab": "auto"})

    result = await publish_suggestions(ha, _temp_plan(), devices)

    assert ha.service_calls == []
    assert result.skipped[0]["source"] == "aus"


async def test_publish_writes_original_via_call_service():
    extra = DeviceExtra(
        read_entity_id="input_number.ep_heizstab_max_temperatur",
        ai_suggestion=True, write_original=True, label="Max. Wassertemperatur", unit="°C",
    )
    devices = _devices_with_write_original(extra)
    ha = _FakeHA()
    plan = _plan([{"name": "heizstab", "extra_heizstab_max_temperatur_vorschlag": 55.0}])

    result = await publish_suggestions(ha, plan, devices)

    assert result.ok
    assert "sensor.ep_heizstab_max_temperatur_vorschlag" in result.written  # weiterhin der Sensor
    assert "input_number.ep_heizstab_max_temperatur" in result.written  # zusätzlich das Original
    assert ha.service_calls == [
        ("input_number", "set_value", "input_number.ep_heizstab_max_temperatur", {"value": 55.0})
    ]


async def test_publish_original_write_failure_does_not_block_sensor_write():
    extra = DeviceExtra(
        read_entity_id="input_number.ep_heizstab_max_temperatur",
        ai_suggestion=True, write_original=True,
    )
    devices = _devices_with_write_original(extra)
    ha = _FakeHA(fail_for={"input_number.ep_heizstab_max_temperatur"})
    plan = _plan([{"name": "heizstab", "extra_heizstab_max_temperatur_vorschlag": 55.0}])

    result = await publish_suggestions(ha, plan, devices)

    assert not result.ok  # Original-Schreibweg schlug fehl
    assert "sensor.ep_heizstab_max_temperatur_vorschlag" in result.written  # Sensor trotzdem ok
    assert result.failed[0]["entity_id"] == "input_number.ep_heizstab_max_temperatur"
