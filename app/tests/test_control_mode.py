"""Tests für die Modus-Achse (D-057): Wahrheitstabelle + fail-safes Lesen.

Die Wahrheitstabelle ist gegen `SkytechHEMS/app/ems/devices.py` (`Device.resolve_source`)
gespiegelt – weicht sie ab, laufen HEMS und EP auseinander und ein Gerät auf `manuell` bekäme
im schlimmsten Fall doch einen KI-Wert ins Original geschrieben.
"""

import pytest

from energy_pilot.control_mode import (
    HA_GLOBAL_MODE,
    device_mode_entity,
    read_modes,
    read_sources,
    resolve_source,
)
from energy_pilot.devices import CONTROLLABLE, Device
from energy_pilot.http_errors import HTTPStatusError

DEVICES = [Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt")]


class _FakeHA:
    """Liefert Modus-Zustände; unbekannte Entität => HTTP 404 (wie HA)."""

    def __init__(self, states=None, fail_for=None):
        self._states = dict(states or {})
        self._fail_for = set(fail_for or ())
        self.reads = []

    async def get_state(self, entity_id):
        self.reads.append(entity_id)
        if entity_id in self._fail_for:
            raise HTTPStatusError(service="Home Assistant", status=500, reason="Server Error")
        if entity_id not in self._states:
            raise HTTPStatusError(service="Home Assistant", status=404, reason="Not Found")
        return {"entity_id": entity_id, "state": self._states[entity_id]}


# -- Wahrheitstabelle (rein) -----------------------------------------------


@pytest.mark.parametrize(
    ("global_mode", "device_mode", "expected"),
    [
        # global "aus" schlägt alles
        ("aus", "auto", "aus"),
        ("aus", "manuell", "aus"),
        ("aus", None, "aus"),
        # Per-Gerät-Kill gilt immer – auch gegen global "auto"
        ("auto", "aus", "aus"),
        ("manuell", "aus", "aus"),
        # global "auto" erzwingt KI auf allen Geräten (überstimmt Gerät "manuell")
        ("auto", "auto", "ep"),
        ("auto", "manuell", "ep"),
        ("auto", None, "ep"),
        # global "manuell"/"nur_*" delegiert an das Gerät
        ("manuell", "auto", "ep"),
        ("manuell", "manuell", "user"),
        ("manuell", None, "user"),
        ("nur_heizen", "auto", "ep"),
        ("nur_heizen", "manuell", "user"),
        ("nur_laden", None, "user"),
        # fehlender globaler Modus => "aus" (HEMS: `st.get(...) or "aus"`)
        (None, "auto", "aus"),
        (None, "manuell", "aus"),
        ("", "auto", "aus"),
    ],
)
def test_resolve_source_truth_table(global_mode, device_mode, expected):
    assert resolve_source(global_mode, device_mode) == expected


def test_device_mode_entity_naming():
    assert device_mode_entity("heizstab") == "input_select.ems_heizstab_modus"


# -- Lesen aus HA (fail-safe) ----------------------------------------------


async def test_read_sources_resolves_per_device():
    ha = _FakeHA({HA_GLOBAL_MODE: "manuell", "input_select.ems_heizstab_modus": "auto"})
    assert await read_sources(ha, DEVICES) == {"heizstab": "ep"}


async def test_read_modes_exposes_raw_mode_for_display():
    ha = _FakeHA({HA_GLOBAL_MODE: "manuell", "input_select.ems_heizstab_modus": "manuell"})
    modes = await read_modes(ha, DEVICES)
    assert modes["heizstab"] == {"global_mode": "manuell", "mode": "manuell", "source": "user"}


async def test_read_sources_without_devices_reads_nothing():
    ha = _FakeHA({HA_GLOBAL_MODE: "auto"})
    assert await read_sources(ha, []) == {}
    assert ha.reads == []  # ohne Geräte auch keinen globalen Modus lesen


async def test_read_sources_without_ha_client_blocks():
    assert await read_sources(None, DEVICES) == {"heizstab": "aus"}


async def test_read_sources_global_read_error_blocks_all():
    ha = _FakeHA(
        {HA_GLOBAL_MODE: "auto", "input_select.ems_heizstab_modus": "auto"},
        fail_for={HA_GLOBAL_MODE},
    )
    assert await read_sources(ha, DEVICES) == {"heizstab": "aus"}


async def test_read_sources_missing_global_helper_blocks_all():
    ha = _FakeHA({"input_select.ems_heizstab_modus": "auto"})  # globaler Helfer fehlt => 404
    assert await read_sources(ha, DEVICES) == {"heizstab": "aus"}


async def test_read_sources_unavailable_global_blocks_all():
    ha = _FakeHA({HA_GLOBAL_MODE: "unavailable", "input_select.ems_heizstab_modus": "auto"})
    assert await read_sources(ha, DEVICES) == {"heizstab": "aus"}


async def test_read_sources_missing_device_helper_falls_through():
    """404 am Geräte-Helfer = Helfer nicht angelegt => Durchfall wie im HEMS, kein 'aus'."""
    ha = _FakeHA({HA_GLOBAL_MODE: "manuell"})
    assert await read_sources(ha, DEVICES) == {"heizstab": "user"}
    ha_auto = _FakeHA({HA_GLOBAL_MODE: "auto"})
    assert await read_sources(ha_auto, DEVICES) == {"heizstab": "ep"}


async def test_read_sources_device_read_error_blocks_only_that_device():
    """Ein HA-Fehler (500) ist kein fehlender Helfer: fail-safe 'aus'."""
    ha = _FakeHA(
        {HA_GLOBAL_MODE: "auto", "input_select.ems_heizstab_modus": "auto"},
        fail_for={"input_select.ems_heizstab_modus"},
    )
    assert await read_sources(ha, DEVICES) == {"heizstab": "aus"}


async def test_read_sources_unavailable_device_mode_falls_through():
    ha = _FakeHA({HA_GLOBAL_MODE: "manuell", "input_select.ems_heizstab_modus": "unknown"})
    assert await read_sources(ha, DEVICES) == {"heizstab": "user"}
