"""Tests für die Persistenz der Wärmespeicher-Kennwerte (D-066)."""

from energy_pilot.database import init_db
from energy_pilot.device_speicher import (
    SpeicherDaten,
    get_speicher,
    load_speicher,
    set_speicher,
)


def _db():
    return init_db(":memory:")


def test_roundtrip():
    db = _db()
    daten = set_speicher(
        db, "heizstab", volumen_liter=300.0, komfort_min_c=45.0, ziel_c=60.0
    )
    assert daten.rechenbar is True
    gelesen = get_speicher(db, "heizstab")
    assert gelesen == SpeicherDaten(volumen_liter=300.0, komfort_min_c=45.0, ziel_c=60.0)
    assert load_speicher(db) == {"heizstab": gelesen}


def test_update_overwrites():
    db = _db()
    set_speicher(db, "heizstab", volumen_liter=200.0, komfort_min_c=40.0)
    set_speicher(db, "heizstab", volumen_liter=300.0, komfort_min_c=45.0, ziel_c=60.0)
    assert get_speicher(db, "heizstab").volumen_liter == 300.0
    assert get_speicher(db, "heizstab").ziel_c == 60.0


def test_all_empty_removes_the_entry():
    db = _db()
    set_speicher(db, "heizstab", volumen_liter=300.0, komfort_min_c=45.0)
    set_speicher(db, "heizstab", volumen_liter=None, komfort_min_c=None, ziel_c=None)
    assert load_speicher(db) == {}
    assert get_speicher(db, "heizstab") == SpeicherDaten()


def test_empty_string_means_not_maintained_not_zero():
    """Ein leeres Formularfeld darf nicht als 0 Liter oder 0 °C ankommen."""
    db = _db()
    daten = set_speicher(db, "heizstab", volumen_liter="", komfort_min_c="  ", ziel_c=None)
    assert daten == SpeicherDaten()
    assert load_speicher(db) == {}


def test_unparseable_values_are_ignored():
    db = _db()
    daten = set_speicher(db, "heizstab", volumen_liter="dreihundert", komfort_min_c=45.0)
    assert daten.volumen_liter is None
    assert daten.komfort_min_c == 45.0
    assert daten.rechenbar is False
    assert daten.fehlende_felder == ("volumen_liter",)


def test_partial_data_is_kept_but_not_computable():
    """Nur das Volumen reicht nicht: ohne Komfortminimum gibt es keine Reserve."""
    db = _db()
    daten = set_speicher(db, "heizstab", volumen_liter=300.0, komfort_min_c=None)
    assert daten.gepflegt is True
    assert daten.rechenbar is False
    assert daten.fehlende_felder == ("komfort_min_c",)
    assert get_speicher(db, "heizstab").volumen_liter == 300.0


def test_missing_device_and_missing_db_are_harmless():
    db = _db()
    assert get_speicher(db, "gibtsnicht") == SpeicherDaten()
    assert load_speicher(None) == {}
    assert get_speicher(None, "heizstab") == SpeicherDaten()
    # Ohne DB wird nichts gespeichert, aber die Werte kommen normalisiert zurück.
    assert set_speicher(
        None, "heizstab", volumen_liter=300.0, komfort_min_c=45.0
    ).rechenbar is True


def test_boolean_is_not_a_number():
    """`True` wäre in Python 1.0 — als Volumen offensichtlich falsch."""
    db = _db()
    daten = set_speicher(db, "heizstab", volumen_liter=True, komfort_min_c=False)
    assert daten == SpeicherDaten()
