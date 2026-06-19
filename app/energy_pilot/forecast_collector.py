"""Forecast Collector: liest die PV-Prognosesensoren und summiert je Wert.

Pro Ausrichtung werden die konfigurierten Sensoren als Letztwert gelesen (kein
gleitendes Mittel, konsistent mit Decision D-001). Für jeden der vier Wert-Typen
bildet EP die Summe über alle Ausrichtungen mit gültigem Messwert (D-018).
"""

from __future__ import annotations

import logging
import time

from energy_pilot.conversion import safe_float
from energy_pilot.forecast import PV_VALUES, PVOrientation
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import log


class ForecastCollector:
    """Liest die PV-Prognose aller Ausrichtungen und stellt Summen bereit."""

    def __init__(
        self,
        ha_client: HAClient | None,
        logger: logging.Logger | None = None,
        unit: str = "kWh",
    ) -> None:
        self.ha_client = ha_client
        self.logger = logger
        self.unit = unit
        self.orientations: list[PVOrientation] = []
        # orientation.label -> value_key -> {"value", "source", "entity_id"}
        self.last_values: dict[str, dict[str, dict]] = {}
        self.last_collect_ts: float | None = None
        self.last_error: str | None = None

    def set_orientations(self, orientations: list[PVOrientation]) -> None:
        self.orientations = orientations

    async def collect_once(self, now: float | None = None) -> None:
        """Liest für jede Ausrichtung die konfigurierten Sensoren einmal ein."""
        now = time.time() if now is None else now
        for orientation in self.orientations:
            values: dict[str, dict] = {}
            for value_key, entity_id in orientation.entities.items():
                value, source = await self._read(entity_id)
                values[value_key] = {"value": value, "source": source, "entity_id": entity_id}
            self.last_values[orientation.label] = values
        self.last_collect_ts = now

    async def _read(self, entity_id: str) -> tuple[float | None, str]:
        if self.ha_client is None:
            return None, "none"
        try:
            state = await self.ha_client.get_state(entity_id)
            value = safe_float(state.get("state"))
            if value is not None:
                return value, "live"
        except Exception as exc:
            self.last_error = f"{entity_id}: {exc}"
            if self.logger:
                log(
                    self.logger, "warning", "Prognosewert konnte nicht gelesen werden",
                    context={"entity": entity_id, "error": str(exc)},
                )
        return None, "none"

    def snapshot(self) -> dict:
        """Summen je Wert-Typ plus Aufschlüsselung pro Ausrichtung (read-only)."""
        totals = []
        for value in PV_VALUES:
            numbers = [
                fv["value"]
                for orientation in self.orientations
                if (fv := self.last_values.get(orientation.label, {}).get(value.key))
                and fv["value"] is not None
            ]
            totals.append(
                {
                    "key": value.key,
                    "label": value.label,
                    "unit": self.unit,
                    "total": sum(numbers) if numbers else None,
                }
            )

        orientations_out = []
        for orientation in self.orientations:
            stored = self.last_values.get(orientation.label, {})
            values = {
                value.key: stored.get(
                    value.key,
                    {"value": None, "source": "none", "entity_id": orientation.entities[value.key]},
                )
                for value in PV_VALUES
                if value.key in orientation.entities
            }
            orientations_out.append({"label": orientation.label, "values": values})

        return {"unit": self.unit, "values": totals, "orientations": orientations_out}
