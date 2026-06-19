"""State Collector: liest konfigurierte HA-Entitäten und verdichtet ihre Werte.

Liest pro Rolle die zugeordnete Live-Entität, fällt bei fehlendem/ungültigem
Wert auf den konfigurierten Fallback zurück und reicht gültige Werte an den
RollingAggregator weiter (Decision D-001/D-006).
"""

from __future__ import annotations

import asyncio
import logging
import time

from energy_pilot.aggregation import RollingAggregator
from energy_pilot.conversion import safe_float
from energy_pilot.entity_map import EntityMapping
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import log
from energy_pilot.roles import Role


class StateCollector:
    """Sammelt Messwerte und stellt eine Momentaufnahme für UI/API bereit."""

    def __init__(
        self,
        ha_client: HAClient | None,
        aggregator: RollingAggregator,
        roles: tuple[Role, ...],
        logger: logging.Logger | None = None,
    ) -> None:
        self.ha_client = ha_client
        self.aggregator = aggregator
        self.roles = roles
        self.logger = logger
        self.mapping: dict[str, EntityMapping] = {}
        # Quelle des zuletzt erfassten Werts je Rolle: live | fallback | none
        self.last_source: dict[str, str] = {}
        # Diagnose: Zeitpunkt des letzten Laufs und letzter Lesefehler
        self.last_collect_ts: float | None = None
        self.last_error: str | None = None

    def set_mapping(self, mapping: dict[str, EntityMapping]) -> None:
        self.mapping = mapping

    async def collect_once(self, now: float | None = None) -> dict[str, str]:
        """Erfasst für jede Rolle einen Wert und aktualisiert den Aggregator."""
        now = time.time() if now is None else now
        for role in self.roles:
            value, source = await self._read_role(role)
            if value is not None:
                self.aggregator.add(role.key, value, now)
            self.last_source[role.key] = source
        self.last_collect_ts = now
        return dict(self.last_source)

    async def _read_role(self, role: Role) -> tuple[float | None, str]:
        mapping = self.mapping.get(role.key)
        if mapping is None:
            return None, "none"

        if mapping.entity_id and self.ha_client is not None:
            try:
                state = await self.ha_client.get_state(mapping.entity_id)
                value = safe_float(state.get("state"))
                if value is not None:
                    return value, "live"
            except Exception as exc:
                self.last_error = f"{role.key} ({mapping.entity_id}): {exc}"
                if self.logger:
                    log(
                        self.logger,
                        "warning",
                        "Entität konnte nicht gelesen werden",
                        context={"role": role.key, "entity": mapping.entity_id, "error": str(exc)},
                    )

        if mapping.fallback_value is not None:
            return mapping.fallback_value, "fallback"
        return None, "none"

    def snapshot(self, now: float | None = None) -> dict[str, dict]:
        """Aktuelle Werte je Rolle inkl. Mittelwerte (gemittelte Rollen)."""
        now = time.time() if now is None else now
        result: dict[str, dict] = {}
        for role in self.roles:
            entry: dict[str, object] = {
                "label": role.label,
                "unit": role.unit,
                "averaged": role.averaged,
                "source": self.last_source.get(role.key, "none"),
            }
            if role.averaged:
                means = self.aggregator.means(role.key, now)
                entry["latest"] = self.aggregator.latest(role.key)
                entry["mean_1m"] = means[60]
                entry["mean_15m"] = means[900]
                entry["mean_60m"] = means[3600]
            else:
                entry["value"] = self.aggregator.latest(role.key)
            result[role.key] = entry
        return result


async def run_poller(
    collector: StateCollector,
    interval_s: float,
    logger: logging.Logger | None = None,
    device_collector: object | None = None,
) -> None:
    """Periodischer Sammellauf, bis die Aufgabe abgebrochen wird.

    Erfasst je Zyklus die Haus-Messgrößen und – falls vorhanden – die
    Gerätewerte. Jeder Collector wird einzeln gekapselt, damit ein Fehler im
    einen den anderen nicht ausfällt.
    """
    while True:
        for component in (collector, device_collector):
            if component is None:
                continue
            try:
                await component.collect_once()
            except Exception as exc:
                if logger:
                    log(logger, "error", "Sammellauf fehlgeschlagen", context={"error": str(exc)})
        await asyncio.sleep(interval_s)
