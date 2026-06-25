"""Tests für den persistenten Key/Value-Speicher (config-Tabelle)."""

from energy_pilot.database import init_db
from energy_pilot.settings import delete_setting, get_setting, set_setting


def test_get_missing_returns_none():
    db = init_db(":memory:")
    assert get_setting(db, "planning_prompt") is None


def test_set_get_roundtrip_and_upsert():
    db = init_db(":memory:")
    set_setting(db, "planning_prompt", "Hallo")
    assert get_setting(db, "planning_prompt") == "Hallo"
    # UPSERT: erneutes Setzen überschreibt, ohne PK-Konflikt.
    set_setting(db, "planning_prompt", "Neu")
    assert get_setting(db, "planning_prompt") == "Neu"


def test_delete_setting():
    db = init_db(":memory:")
    set_setting(db, "planning_prompt", "Weg damit")
    delete_setting(db, "planning_prompt")
    assert get_setting(db, "planning_prompt") is None


def test_none_db_is_noop():
    assert get_setting(None, "x") is None
    set_setting(None, "x", "y")  # darf nicht crashen
    delete_setting(None, "x")
