"""Tests für die Persistenz der KI-Beschreibung je Gerät (D-051)."""

from energy_pilot.database import init_db
from energy_pilot.device_extras import apply_extras, load_extras
from energy_pilot.device_prompts import (
    get_device_prompt,
    load_device_prompts,
    set_device_prompt,
)
from energy_pilot.devices import CONTROLLABLE, Device


def _db():
    return init_db(":memory:")


def _dev(name="heizstab"):
    return Device(name, name.title(), name, CONTROLLABLE, "watt")


def test_set_and_get_roundtrip():
    db = _db()
    assert set_device_prompt(db, "heizstab", "  Versorgt die Fußbodenheizung.  ") is True
    assert get_device_prompt(db, "heizstab") == "Versorgt die Fußbodenheizung."
    assert load_device_prompts(db) == {"heizstab": "Versorgt die Fußbodenheizung."}


def test_set_updates_existing():
    db = _db()
    set_device_prompt(db, "heizstab", "alt")
    assert set_device_prompt(db, "heizstab", "neu") is True
    assert get_device_prompt(db, "heizstab") == "neu"
    # Kein Duplikat: PRIMARY KEY auf device_name.
    assert list(load_device_prompts(db)) == ["heizstab"]


def test_empty_prompt_deletes():
    db = _db()
    set_device_prompt(db, "heizstab", "text")
    assert set_device_prompt(db, "heizstab", "   ") is False  # nur Whitespace = löschen
    assert get_device_prompt(db, "heizstab") == ""
    assert load_device_prompts(db) == {}


def test_get_missing_is_empty_string():
    db = _db()
    assert get_device_prompt(db, "unbekannt") == ""


def test_load_skips_empty():
    db = _db()
    set_device_prompt(db, "a", "hat text")
    set_device_prompt(db, "b", "")  # löscht -> nicht in load
    assert load_device_prompts(db) == {"a": "hat text"}


def test_none_db_is_noop():
    assert set_device_prompt(None, "x", "y") is False
    assert get_device_prompt(None, "x") == ""
    assert load_device_prompts(None) == {}


def test_apply_extras_merges_prompt_onto_device():
    db = _db()
    set_device_prompt(db, "heizstab", "Funktion X")
    devices = apply_extras(
        [_dev("heizstab"), _dev("wallbox")], load_extras(db), load_device_prompts(db)
    )
    by_name = {d.name: d for d in devices}
    assert by_name["heizstab"].ai_prompt == "Funktion X"
    assert by_name["wallbox"].ai_prompt == ""  # ohne Prompt leer


def test_apply_extras_without_prompts_arg_defaults_empty():
    # Rückwärtskompatibel: alter 2-Argument-Aufruf lässt ai_prompt leer.
    devices = apply_extras([_dev("heizstab")], {})
    assert devices[0].ai_prompt == ""
