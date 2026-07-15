"""Tests für user-definierte Ziele + deren Gewichtung aus der Klassifizierung (D-055)."""

from energy_pilot.database import init_db
from energy_pilot.objectives import (
    Objective,
    delete_ziel,
    load_ziele,
    objectives_from_classification,
    upsert_ziel,
)


def _db():
    return init_db(":memory:")


def test_load_ziele_empty_without_data():
    assert load_ziele(_db()) == []


def test_upsert_creates_and_load_roundtrips():
    db = _db()
    ziel = upsert_ziel(
        db, ziel_id=None, name="Warmwasserkomfort",
        beschreibung="Genug warmes Wasser sicherstellen", devices=["heizstab"],
    )
    assert ziel.id is not None
    loaded = load_ziele(db)
    assert len(loaded) == 1
    assert loaded[0].name == "Warmwasserkomfort"
    assert loaded[0].beschreibung == "Genug warmes Wasser sicherstellen"
    assert loaded[0].devices == ("heizstab",)


def test_upsert_with_id_updates_existing_row():
    db = _db()
    ziel = upsert_ziel(db, ziel_id=None, name="A", beschreibung="", devices=[])
    upsert_ziel(db, ziel_id=ziel.id, name="B", beschreibung="neu", devices=["batterie"])
    loaded = load_ziele(db)
    assert len(loaded) == 1
    assert loaded[0].name == "B"
    assert loaded[0].beschreibung == "neu"
    assert loaded[0].devices == ("batterie",)


def test_delete_ziel_removes_row():
    db = _db()
    ziel = upsert_ziel(db, ziel_id=None, name="A", beschreibung="", devices=[])
    upsert_ziel(db, ziel_id=None, name="B", beschreibung="", devices=[])
    delete_ziel(db, ziel.id)
    names = {z.name for z in load_ziele(db)}
    assert names == {"B"}


def test_objectives_from_classification_maps_id_to_key_and_name_to_label():
    db = _db()
    ziel = upsert_ziel(db, ziel_id=None, name="Netzbezug minimieren", devices=[])
    result = objectives_from_classification([ziel], {str(ziel.id): 77})
    assert result == [Objective(key=str(ziel.id), label="Netzbezug minimieren", weight=77)]


def test_objectives_from_classification_clamps_out_of_range_weight():
    db = _db()
    ziel = upsert_ziel(db, ziel_id=None, name="X", devices=[])
    result = objectives_from_classification([ziel], {str(ziel.id): 250})
    assert result[0].weight == 100
    result = objectives_from_classification([ziel], {str(ziel.id): -5})
    assert result[0].weight == 0


def test_objectives_from_classification_defaults_missing_or_invalid_to_50():
    db = _db()
    ziel = upsert_ziel(db, ziel_id=None, name="X", devices=[])
    assert objectives_from_classification([ziel], {})[0].weight == 50
    assert objectives_from_classification([ziel], {str(ziel.id): "abc"})[0].weight == 50


def test_objectives_from_classification_is_safe_against_non_dict_gewichtung():
    db = _db()
    ziel = upsert_ziel(db, ziel_id=None, name="X", devices=[])
    result = objectives_from_classification([ziel], "kein_dict")
    assert result[0].weight == 50
