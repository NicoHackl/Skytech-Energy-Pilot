"""Modus-Achse: entscheidet, ob ein KI-Vorschlag in die Original-Entität darf (D-057).

Das HEMS unterscheidet global (`input_select.ems_regelmodus`) und je Gerät
(`input_select.ems_<prefix>_modus`) zwischen KI- und manuellem Betrieb. Semantik überall
gleich: **`auto` = KI/EP**, **`manuell` = normale Regeln**, **`aus` = aus**. EP liest diese
`ems_*`-Helfer nur (D-029) und spiegelt die HEMS-Logik hier nach, damit der
Original-Schreibweg (D-052, „In Original schreiben") einen vom User gepflegten Wert im
manuellen Modus niemals überschreibt.

`resolve_source()` ist eine Portierung von `SkytechHEMS/app/ems/devices.py`
(`Device.resolve_source`) — auf die reine Modus-Achse reduziert: `ems_pv_regelung_aktiv`,
`hard_lockout` und das `allowed_modes`-Typ-Gate bleiben bewusst außen vor. Zusatz-Entitäten
sind advisorisch und nicht HEMS-relevant (D-047); `hard_lockout` ist ein PV-Notabwurf, keine
Nutzeraussage über die KI-Übernahme, und `allowed_modes` steht in der HEMS-Addon-Config, die
EP nicht kennt.

Fail-safe: Ist der Modus nicht sicher feststellbar (Helfer fehlt, `unavailable`, HA-Fehler),
gilt `aus` — dann wird nicht geschrieben. Hier zeigt Iron Rule 8 nach innen: nicht schreiben
ist der sichere Zustand, weil der Nutzerwert stehen bleibt.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from energy_pilot.conversion import INVALID_STATES
from energy_pilot.http_errors import HTTPStatusError
from energy_pilot.logging_setup import log

if TYPE_CHECKING:
    from energy_pilot.devices import Device
    from energy_pilot.ha_client import HAClient

# Globaler Regelmodus (HEMS-Domäne, EP liest nur). Entspricht HA_GLOBAL_MODE im HEMS.
HA_GLOBAL_MODE = "input_select.ems_regelmodus"

# Steuerquellen (identische Werte wie im HEMS-Status, damit UI/Logs vergleichbar bleiben).
SOURCE_OFF = "aus"
SOURCE_USER = "user"
SOURCE_EP = "ep"


def device_mode_entity(entity_prefix: str) -> str:
    """Modus-Helfer eines Geräts: `input_select.ems_<prefix>_modus`."""
    return f"input_select.ems_{entity_prefix}_modus"


def resolve_source(global_mode: str | None, device_mode: str | None) -> str:
    """Steuerquelle bestimmen: 'aus' | 'user' | 'ep'.

    Präzedenz exakt wie im HEMS (`app/ems/devices.py`), inklusive der bewussten Asymmetrie:
      - global "aus"/fehlt  -> 'aus' (schlägt alles)
      - Gerät "aus"         -> 'aus' (Per-Gerät-Kill gilt immer, auch bei global "auto")
      - global "auto"       -> 'ep' für alle Geräte; überstimmt Gerät "manuell"
      - Gerät "auto"        -> 'ep' (bei global "manuell"/"nur_*" entscheidet das Gerät)
      - sonst               -> 'user'

    Ein fehlender Geräte-Helfer (`None`) fällt auf 'user' durch — der Nutzerwert bleibt stehen.
    Ein fehlender **globaler** Modus (`None`) gilt dagegen als "aus" und sperrt jedes Gerät;
    das entspricht dem HEMS (`controller.py`: `st.get(HA_GLOBAL_MODE) or "aus"`) und verhindert,
    dass ein Gerät auf "auto" ohne globalen Helfer stillschweigend zu 'ep' würde.
    """
    if not global_mode or global_mode == "aus":
        return SOURCE_OFF
    if device_mode == "aus":
        return SOURCE_OFF
    if global_mode == "auto":
        return SOURCE_EP
    if device_mode == "auto":
        return SOURCE_EP
    return SOURCE_USER


async def _read_mode(ha_client: HAClient, entity_id: str) -> str | None:
    """Liest einen Modus-Helfer; `None` bei fehlender Entität oder Ungültig-Zustand.

    Ein **fehlender Helfer** (HTTP 404) ergibt `None` und damit denselben Durchfall wie im HEMS,
    wo `StateProxy.get()` für eine unbekannte Entität `None` liefert. Alle anderen HA-Fehler
    (500, Timeout, …) fliegen weiter und werden vom Aufrufer fail-safe zu 'aus' aufgelöst — ein
    kaputtes HA ist etwas anderes als ein bewusst nicht angelegter Helfer.
    """
    try:
        state = await ha_client.get_state(entity_id)
    except HTTPStatusError as exc:
        if exc.status == 404:
            return None
        raise
    raw = state.get("state") if isinstance(state, dict) else None
    if raw is None:
        return None
    text = str(raw).strip()
    return None if text.lower() in INVALID_STATES else text


def _blocked(devices: list[Device], global_mode: str | None) -> dict[str, dict]:
    """Alle Geräte gesperrt (globaler Modus unbekannt/nicht lesbar)."""
    return {
        device.name: {"global_mode": global_mode, "mode": None, "source": SOURCE_OFF}
        for device in devices
    }


async def read_modes(
    ha_client: HAClient | None,
    devices: list[Device],
    *,
    logger: logging.Logger | None = None,
) -> dict[str, dict]:
    """Liest den Modus global und je Gerät und löst die Steuerquelle auf.

    Liefert `device.name -> {global_mode, mode, source}`; `mode` ist der rohe Gerätezustand
    (für die Anzeige), `source` die aufgelöste Quelle `'aus' | 'user' | 'ep'` (für das Gate).

    Wirft nie (Iron Rule 8): jeder Lesefehler wird gefangen und fail-safe zu 'aus' aufgelöst,
    damit ein HA-Aussetzer nie zum Überschreiben eines Nutzerwerts führt.

    Ohne HA-Client oder ohne lesbaren globalen Modus gilt für **alle** Geräte 'aus' — das
    entspricht dem HEMS, das den globalen Modus ebenfalls zu "aus" auflöst, wenn der Helfer
    fehlt. Da das HEMS ohne diesen Helfer gar nicht regelt, kann er in einer laufenden Anlage
    nicht fehlen; tut er es doch, ist die Warnung der Hinweis darauf.
    """
    if not devices:  # ohne Geräte gibt es nichts zu entscheiden – auch den globalen nicht lesen
        return {}
    if ha_client is None:
        return _blocked(devices, None)

    try:
        global_mode = await _read_mode(ha_client, HA_GLOBAL_MODE)
    except Exception as exc:  # kontrolliert: HA-Fehler blockiert nie, sperrt aber das Schreiben
        if logger is not None:
            log(
                logger, "warning",
                "Globaler Regelmodus nicht lesbar – Original-Schreibweg gesperrt",
                context={"entity": HA_GLOBAL_MODE, "error": str(exc)},
            )
        return _blocked(devices, None)

    if global_mode is None:
        if logger is not None:
            log(
                logger, "warning",
                "Globaler Regelmodus fehlt oder ist unbekannt – Original-Schreibweg gesperrt",
                context={"entity": HA_GLOBAL_MODE},
            )
        return _blocked(devices, None)

    modes: dict[str, dict] = {}
    for device in devices:
        entity_id = device_mode_entity(device.entity_prefix)
        try:
            device_mode = await _read_mode(ha_client, entity_id)
        except Exception as exc:  # Helfer fehlt/HA-Fehler => fail-safe, kein Schreiben
            if logger is not None:
                log(
                    logger, "warning",
                    "Gerätemodus nicht lesbar – Original-Schreibweg für dieses Gerät gesperrt",
                    context={"entity": entity_id, "device": device.name, "error": str(exc)},
                )
            modes[device.name] = {
                "global_mode": global_mode, "mode": None, "source": SOURCE_OFF
            }
            continue
        modes[device.name] = {
            "global_mode": global_mode,
            "mode": device_mode,
            "source": resolve_source(global_mode, device_mode),
        }
    return modes


async def read_sources(
    ha_client: HAClient | None,
    devices: list[Device],
    *,
    logger: logging.Logger | None = None,
) -> dict[str, str]:
    """Steuerquelle je Gerät: `device.name -> 'aus' | 'user' | 'ep'` (Gate-Sicht auf
    `read_modes`)."""
    modes = await read_modes(ha_client, devices, logger=logger)
    return {name: entry["source"] for name, entry in modes.items()}
