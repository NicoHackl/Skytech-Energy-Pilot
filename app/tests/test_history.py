"""Tests für die Tages-Aggregation des Rückblicks (D-065)."""

from datetime import UTC, date, datetime, timedelta

from energy_pilot.history import (
    KIND_COUNTER,
    KIND_LEVEL,
    KIND_POWER,
    LOCAL_TZ,
    MAX_GAP_S,
    aggregate_day,
    day_bounds,
    days_in_window,
    kind_for_unit,
    local_date,
    parse_samples,
    water_energy_kwh,
)

TAG = date(2026, 8, 14)


def _rows(*pairs):
    """HA-Verlaufszeilen (Ortszeit-Stunde, Wert) in der Form, die `/api/history` liefert."""
    return [
        {
            "state": str(value),
            "last_changed": datetime(
                TAG.year, TAG.month, TAG.day, hour, tzinfo=LOCAL_TZ
            ).isoformat(),
        }
        for hour, value in pairs
    ]


def test_kind_follows_unit():
    assert kind_for_unit("W") == KIND_POWER
    assert kind_for_unit("kWh") == KIND_COUNTER
    assert kind_for_unit("°C") == KIND_LEVEL
    assert kind_for_unit("") == KIND_LEVEL
    assert kind_for_unit(None) == KIND_LEVEL


def test_day_bounds_are_local_calendar_days():
    """Grenzen sind der lokale Kalendertag, zurückgegeben als UTC (siehe Docstring dort)."""
    start, ende = day_bounds(TAG)
    assert start.astimezone(LOCAL_TZ).isoformat() == "2026-08-14T00:00:00+02:00"
    assert ende.astimezone(LOCAL_TZ).isoformat() == "2026-08-15T00:00:00+02:00"


def test_day_bounds_survive_dst_change():
    """Ein Tag ist über die Zeitumstellung 23 bzw. 25 Stunden lang — nicht immer 24.

    Regression: mit beiden Grenzen in derselben `ZoneInfo` rechnete Python die Wanduhr-Differenz
    (24 h) und die Umstellung fiel aus dem zeitgewichteten Mittel und der Energie heraus.
    """
    # Umstellung auf Sommerzeit: letzter Sonntag im März 2026 = 29.03.
    start, ende = day_bounds(date(2026, 3, 29))
    assert (ende - start) == timedelta(hours=23)
    # Umstellung auf Winterzeit: letzter Sonntag im Oktober 2026 = 25.10.
    start, ende = day_bounds(date(2026, 10, 25))
    assert (ende - start) == timedelta(hours=25)


def test_level_aggregate_uses_time_weighted_mean():
    """Ein Temperaturfühler meldet unregelmäßig; ein Mittel über Proben wäre verzerrt.

    20 °C gelten von 00:00 bis 22:00 (22 h), 60 °C nur die letzten 2 h. Arithmetisch wären das
    40 °C, zeitgewichtet rund 23,6 °C — letzteres beschreibt den Tag.
    """
    aggregat = aggregate_day(parse_samples(_rows((0, 20.0), (22, 60.0))), TAG, KIND_LEVEL)
    assert aggregat.wert_min == 20.0
    assert aggregat.wert_max == 60.0
    assert aggregat.wert_delta == 40.0
    assert 23.0 < aggregat.wert_mittel < 24.0
    assert aggregat.energie_kwh is None  # eine Temperatur hat keine Energie
    assert aggregat.proben == 2


def test_counter_aggregate_uses_daily_difference():
    aggregat = aggregate_day(parse_samples(_rows((0, 100.0), (12, 104.5))), TAG, KIND_COUNTER)
    assert aggregat.energie_kwh == 4.5
    assert aggregat.wert_delta == 4.5


def test_counter_reset_does_not_produce_negative_energy():
    """Ein Zähler-Reset ist kein Energierückfluss."""
    aggregat = aggregate_day(parse_samples(_rows((0, 100.0), (12, 3.0))), TAG, KIND_COUNTER)
    assert aggregat.energie_kwh == 0.0


def test_power_aggregate_integrates_to_kwh():
    """1000 W über eine Stunde sind 1 kWh; danach 0 W.

    Regression: HA speichert nur Änderungen, ein Abstand von einer Stunde ist der Normalfall.
    Eine zu enge Lückengrenze (erste Fassung: 900 s) verwarf genau diesen Fall und verschluckte
    die Tagesenergie.
    """
    samples = [
        (datetime(2026, 8, 14, 10, tzinfo=LOCAL_TZ), 1000.0),
        (datetime(2026, 8, 14, 11, tzinfo=LOCAL_TZ), 0.0),
    ]
    aggregat = aggregate_day(samples, TAG, KIND_POWER)
    assert aggregat.energie_kwh == 1.0


def test_power_gap_beyond_the_limit_is_not_extrapolated():
    """Ein stundenlanger Ausfall darf nicht als konstante Last hochgerechnet werden."""
    assert MAX_GAP_S == 21600.0  # 6 h
    samples = [
        (datetime(2026, 8, 14, 2, tzinfo=LOCAL_TZ), 2000.0),
        (datetime(2026, 8, 14, 20, tzinfo=LOCAL_TZ), 0.0),
    ]
    aggregat = aggregate_day(samples, TAG, KIND_POWER)
    # 18 h Abstand > MAX_GAP_S ⇒ die 2000 W zählen nicht durch.
    assert aggregat.energie_kwh == 0.0


def test_samples_outside_the_day_are_ignored():
    samples = [
        (datetime(2026, 8, 13, 23, 30, tzinfo=LOCAL_TZ), 5.0),
        (datetime(2026, 8, 14, 12, tzinfo=LOCAL_TZ), 50.0),
        (datetime(2026, 8, 15, 0, 30, tzinfo=LOCAL_TZ), 99.0),
    ]
    aggregat = aggregate_day(samples, TAG, KIND_LEVEL)
    assert aggregat.proben == 1
    assert aggregat.wert_max == 50.0


def test_empty_day_is_marked_empty_not_zero():
    """Kein Wert heißt „unbekannt", nicht 0 — sonst kippt jede Bilanz."""
    aggregat = aggregate_day([], TAG, KIND_LEVEL)
    assert aggregat.leer is True
    assert aggregat.wert_min is None
    assert aggregat.energie_kwh is None


def test_parse_samples_drops_unusable_rows():
    rows = [
        {"state": "unavailable", "last_changed": "2026-08-14T10:00:00+02:00"},
        {"state": "unknown", "last_changed": "2026-08-14T10:05:00+02:00"},
        {"state": "Standby", "last_changed": "2026-08-14T10:10:00+02:00"},
        {"state": "21.5"},  # kein Zeitstempel
        {"state": "21.5", "last_updated": "2026-08-14T10:15:00+02:00"},  # nur last_updated
    ]
    samples = parse_samples(rows)
    assert len(samples) == 1
    assert samples[0][1] == 21.5


def test_parse_samples_sorts_by_time():
    rows = _rows((12, 2.0), (6, 1.0), (18, 3.0))
    assert [value for _m, value in parse_samples(rows)] == [1.0, 2.0, 3.0]


def test_days_in_window_is_oldest_first_and_includes_today():
    now = datetime(2026, 8, 14, 22, 30, tzinfo=UTC)  # 00:30 Ortszeit am 15.08.
    assert local_date(now) == date(2026, 8, 15)
    assert days_in_window(now, 3) == [date(2026, 8, 13), date(2026, 8, 14), date(2026, 8, 15)]
    assert days_in_window(now, 0) == [date(2026, 8, 15)]


def test_water_energy_matches_hand_calculation():
    """200 l um 5 K erwärmen ≈ 1,16 kWh (m·c·ΔT)."""
    assert round(water_energy_kwh(200.0, 5.0), 2) == 1.16
    # Negative Differenz = Entnahme, das Vorzeichen bleibt erhalten.
    assert water_energy_kwh(200.0, -5.0) < 0
    assert water_energy_kwh(0.0, 5.0) == 0.0
