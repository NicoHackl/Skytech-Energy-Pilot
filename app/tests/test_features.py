"""Tests für die gerechneten Geräte- und Systemmerkmale (D-066).

Leitfall ist das Beispiel des Users: **dieselben 65 °C**, zwei entgegengesetzte richtige
Entscheidungen — je nachdem, ob der Speicher in den Tagen davor ohne Strom gewonnen oder
verloren hat.
"""

from energy_pilot.device_speicher import SpeicherDaten
from energy_pilot.features import (
    ELEKTRISCH_SCHWELLE_KWH,
    HOT_WATER_ROLE,
    base_load_w,
    build_device_features,
    build_system_features,
)

SPEICHER = SpeicherDaten(volumen_liter=300.0, komfort_min_c=45.0, ziel_c=60.0)


def _state(ist_c=65.0):
    return {
        HOT_WATER_ROLE: {"label": "Warmwassertemperatur", "unit": "°C", "latest": ist_c},
        "house_load": {"label": "Hausverbrauch", "unit": "W", "latest": 800.0},
    }


def _tag(tag, *, ww_delta, wolken=None, strom_kwh=None):
    groessen = {HOT_WATER_ROLE: {"delta": ww_delta, "min": 50.0, "max": 70.0, "mittel": 60.0}}
    if wolken is not None:
        groessen["wolken"] = {"mittel": wolken}
    if strom_kwh is not None:
        groessen["heizstab_energie"] = {"energie_kwh": strom_kwh}
    return {"tag": tag, "vollstaendig": True, "groessen": groessen}


def test_reserve_and_demand_are_energy_not_degrees():
    """65 °C bei Komfortminimum 45 °C und 300 l sind rund 7 kWh Reserve."""
    merkmale = build_device_features("heizstab", SPEICHER, _state(65.0), [])
    assert merkmale.reserve_kwh == 6.97
    # Ziel 60 °C, Ist 65 °C ⇒ kein Bedarf (nicht negativ).
    assert merkmale.energiebedarf_kwh == 0.0
    assert merkmale.fehlt == ()


def test_demand_when_below_target():
    merkmale = build_device_features("heizstab", SPEICHER, _state(50.0), [])
    assert merkmale.energiebedarf_kwh == 3.49  # 300 l um 10 K
    assert merkmale.reserve_kwh == 1.74  # 300 l um 5 K über dem Minimum


def test_sunny_days_yield_no_coverage_limit():
    """Fall 1 des Users: Speicher gewinnt ohne Strom ⇒ keine Deckungsgrenze, kein Handlungsdruck."""
    rueckblick = [
        _tag("2026-08-12", ww_delta=8.0, wolken=15.0, strom_kwh=0.0),
        _tag("2026-08-13", ww_delta=7.0, wolken=20.0, strom_kwh=0.0),
        _tag("2026-08-14", ww_delta=9.0, wolken=10.0, strom_kwh=0.0),
    ]
    merkmale = build_device_features(
        "heizstab", SPEICHER, _state(65.0), rueckblick,
        strom_quellen=("heizstab_energie",),
    )
    assert len(merkmale.fremdwaerme_tage) == 3
    assert merkmale.fremdwaerme_mittel_kwh > 0
    assert merkmale.deckung_tage is None
    assert any("gewonnen" in h for h in merkmale.hinweise)


def test_cloudy_days_yield_a_coverage_in_days():
    """Fall 2 des Users: Speicher verliert ohne Strom ⇒ Deckung in Tagen wird konkret."""
    rueckblick = [
        _tag("2026-08-12", ww_delta=-4.0, wolken=70.0, strom_kwh=0.0),
        _tag("2026-08-13", ww_delta=-4.0, wolken=80.0, strom_kwh=0.0),
    ]
    merkmale = build_device_features(
        "heizstab", SPEICHER, _state(65.0), rueckblick,
        strom_quellen=("heizstab_energie",),
    )
    # -4 K/Tag bei 300 l ≈ -1,39 kWh/Tag; Reserve 6,97 kWh ⇒ rund 5 Tage.
    assert merkmale.fremdwaerme_mittel_kwh == -1.39
    assert merkmale.deckung_tage == 5.0


def test_days_with_electric_input_are_excluded_from_the_measurement():
    """An einem Tag mit laufendem Heizstab lässt sich Fremdwärme nicht trennen."""
    rueckblick = [
        _tag("2026-08-12", ww_delta=12.0, wolken=60.0, strom_kwh=4.0),  # geheizt -> raus
        _tag("2026-08-13", ww_delta=-3.0, wolken=70.0, strom_kwh=0.0),
    ]
    merkmale = build_device_features(
        "heizstab", SPEICHER, _state(65.0), rueckblick,
        strom_quellen=("heizstab_energie",),
    )
    assert [t.tag for t in merkmale.fremdwaerme_tage] == ["2026-08-13"]


def test_measurement_noise_does_not_count_as_heating():
    """Ein Zähler rauscht im Hundertstelbereich; das ist kein Heizbetrieb."""
    assert ELEKTRISCH_SCHWELLE_KWH == 0.1
    rueckblick = [_tag("2026-08-13", ww_delta=6.0, strom_kwh=0.014)]
    merkmale = build_device_features(
        "heizstab", SPEICHER, _state(), rueckblick, strom_quellen=("heizstab_energie",)
    )
    assert len(merkmale.fremdwaerme_tage) == 1


def test_missing_values_are_named_not_silently_zero():
    """Eiserne Regel 13: fehlende Angaben werden benannt, nicht als 0 ausgegeben."""
    merkmale = build_device_features("heizstab", SpeicherDaten(), _state(65.0), [])
    assert merkmale.reserve_kwh is None
    assert merkmale.energiebedarf_kwh is None
    assert set(merkmale.fehlt) == {"volumen_liter", "komfort_min_c"}


def test_missing_temperature_role_is_reported():
    merkmale = build_device_features("heizstab", SPEICHER, {}, [])
    assert merkmale.ist_c is None
    assert f"Mess-Rolle {HOT_WATER_ROLE}" in merkmale.fehlt


def test_missing_electric_source_is_flagged():
    """Ohne elektrische Energiegröße ist die Fremdwärme-Messung nicht abgesichert."""
    merkmale = build_device_features(
        "heizstab", SPEICHER, _state(), [_tag("2026-08-13", ww_delta=5.0)]
    )
    assert any("keine elektrische Energiegröße" in h for h in merkmale.hinweise)


def test_energy_without_volume_stays_none():
    """Ohne Volumen bleiben die Fremdwärme-Tage in °C, ohne erfundene kWh."""
    speicher = SpeicherDaten(komfort_min_c=45.0)
    merkmale = build_device_features(
        "heizstab", speicher, _state(), [_tag("2026-08-13", ww_delta=-4.0)],
        strom_quellen=("heizstab_energie",),
    )
    assert merkmale.fremdwaerme_tage[0].delta_c == -4.0
    assert merkmale.fremdwaerme_tage[0].energie_kwh is None
    assert merkmale.deckung_tage is None


# --- Systemmerkmale ---------------------------------------------------------------------------


def _load_days(*minima):
    return [
        {"tag": f"2026-08-{10 + i}", "groessen": {"house_load": {"min": value}}}
        for i, value in enumerate(minima)
    ]


def test_base_load_is_the_mean_of_daily_minima():
    assert base_load_w(_load_days(300.0, 340.0, 320.0)) == 320.0
    assert base_load_w([]) is None


def test_surplus_subtracts_the_base_load():
    forecast = {"unit": "kWh", "values": [{"key": "tomorrow", "total": 10.0}]}
    merkmale = build_system_features(forecast, _load_days(250.0, 250.0))
    assert merkmale["grundlast_w"] == 250.0
    assert merkmale["grundlast_kwh_pro_tag"] == 6.0
    assert merkmale["ueberschuss"]["morgen_kwh"] == 4.0


def test_surplus_is_absent_without_base_load():
    """Die Bruttoprognose als „Überschuss" auszugeben wäre eine stille Übertreibung."""
    forecast = {"unit": "kWh", "values": [{"key": "tomorrow", "total": 10.0}]}
    merkmale = build_system_features(forecast, [])
    assert "ueberschuss" not in merkmale
    assert "Bruttowert" in merkmale["hinweis"]
