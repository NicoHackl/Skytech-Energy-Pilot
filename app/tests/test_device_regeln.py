"""Tests für die Persistenz der Freitext-Betriebsregeln (D-060)."""

from energy_pilot.database import init_db
from energy_pilot.device_extras import apply_extras, load_extras
from energy_pilot.device_prompts import set_device_prompt
from energy_pilot.device_regeln import (
    get_device_regeln,
    get_global_regeln,
    load_device_regeln,
    set_device_regeln,
    set_global_regeln,
)
from energy_pilot.devices import CONTROLLABLE, Device

_REGEL = (
    "Steht die Warmwassertemperatur über 70 °C oder werden die nächsten zwei Tage über 25 °C "
    "warm, bleibt der Heizstab gesperrt."
)


def _db():
    return init_db(":memory:")


def _dev(name="heizstab"):
    return Device(name, name.title(), name, CONTROLLABLE, "watt")


def test_set_and_get_roundtrip():
    db = _db()
    assert set_device_regeln(db, "heizstab", f"  {_REGEL}  ") is True
    assert get_device_regeln(db, "heizstab") == _REGEL
    assert load_device_regeln(db) == {"heizstab": _REGEL}


def test_empty_text_deletes_the_entry():
    db = _db()
    set_device_regeln(db, "heizstab", _REGEL)
    assert set_device_regeln(db, "heizstab", "   ") is False
    assert get_device_regeln(db, "heizstab") == ""
    assert load_device_regeln(db) == {}


def test_missing_device_and_missing_db_are_harmless():
    db = _db()
    assert get_device_regeln(db, "gibtsnicht") == ""
    assert set_device_regeln(None, "heizstab", _REGEL) is False
    assert load_device_regeln(None) == {}
    assert get_device_regeln(None, "heizstab") == ""


def test_global_regeln_roundtrip():
    db = _db()
    assert get_global_regeln(db) == ""
    assert set_global_regeln(db, "  Im Sommer keine elektrische Nachheizung.  ") == (
        "Im Sommer keine elektrische Nachheizung."
    )
    assert get_global_regeln(db) == "Im Sommer keine elektrische Nachheizung."
    assert set_global_regeln(db, "") == ""
    assert get_global_regeln(db) == ""


def test_apply_extras_attaches_regeln_separately_from_description():
    """Regeln (was der User will) und Beschreibung (was das Gerät ist) bleiben getrennt."""
    db = _db()
    set_device_regeln(db, "heizstab", _REGEL)
    set_device_prompt(db, "heizstab", "Elektrischer Heizstab im Warmwasserspeicher.")

    devices = apply_extras(
        [_dev()], load_extras(db),
        {"heizstab": "Elektrischer Heizstab im Warmwasserspeicher."},
        load_device_regeln(db),
    )

    assert devices[0].ai_regeln == _REGEL
    assert devices[0].ai_prompt == "Elektrischer Heizstab im Warmwasserspeicher."


def test_device_without_regeln_keeps_empty_text():
    devices = apply_extras([_dev("wallbox")], {}, {}, {})
    assert devices[0].ai_regeln == ""
