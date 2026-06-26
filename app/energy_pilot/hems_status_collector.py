"""HEMS-Status-Collector (M3): pollt den HEMS-Zustand und spiegelt die Plan-Rückkopplung.

Analog zu `weather_collector`/`device_collector`. Je Zyklus:
1. `GET /api/status` holen — fehlertolerant (Iron Rule 8: HEMS offline ⇒ `online=False`,
   kein Crash);
2. die beobachtete Plan-Übereinstimmung ableiten (`plan_feedback.derive_plan_feedback`);
3. falls aktiviert, als EP-Status-Sensoren nach HA schreiben (`status_publisher`);
4. einen Verlaufseintrag in `hems_feedback` protokollieren.

Der Collector drosselt seinen HEMS-Abruf selbst auf `interval_s` (wie der Wetter-Collector),
läuft also nicht zwingend bei jedem 30-s-Poll-Zyklus.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time

from energy_pilot.logging_setup import log
from energy_pilot.plan_feedback import derive_plan_feedback
from energy_pilot.status_publisher import publish_status


class HEMSStatusCollector:
    """Pollt den HEMS-`/api/status`, leitet die Plan-Rückkopplung ab und spiegelt sie."""

    def __init__(
        self,
        hems_client: object | None,
        *,
        logger: logging.Logger | None = None,
        planner: object | None = None,
        device_collector: object | None = None,
        ha_client: object | None = None,
        db: sqlite3.Connection | None = None,
        publish_status_enabled: bool = True,
        interval_s: float = 60.0,
    ) -> None:
        self.hems_client = hems_client
        self.logger = logger
        self.planner = planner
        self.device_collector = device_collector
        self.ha_client = ha_client
        self.db = db
        self.publish_status_enabled = publish_status_enabled
        self.interval_s = float(interval_s)

        self.online: bool = False
        self.last_fetch_ts: float | None = None
        self.last_error: str | None = None
        self.last_status: dict | None = None  # vollständiger /api/status-Payload
        self.last_feedback: dict | None = None  # abgeleitete Plan-Rückkopplung
        self._last_run_ts: float | None = None

    @property
    def configured(self) -> bool:
        return self.hems_client is not None

    async def collect_once(self, now: float | None = None) -> None:
        """Ein Poll-Zyklus (selbst gedrosselt auf `interval_s`)."""
        now = time.time() if now is None else now
        if self.hems_client is None:
            return
        if self._last_run_ts is not None and (now - self._last_run_ts) < self.interval_s:
            return
        self._last_run_ts = now

        try:
            self.last_status = await self.hems_client.status()
            self.online = True
            self.last_error = None
        except Exception as exc:  # kontrolliert: HEMS-Ausfall blockiert EP nie
            self.online = False
            self.last_error = str(exc).strip() or exc.__class__.__name__
            if self.logger is not None:
                log(self.logger, "warning", "HEMS-Status nicht abrufbar",
                    context={"error": self.last_error})
        self.last_fetch_ts = now

        # Plan-Rückkopplung immer ableiten; offline ⇒ kein HEMS-Status ⇒ „unbekannt".
        latest = self.planner.latest_plan() if self.planner is not None else None
        devices = getattr(self.device_collector, "devices", []) if self.device_collector else []
        feedback = derive_plan_feedback(
            latest, devices, self.last_status if self.online else None
        )
        self.last_feedback = feedback

        if self.publish_status_enabled:
            await publish_status(
                self.ha_client, self.snapshot(), feedback, logger=self.logger, db=self.db
            )
        self._record(feedback)

    async def test_fetch(self) -> dict:
        """Live-Einzelabruf für den „Jetzt prüfen"-Button (umgeht die Drosselung)."""
        if self.hems_client is None:
            return {"ok": False, "reason": "HEMS nicht konfiguriert (hems_base_url leer)"}
        try:
            status = await self.hems_client.status()
        except Exception as exc:
            return {"ok": False, "reason": str(exc).strip() or exc.__class__.__name__}
        latest = self.planner.latest_plan() if self.planner is not None else None
        devices = getattr(self.device_collector, "devices", []) if self.device_collector else []
        feedback = derive_plan_feedback(latest, devices, status)
        inner = status.get("status") if isinstance(status, dict) else {}
        inner = inner if isinstance(inner, dict) else {}
        return {
            "ok": True,
            "online": True,
            "last_cycle_at": status.get("last_cycle_at"),
            "cycle_count": status.get("cycle_count"),
            "error": status.get("error"),
            "pool_w": inner.get("pool_w"),
            "feedback": feedback,
        }

    def snapshot(self) -> dict:
        """HEMS-Zustand für UI/API + Status-Publisher (read-only)."""
        status = self.last_status if (self.online and isinstance(self.last_status, dict)) else {}
        inner = status.get("status") if isinstance(status.get("status"), dict) else {}
        return {
            "configured": self.configured,
            "online": self.online,
            "last_fetch_ts": self.last_fetch_ts,
            "last_error": self.last_error,
            "last_cycle_at": status.get("last_cycle_at"),
            "cycle_count": status.get("cycle_count"),
            "error": status.get("error"),
            "interval_s": status.get("interval_s"),
            "pool_w": inner.get("pool_w"),
            "current_deficit_w": inner.get("current_deficit_w"),
            "global_mode": inner.get("global_mode"),
            "hard_lockout": inner.get("hard_lockout"),
            "devices": inner.get("devices") or [],
        }

    def _record(self, feedback: dict) -> None:
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO hems_feedback (plan_id, hems_online, plan_status, detail_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    feedback.get("plan_id"),
                    1 if self.online else 0,
                    feedback.get("overall"),
                    json.dumps(feedback, ensure_ascii=False),
                ),
            )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert den Poll nie
            pass
