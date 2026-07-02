"""Gerätemodell und -Discovery des Energy Pilot.

EP liest pro Gerät die vom User gepflegten technischen `ems_*`-Werte (Decision
D-029/D-031). Die konkreten Entity-IDs werden **ausschließlich** aus dem HEMS-Schema
(`/api/device_controls_schema`, D-036) erkannt – die Geräte werden vollständig vom
HEMS gezogen. Einen Geräte-Fallback in der Addon-Config gibt es nicht mehr (D-046):
ist das HEMS beim Start nicht erreichbar, kennt EP keine Geräte. Der Webserver
wiederholt die Discovery dann automatisch (begrenzt) und stellt einen manuellen
HEMS-Sync (Button im HEMS-Tab) bereit.

Das Read-Schema ist gegen den HEMS-Quellcode verifiziert
(SkytechHEMS app/main.py `_ctrl_items_controllable`/`_ctrl_items_binary`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from energy_pilot.hems_client import HEMSClient
from energy_pilot.logging_setup import log

CONTROLLABLE = "controllable"
BINARY = "binary"

# Prefix steckt im stabilen Suffix `_technische_freigabe` (existiert in beiden Klassen).
_PREFIX_RE = re.compile(r"\.ems_(?P<prefix>.+)_technische_freigabe$")


@dataclass(frozen=True)
class Device:
    """Ein vom HEMS geregeltes Gerät aus EP-Sicht."""

    name: str
    label: str
    entity_prefix: str
    device_class: str  # CONTROLLABLE | BINARY
    output_unit: str = "watt"  # "watt" | "ampere"


@dataclass(frozen=True)
class ReadField:
    """Eine von EP gelesene Gerätegröße inkl. abgeleiteter HA-Entität."""

    key: str
    label: str
    kind: str  # "bool" | "number"
    entity_id: str
    unit: str = ""


def _unit_suffix(output_unit: str) -> str:
    return "a" if output_unit == "ampere" else "w"


def read_fields(device: Device) -> list[ReadField]:
    """Leitet die EP-relevanten Lese-Entitäten eines Geräts ab (Read-Schema D-029)."""
    p = device.entity_prefix
    u = _unit_suffix(device.output_unit)
    unit_label = "A" if device.output_unit == "ampere" else "W"
    freigabe = ReadField(
        "technische_freigabe",
        "Technische Freigabe",
        "bool",
        f"input_boolean.ems_{p}_technische_freigabe",
    )

    if device.device_class == BINARY:
        fields = [
            ReadField(
                "leistung_w", "Ist-Leistung", "number",
                f"input_number.ems_{p}_leistung_w", "W",
            ),
            freigabe,
        ]
    else:  # CONTROLLABLE (inkl. Batterie)
        fields = [
            freigabe,
            ReadField(
                "min_technisch", "Min. Leistung (technisch)", "number",
                f"input_number.ems_{p}_min_technisch_{u}", unit_label,
            ),
            ReadField(
                "max_technisch", "Max. Leistung (technisch)", "number",
                f"input_number.ems_{p}_max_technisch_{u}", unit_label,
            ),
        ]

    # Heizstab-Sonderfall (D-035): EP-eigener Grenzwert-Helfer, den EP liest.
    if device.entity_prefix == "heizstab":
        fields.append(
            ReadField(
                "ep_max_temperatur", "EP max. Wassertemperatur (Grenzwert)", "number",
                "input_number.ep_heizstab_max_temperatur", "°C",
            )
        )
    return fields


def _default_label(name: str) -> str:
    return name.replace("_", " ").title()


def discover_from_hems_schema(schema: list[dict]) -> list[Device]:
    """Baut die Geräteliste aus dem HEMS-Kontrollschema (D-036).

    Klasse und Einheit werden aus den vorhandenen `ems_*`-Items abgeleitet:
    `_min_technisch_*` => controllable, sonst `_leistung_w` => binary;
    `_*_a` => Ampere, sonst Watt.
    """
    devices: list[Device] = []
    for group in schema:
        label = (group.get("label") or "").strip()
        if label.lower() == "global":
            continue
        entities = [item.get("entity", "") for item in group.get("items", [])]

        prefix = next(
            (m.group("prefix") for e in entities if (m := _PREFIX_RE.search(e))),
            None,
        )
        if not prefix:
            continue

        # Geräteidentität (D-029): stabiler technischer `name` aus dem HEMS-Schema.
        # `label` ist nur Anzeigename und darf ohne Folgen umbenannt werden. Ältere
        # HEMS-Versionen liefern kein `name` – dann auf das Entitätspräfix zurückfallen.
        name = (group.get("name") or "").strip() or prefix

        has_min_technisch = any(re.search(r"_min_technisch_[wa]$", e) for e in entities)
        has_leistung = any(e.endswith("_leistung_w") for e in entities)
        if has_min_technisch:
            device_class = CONTROLLABLE
        elif has_leistung:
            device_class = BINARY
        else:
            continue

        is_ampere = any(re.search(r"_(?:min|max)_technisch_a$", e) for e in entities)
        output_unit = "ampere" if is_ampere else "watt"

        devices.append(
            Device(
                name=name,
                label=label or _default_label(name),
                entity_prefix=prefix,
                device_class=device_class,
                output_unit=output_unit,
            )
        )
    return devices


async def discover(
    hems_client: HEMSClient | None,
    logger: logging.Logger | None = None,
) -> tuple[list[Device], str]:
    """Erkennt die Geräte ausschließlich über das HEMS-Kontrollschema (D-036).

    Liefert die Geräteliste und die Quelle ("hems" | "none"). Ist das HEMS nicht
    erreichbar oder liefert es keine Geräte, ist die Liste leer (Quelle "none") –
    einen Addon-Config-Fallback gibt es nicht mehr (D-046); die Geräte werden
    vollständig vom HEMS gezogen. Der Aufrufer wiederholt die Discovery bei "none"
    (Auto-Retry) bzw. stößt sie manuell über den HEMS-Sync neu an.
    """
    if hems_client is not None:
        try:
            schema = await hems_client.device_schema()
            devices = discover_from_hems_schema(schema)
            if devices:
                return devices, "hems"
        except Exception as exc:
            if logger:
                log(
                    logger, "warning",
                    "HEMS-Geräteschema nicht abrufbar – keine Geräte erkannt",
                    context={"error": str(exc)},
                )
    return [], "none"
