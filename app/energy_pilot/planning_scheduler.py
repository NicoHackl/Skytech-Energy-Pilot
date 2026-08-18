"""Interner, rollierender Scheduler für den Energy Pilot.

Er startet erst, wenn HEMS-Discovery und erste Haus-/Geräte-Snapshots erfolgreich waren. Der
Planner selbst serialisiert automatische und manuelle Läufe; dieser Scheduler bestimmt nur die
Fälligkeit und hält Providerfehler bis zum nächsten regulären Intervall zurück.
"""

from __future__ import annotations

import asyncio
import logging
import time

from energy_pilot.logging_setup import log


class PlanningScheduler:
    """Stündlicher Planungstakt mit testbarer Einzel-Tick-Schnittstelle."""

    def __init__(
        self,
        planner: object,
        collector: object,
        device_collector: object,
        *,
        interval_min: float = 60,
        logger: logging.Logger | None = None,
        clock=time.monotonic,
    ) -> None:
        self.planner = planner
        self.collector = collector
        self.device_collector = device_collector
        self.interval_s = max(60.0, float(interval_min) * 60.0)
        self.logger = logger
        self.clock = clock
        self.last_attempt: float | None = None
        self.last_success: float | None = None
        self.last_error: str | None = None
        self._restored = False
        self._ha_connected: bool | None = None
        self._stop = asyncio.Event()
        self._tick_lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        """HEMS-Geräte und beide für Entscheidungen nötigen Snapshots liegen vor."""
        return (
            getattr(self.device_collector, "discovery_source", "none") == "hems"
            and bool(getattr(self.device_collector, "devices", ()))
            and getattr(self.collector, "last_collect_ts", None) is not None
            and getattr(self.device_collector, "last_collect_ts", None) is not None
        )

    def due(self, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        return self.last_attempt is None or now - self.last_attempt >= self.interval_s

    async def tick(self, *, force: bool = False, now: float | None = None):
        """Führt höchstens einen fälligen Lauf aus; fehlende Bereitschaft ist ein No-op."""
        if self._tick_lock.locked():
            return None
        async with self._tick_lock:
            return await self._tick(force=force, now=now)

    async def _tick(self, *, force: bool = False, now: float | None = None):
        """Interner Tick unter dem Parallelitätsschutz."""
        if not self.ready:
            return None
        moment = self.clock() if now is None else now

        # Der HA-Verbindungstest läuft auch zwischen zwei Planungszeitpunkten. So wird ein noch
        # gültiger Plan nach einem HA-Neustart beziehungsweise einer Verbindungsunterbrechung
        # zeitnah erneut publiziert, ohne dafür einen zusätzlichen KI-Lauf zu starten.
        reconnected = await self._probe_reconnected()
        if not self._restored or reconnected:
            self._restored = True
            try:
                await self.planner.publish_latest()
            except Exception as exc:  # noqa: BLE001 - Wiederherstellung darf Start nie blockieren
                self.last_error = str(exc).strip() or exc.__class__.__name__

        if not force and not self.due(moment):
            return None

        self.last_attempt = moment
        try:
            result = await self.planner.run()
        except Exception as exc:  # noqa: BLE001 - kontrollierter Scheduler-Rand
            self.last_error = str(exc).strip() or exc.__class__.__name__
            if self.logger is not None:
                log(
                    self.logger,
                    "error",
                    "Automatische Planung fehlgeschlagen",
                    context={"error": self.last_error},
                    exc_info=exc,
                )
            return None
        if getattr(result, "ok", False):
            self.last_success = moment
            self.last_error = None
        else:
            self.last_error = str(getattr(result, "error", None) or "Planung ungültig")
        return result

    async def _probe_reconnected(self) -> bool:
        """Erkennt eine HA-Wiederverbindung; ohne testbaren Client bleibt der Pfad inaktiv."""
        client = getattr(self.planner, "ha_client", None)
        probe = getattr(client, "test_connection", None)
        if not callable(probe):
            return False
        try:
            await probe()
        except Exception:  # noqa: BLE001 - der reguläre Poller diagnostiziert die Ursache
            self._ha_connected = False
            return False
        reconnected = self._ha_connected is False
        self._ha_connected = True
        return reconnected

    async def serve(self) -> None:
        """Läuft bis `stop()`; prüft Bereitschaft zeitnah und Fälligkeit ohne Busy-Wait."""
        while not self._stop.is_set():
            await self.tick()
            timeout = 5.0
            if self.ready and self.last_attempt is not None:
                timeout = max(1.0, min(60.0, self.interval_s - (self.clock() - self.last_attempt)))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=timeout)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()
