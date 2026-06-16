"""Tests für die gleitende Mittelwertbildung."""

from energy_pilot.aggregation import RollingAggregator


def test_means_over_windows():
    agg = RollingAggregator()
    now = 10_000.0
    # Werte in unterschiedlichem Alter ablegen
    agg.add("pv", 100.0, now - 3000)  # nur im 60-min-Fenster
    agg.add("pv", 200.0, now - 800)   # im 15- und 60-min-Fenster
    agg.add("pv", 300.0, now - 30)    # in allen Fenstern

    means = agg.means("pv", now)
    assert means[60] == 300.0
    assert means[900] == 250.0  # (200 + 300) / 2
    assert means[3600] == 200.0  # (100 + 200 + 300) / 3


def test_latest_value():
    agg = RollingAggregator()
    agg.add("soc", 55.0, 1.0)
    agg.add("soc", 60.0, 2.0)
    assert agg.latest("soc") == 60.0


def test_old_samples_are_pruned():
    agg = RollingAggregator()
    now = 10_000.0
    agg.add("pv", 1.0, now - 5000)  # älter als 60 min -> wird verworfen
    agg.add("pv", 2.0, now)
    assert agg.means("pv", now)[3600] == 2.0


def test_empty_key_returns_none():
    agg = RollingAggregator()
    assert agg.latest("missing") is None
    assert agg.mean("missing", 60, 1.0) is None
