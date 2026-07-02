"""Device Collector: liest pro Gerät die technischen `ems_*`-Werte aus HA.

Die Gerätewerte sind Grenzen/Zustände und werden als Letztwert geführt (kein
gleitendes Mittel, konsistent mit Decision D-001). Quelle je Wert wird
mitgeführt (`live` | `none`), damit UI/Diagnose Lücken sichtbar machen.
"""

from __future__ import annotations

import logging
import time

from energy_pilot.conversion import INVALID_STATES, safe_float
from energy_pilot.devices import Device, ReadField, read_fields
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import log

# HA-`input_boolean`-Zustände in einen Wahrheitswert übersetzen.
_TRUE_STATES = frozenset({"on", "true", "1"})
_FALSE_STATES = frozenset({"off", "false", "0"})


def parse_bool(value: object) -> bool | None:
    """Wandelt einen HA-Zustand in bool; liefert None bei ungültigen Werten."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_STATES:
        return True
    if text in _FALSE_STATES:
        return False
    return None


def parse_text(value: object) -> str | None:
    """Liefert den bereinigten Textzustand (für datetime/text/auto); None bei Ungültig-Zuständen."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in INVALID_STATES:
        return None
    return text


def parse_by_kind(kind: str, raw: object) -> object | None:
    """Interpretiert einen HA-Rohzustand gemäß Zusatz-Entität-Typ (D-048)."""
    if kind == "bool":
        return parse_bool(raw)
    if kind == "number":
        return safe_float(raw)
    if kind == "auto":  # sensor u.ä.: Zahl wenn möglich, sonst Text
        num = safe_float(raw)
        return num if num is not None else parse_text(raw)
    return parse_text(raw)  # datetime | text


class DeviceCollector:
    """Liest die `ems_*`-Werte aller erkannten Geräte und stellt sie bereit."""

    def __init__(self, ha_client: HAClient | None, logger: logging.Logger | None = None) -> None:
        self.ha_client = ha_client
        self.logger = logger
        self.devices: list[Device] = []
        self.discovery_source: str = "none"
        # device.name -> field.key -> {"value": ..., "source": "live|none"}
        self.last_values: dict[str, dict[str, dict]] = {}
        self.last_collect_ts: float | None = None
        self.last_error: str | None = None

    def set_devices(self, devices: list[Device], source: str = "none") -> None:
        self.devices = devices
        self.discovery_source = source

    async def collect_once(self, now: float | None = None) -> None:
        """Liest für jedes Gerät alle Lese-Entitäten einmal ein."""
        now = time.time() if now is None else now
        for device in self.devices:
            field_values: dict[str, dict] = {}
            for field in read_fields(device):
                value, source, attrs = await self._read_field(field)
                field_values[field.key] = {"value": value, "source": source, "attrs": attrs}
            self.last_values[device.name] = field_values
        self.last_collect_ts = now

    async def _read_field(self, field: ReadField) -> tuple[object | None, str, dict]:
        """Liest Zustand (typgerecht, D-048) + die je Typ relevanten HA-Attribute."""
        if self.ha_client is None:
            return None, "none", {}
        try:
            state = await self.ha_client.get_state(field.entity_id)
            value = parse_by_kind(field.kind, state.get("state"))
            attrs = {}
            if field.capture_attrs:
                raw_attrs = state.get("attributes") or {}
                attrs = {k: raw_attrs[k] for k in field.capture_attrs if k in raw_attrs}
            if value is not None:
                return value, "live", attrs
            return None, "none", attrs
        except Exception as exc:
            self.last_error = f"{field.entity_id}: {exc}"
            if self.logger:
                log(
                    self.logger, "warning", "Gerätewert konnte nicht gelesen werden",
                    context={"entity": field.entity_id, "error": str(exc)},
                )
        return None, "none", {}

    def snapshot(self) -> list[dict]:
        """Aktuelle Werte je Gerät für UI/API (read-only).

        `fields` enthält nur die Standard-`ems_*`-Lesewerte; user-gepflegte Zusatz-Entitäten
        (D-047) werden separat (`/api/devices` → `extras`) geführt, damit sie im UI nicht doppelt
        (Standard-Tabelle **und** Zusatz-Editor) erscheinen. Gelesen werden sie dennoch (siehe
        `collect_once`).
        """
        result: list[dict] = []
        for device in self.devices:
            values = self.last_values.get(device.name, {})
            extra_keys = {ex.read_key for ex in device.extras}
            fields_out = []
            for field in read_fields(device):
                if field.key in extra_keys:
                    continue
                current = values.get(field.key, {"value": None, "source": "none"})
                fields_out.append(
                    {
                        "key": field.key,
                        "label": field.label,
                        "kind": field.kind,
                        "unit": field.unit,
                        "entity_id": field.entity_id,
                        "value": current["value"],
                        "source": current["source"],
                    }
                )
            result.append(
                {
                    "name": device.name,
                    "label": device.label,
                    "class": device.device_class,
                    "output_unit": device.output_unit,
                    "fields": fields_out,
                }
            )
        return result
