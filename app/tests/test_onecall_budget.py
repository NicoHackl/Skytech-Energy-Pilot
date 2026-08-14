"""Tests für den persistenten Tages-Call-Budget-Zähler der One Call API 4.0 (O2)."""

from energy_pilot import onecall_budget
from energy_pilot.database import init_db


def test_empty_db_reports_zero_and_full_budget():
    db = init_db(":memory:")
    assert onecall_budget.calls_today(db, now_day="2026-06-26") == 0
    assert onecall_budget.remaining(db, 1000, now_day="2026-06-26") == 1000


def test_consume_accumulates_within_same_day():
    db = init_db(":memory:")
    onecall_budget.consume(db, 2, now_day="2026-06-26")
    onecall_budget.consume(db, 3, now_day="2026-06-26")
    assert onecall_budget.calls_today(db, now_day="2026-06-26") == 5
    assert onecall_budget.remaining(db, 10, now_day="2026-06-26") == 5


def test_remaining_never_negative():
    db = init_db(":memory:")
    onecall_budget.consume(db, 7, now_day="2026-06-26")
    assert onecall_budget.remaining(db, 5, now_day="2026-06-26") == 0


def test_counter_resets_on_new_utc_day():
    db = init_db(":memory:")
    onecall_budget.consume(db, 4, now_day="2026-06-26")
    assert onecall_budget.calls_today(db, now_day="2026-06-26") == 4
    # Neuer Tag → Zähler beginnt wieder bei 0 (OWM-Quota-Reset um Mitternacht UTC).
    assert onecall_budget.calls_today(db, now_day="2026-06-27") == 0
    # Verbrauch am neuen Tag baut auf 0 auf, überschreibt den alten Tag.
    onecall_budget.consume(db, 1, now_day="2026-06-27")
    assert onecall_budget.calls_today(db, now_day="2026-06-27") == 1


def test_consume_without_db_is_noop():
    # Ohne DB blockiert nichts (eiserne Regel 13); Zähler bleibt 0/Budget voll.
    onecall_budget.consume(None, 5, now_day="2026-06-26")
    assert onecall_budget.calls_today(None, now_day="2026-06-26") == 0
    assert onecall_budget.remaining(None, 1000, now_day="2026-06-26") == 1000


def test_consume_zero_or_negative_is_noop():
    db = init_db(":memory:")
    onecall_budget.consume(db, 0, now_day="2026-06-26")
    onecall_budget.consume(db, -3, now_day="2026-06-26")
    assert onecall_budget.calls_today(db, now_day="2026-06-26") == 0


def test_corrupt_value_treated_as_unset():
    db = init_db(":memory:")
    from energy_pilot.settings import set_setting
    set_setting(db, onecall_budget.ONECALL_BUDGET_KEY, "kein-json")
    assert onecall_budget.calls_today(db, now_day="2026-06-26") == 0


def test_persists_across_fresh_connection(tmp_path):
    db_path = str(tmp_path / "ep.db")
    db1 = init_db(db_path)
    onecall_budget.consume(db1, 6, now_day="2026-06-26")
    db1.close()
    # „Neustart": frische Connection auf dieselbe Datei → Zähler bleibt erhalten.
    db2 = init_db(db_path)
    assert onecall_budget.calls_today(db2, now_day="2026-06-26") == 6
