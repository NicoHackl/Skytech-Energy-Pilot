"""Tests für Startbedingung, Takt, Parallelität und Wiederanlauf des EP-Schedulers."""

import asyncio
from types import SimpleNamespace

from energy_pilot.planning_scheduler import PlanningScheduler


class _Collector:
    def __init__(self, collected=False):
        self.last_collect_ts = 1.0 if collected else None


class _Devices(_Collector):
    def __init__(self, ready=False):
        super().__init__(ready)
        self.discovery_source = "hems" if ready else "none"
        self.devices = [object()] if ready else []


class _Planner:
    def __init__(self, *, ok=True, gate=None):
        self.ok = ok
        self.gate = gate
        self.runs = 0
        self.publishes = 0

    async def publish_latest(self):
        self.publishes += 1
        return {"ok": True}

    async def run(self):
        self.runs += 1
        if self.gate is not None:
            await self.gate.wait()
        return SimpleNamespace(ok=self.ok, error=None if self.ok else "provider_error")


class _HA:
    def __init__(self):
        self.connected = True

    async def test_connection(self):
        if not self.connected:
            raise OSError("HA nicht erreichbar")
        return {"message": "API running"}


async def test_scheduler_waits_for_discovery_and_first_snapshots():
    planner = _Planner()
    scheduler = PlanningScheduler(planner, _Collector(), _Devices(), interval_min=60)
    assert await scheduler.tick(now=0.0) is None
    assert planner.runs == 0


async def test_first_run_restores_plan_then_runs_and_obeys_hourly_interval():
    planner = _Planner()
    scheduler = PlanningScheduler(
        planner, _Collector(True), _Devices(True), interval_min=60
    )
    await scheduler.tick(now=100.0)
    assert (planner.publishes, planner.runs) == (1, 1)
    assert await scheduler.tick(now=3699.0) is None
    await scheduler.tick(now=3700.0)
    assert (planner.publishes, planner.runs) == (1, 2)


async def test_provider_failure_does_not_trigger_a_tight_retry_or_extend_a_plan():
    planner = _Planner(ok=False)
    scheduler = PlanningScheduler(
        planner, _Collector(True), _Devices(True), interval_min=60
    )
    result = await scheduler.tick(now=100.0)
    assert result.ok is False
    assert scheduler.last_success is None
    assert scheduler.last_error == "provider_error"
    assert await scheduler.tick(now=101.0) is None
    assert planner.runs == 1


async def test_parallel_ticks_start_only_one_run():
    gate = asyncio.Event()
    planner = _Planner(gate=gate)
    scheduler = PlanningScheduler(
        planner, _Collector(True), _Devices(True), interval_min=60
    )
    first = asyncio.create_task(scheduler.tick(now=100.0))
    await asyncio.sleep(0)
    second = await scheduler.tick(now=100.0)
    gate.set()
    await first
    assert second is None
    assert planner.runs == 1


async def test_new_scheduler_republishes_still_valid_plan_after_restart():
    planner = _Planner()
    first = PlanningScheduler(planner, _Collector(True), _Devices(True))
    await first.tick(now=1.0)
    restarted = PlanningScheduler(planner, _Collector(True), _Devices(True))
    await restarted.tick(now=2.0)
    assert planner.publishes == 2


async def test_reconnection_republishes_without_early_ai_run():
    planner = _Planner()
    planner.ha_client = _HA()
    scheduler = PlanningScheduler(planner, _Collector(True), _Devices(True), interval_min=60)
    await scheduler.tick(now=100.0)
    assert (planner.publishes, planner.runs) == (1, 1)

    planner.ha_client.connected = False
    await scheduler.tick(now=101.0)
    planner.ha_client.connected = True
    await scheduler.tick(now=102.0)

    assert planner.publishes == 2
    assert planner.runs == 1
