"""Tests für die deterministische Anti-Flatter-Schicht (A2 / Validator Stufe 5)."""

from datetime import UTC, datetime, timedelta

from energy_pilot.constraints import build_constraints
from energy_pilot.devices import CONTROLLABLE, Device
from energy_pilot.validator import StabilityLimits, smooth_plan

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def _cmap(*, heizstab_frei=True):
    """Gerät->Constraint für Batterie + Heizstab (Freigabe des Heizstabs einstellbar)."""
    devices = [
        Device("batterie", "Batterie", "batterie", CONTROLLABLE, "watt"),
        Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt"),
    ]
    readings = {
        "batterie": {
            "technische_freigabe": {"value": True},
            "min_technisch": {"value": 0.0},
            "max_technisch": {"value": 8000.0},
        },
        "heizstab": {
            "technische_freigabe": {"value": heizstab_frei},
            "min_technisch": {"value": 0.0},
            "max_technisch": {"value": 3000.0},
        },
    }
    return {c.name: c for c in build_constraints(devices, readings)}


# --- Delta-Limit -----------------------------------------------------------------------------

def test_delta_clamp_limits_power_growth():
    # Heizstab: +100 % gewünscht, ±20 % erlaubt -> auf 1200 geklemmt.
    devices = [{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                "geschutzte_mindestleistung_w_vorschlag": 2000.0}]
    prev = {"heizstab": {"geschutzte_mindestleistung_w_vorschlag": 1000.0}}
    res = smooth_plan(devices, prev, _cmap(), {}, limits=StabilityLimits(), now=NOW)
    assert devices[0]["geschutzte_mindestleistung_w_vorschlag"] == 1200.0
    assert any("Delta-Limit" in n for n in res.notes)


def test_delta_clamp_uses_battery_percent():
    # Batterie hat den engeren Satz (±10 %): 3000 -> gewünscht 3600 -> auf 3300 geklemmt.
    devices = [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3600.0}]
    prev = {"batterie": {"geschutzte_mindestleistung_w_vorschlag": 3000.0}}
    res = smooth_plan(devices, prev, _cmap(), {}, limits=StabilityLimits(), now=NOW)
    assert devices[0]["geschutzte_mindestleistung_w_vorschlag"] == 3300.0
    assert any("Delta-Limit ±10%" in n for n in res.notes)


def test_delta_clamp_skips_without_previous_plan():
    # Erster Lauf (kein Vorplan) -> keine Delta-Klemmung, Wert bleibt.
    devices = [{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True,
                "geschutzte_mindestleistung_w_vorschlag": 9999.0}]
    res = smooth_plan(devices, {}, _cmap(), {}, limits=StabilityLimits(), now=NOW)
    assert devices[0]["geschutzte_mindestleistung_w_vorschlag"] == 9999.0
    assert not any("Delta-Limit" in n for n in res.notes)


# --- Freigabe-Hysterese ----------------------------------------------------------------------

def test_freigabe_hysteresis_holds_until_n_runs():
    limits = StabilityLimits(hysteresis_runs=2, min_hold_minutes=0)
    state = {"heizstab": {"last_freigabe": 1, "last_prio": 10,
                          "pending_freigabe": None, "pending_count": 0, "last_change_ts": None}}
    # Lauf 1: Kandidat false -> Wechsel gehalten (bleibt true).
    d1 = [{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": False,
           "geschutzte_mindestleistung_w_vorschlag": 500.0}]
    r1 = smooth_plan(d1, {}, _cmap(), state, limits=limits, now=NOW)
    assert d1[0]["freigabe_vorschlag"] is True
    assert any("gehalten" in n for n in r1.notes)
    # Lauf 2: gleicher Kandidat -> Hysterese bestätigt, jetzt false.
    d2 = [{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": False,
           "geschutzte_mindestleistung_w_vorschlag": 500.0}]
    r2 = smooth_plan(d2, {}, _cmap(), r1.state, limits=limits, now=NOW)
    assert d2[0]["freigabe_vorschlag"] is False
    assert any("Hysterese bestätigt" in n for n in r2.notes)


def test_hysteresis_counter_resets_on_flip_flopping_candidate():
    # Wechselnder Kandidat setzt den Zähler zurück -> kein vorzeitiger Flip.
    limits = StabilityLimits(hysteresis_runs=2, min_hold_minutes=0)
    state = {"heizstab": {"last_freigabe": 1, "last_prio": 10,
                          "pending_freigabe": 0, "pending_count": 1, "last_change_ts": None}}
    # Kandidat springt zurück auf true == letzter Wert -> keine Änderung, Kandidat weg.
    d = [{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True,
          "geschutzte_mindestleistung_w_vorschlag": 500.0}]
    res = smooth_plan(d, {}, _cmap(), state, limits=limits, now=NOW)
    assert d[0]["freigabe_vorschlag"] is True
    assert res.state["heizstab"]["pending_count"] == 0


def test_min_hold_blocks_recent_change():
    # Zähler erreicht, aber letzte Änderung erst vor 5 min (Haltezeit 15) -> gehalten.
    limits = StabilityLimits(hysteresis_runs=1, min_hold_minutes=15)
    recent = (NOW - timedelta(minutes=5)).isoformat()
    state = {"heizstab": {"last_freigabe": 1, "last_prio": 10,
                          "pending_freigabe": 0, "pending_count": 1, "last_change_ts": recent}}
    d = [{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": False,
          "geschutzte_mindestleistung_w_vorschlag": 500.0}]
    res = smooth_plan(d, {}, _cmap(), state, limits=limits, now=NOW)
    assert d[0]["freigabe_vorschlag"] is True
    assert any("Mindesthaltezeit" in n for n in res.notes)


def test_safety_never_holds_true_when_technically_locked():
    # Technisch gesperrt: der Wechsel auf false greift sofort, trotz Hysterese/Haltezeit.
    limits = StabilityLimits(hysteresis_runs=5, min_hold_minutes=60)
    state = {"heizstab": {"last_freigabe": 1, "last_prio": 10, "pending_freigabe": None,
                          "pending_count": 0, "last_change_ts": NOW.isoformat()}}
    d = [{"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": False,
          "geschutzte_mindestleistung_w_vorschlag": 500.0}]
    res = smooth_plan(d, {}, _cmap(heizstab_frei=False), state, limits=limits, now=NOW)
    assert d[0]["freigabe_vorschlag"] is False
    assert any("Sicherheit" in n for n in res.notes)


def test_battery_without_freigabe_contract_is_untouched():
    # Batterie hat keine Freigabe im Schreibvertrag -> Hysterese lässt sie in Ruhe.
    d = [{"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0}]
    res = smooth_plan(d, {}, _cmap(), {}, limits=StabilityLimits(), now=NOW)
    assert res.state["batterie"]["last_freigabe"] is None
    assert res.notes == []
