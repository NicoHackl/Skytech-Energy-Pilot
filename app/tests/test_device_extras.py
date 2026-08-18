"""Tests für die Persistenz der Zusatz-Entitäten (D-047) und das Heizstab-Seeding."""

from energy_pilot.database import init_db
from energy_pilot.device_extras import (
    apply_extras,
    delete_extra,
    is_valid_entity_id,
    load_extras,
    seed_defaults,
    suggestion_conflict,
    upsert_extra,
)
from energy_pilot.devices import CONTROLLABLE, Device


def _db():
    return init_db(":memory:")


def _dev(name="heizstab", prefix=None):
    return Device(name, name.title(), prefix or name, CONTROLLABLE, "watt")


def test_is_valid_entity_id():
    assert is_valid_entity_id("input_number.min_soc_auto")
    assert is_valid_entity_id("sensor.foo_bar")
    assert not is_valid_entity_id("keine_id")
    assert not is_valid_entity_id("input_number.")
    assert not is_valid_entity_id("")


def test_upsert_and_load_roundtrip():
    db = _db()
    upsert_extra(
        db, device_name="heizstab", read_entity_id="input_number.min_soc_auto",
        ai_suggestion=True, ai_hint="Minimaler SOC", label="Min SOC", unit="%",
    )
    extras = load_extras(db)
    assert list(extras) == ["heizstab"]
    ex = extras["heizstab"][0]
    assert ex.read_entity_id == "input_number.min_soc_auto"
    assert ex.ai_suggestion is True
    assert ex.ai_hint == "Minimaler SOC"
    assert ex.unit == "%"
    assert ex.suggestion_entity_id == "sensor.ep_min_soc_auto_vorschlag"


def test_upsert_and_load_roundtrip_write_original():
    db = _db()
    upsert_extra(
        db, device_name="heizstab", read_entity_id="input_number.min_soc_auto",
        ai_suggestion=True, write_original=True,
    )
    ex = load_extras(db)["heizstab"][0]
    assert ex.write_original is True
    assert ex.should_write_original is True

    # Default (nicht übergeben) bleibt False.
    upsert_extra(
        db, device_name="heizstab", read_entity_id="input_number.other", ai_suggestion=True,
    )
    ex2 = next(e for e in load_extras(db)["heizstab"] if e.read_entity_id == "input_number.other")
    assert ex2.write_original is False


def test_upsert_updates_existing():
    db = _db()
    upsert_extra(db, device_name="heizstab", read_entity_id="input_number.x", ai_suggestion=False)
    upsert_extra(
        db, device_name="heizstab", read_entity_id="input_number.x",
        ai_suggestion=True, ai_hint="neu",
    )
    extras = load_extras(db)["heizstab"]
    assert len(extras) == 1  # kein Duplikat, sondern Update
    assert extras[0].ai_suggestion is True
    assert extras[0].ai_hint == "neu"


def test_delete_extra():
    db = _db()
    upsert_extra(db, device_name="heizstab", read_entity_id="input_number.x", ai_suggestion=False)
    delete_extra(db, device_name="heizstab", read_entity_id="input_number.x")
    assert load_extras(db) == {}


def test_apply_extras_attaches_to_devices():
    db = _db()
    upsert_extra(db, device_name="heizstab", read_entity_id="input_number.x", ai_suggestion=True)
    devices = apply_extras([_dev("heizstab"), _dev("wallbox")], load_extras(db))
    by_name = {d.name: d for d in devices}
    assert len(by_name["heizstab"].extras) == 1
    assert by_name["wallbox"].extras == ()  # ohne Konfiguration leer


def test_suggestion_conflict_detects_same_target_sensor():
    db = _db()
    upsert_extra(
        db, device_name="heizstab", read_entity_id="input_number.min_soc_auto", ai_suggestion=True
    )
    extras_map = load_extras(db)
    # Ein anderes Gerät mit derselben object_id würde denselben Vorschlags-Sensor erzeugen.
    clash = suggestion_conflict(
        extras_map, device_name="wallbox", read_entity_id="sensor.min_soc_auto"
    )
    assert clash == "input_number.min_soc_auto"
    # Der Eintrag selbst kollidiert nicht mit sich (Update-Fall).
    assert suggestion_conflict(
        extras_map, device_name="heizstab", read_entity_id="input_number.min_soc_auto"
    ) is None


def test_seed_defaults_seeds_heizstab_once():
    db = _db()
    devices = [_dev("heizstab"), _dev("wallbox")]
    assert seed_defaults(db, devices) is True
    extras = load_extras(db)
    assert "heizstab" in extras
    seeded = extras["heizstab"][0]
    assert seeded.read_entity_id == "input_number.e3dc_heizstab_maxtemperatur"
    assert seeded.ai_suggestion is False
    assert seeded.can_suggest is False
    assert seeded.suggestion_entity_id == "sensor.ep_e3dc_heizstab_maxtemperatur_vorschlag"
    # Zweiter Aufruf seedet nicht erneut (Marker gesetzt).
    assert seed_defaults(db, devices) is False


def test_seed_defaults_not_reseeded_after_user_deletes():
    db = _db()
    devices = [_dev("heizstab")]
    seed_defaults(db, devices)
    delete_extra(
        db, device_name="heizstab", read_entity_id="input_number.e3dc_heizstab_maxtemperatur"
    )
    assert seed_defaults(db, devices) is False  # Marker verhindert Wiederkehr
    assert load_extras(db) == {}


def test_seed_defaults_noop_without_heizstab():
    db = _db()
    assert seed_defaults(db, [_dev("wallbox")]) is False
    assert load_extras(db) == {}
