"""HEMS-Connector: liest das Geräteschema des Skytech-HEMS-Addons.

Das HEMS stellt die technischen Gerätewerte (`ems_*`) bereit und erzeugt die
Entity-IDs dynamisch pro Gerät aus `entity_prefix`/`class`/`output_unit`
(Decision D-036). EP fragt darum `GET /api/device_controls_schema` ab, statt die
Namen zu raten. Ist das HEMS nicht erreichbar, kennt EP keine Geräte – es gibt
keinen Addon-Config-Fallback mehr (siehe devices.discover, doc/devices.md).
"""

from __future__ import annotations

from typing import Any

import aiohttp

from energy_pilot.http_errors import raise_for_status

# Kurzer Timeout: EP soll nie auf ein langsames/abwesendes HEMS warten.
DEFAULT_TIMEOUT_S = 10.0


class HEMSClient:
    """Schlanker Async-Client für die interne HEMS-API."""

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Schließt die selbst angelegte Session (nicht eine injizierte)."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def device_schema(self) -> list[dict[str, Any]]:
        """Liefert das HEMS-Kontrollschema (Gruppen mit `ems_*`-Entitäten je Gerät).

        Format: `[{"label": ..., "items": [{"entity": ..., "label": ...}, ...]}, ...]`.
        Wirft bei Nichterreichbarkeit/Fehlerstatus – der Aufrufer behandelt das als
        „keine Geräte" und startet den Discovery-Retry (D-046, kein Config-Fallback).
        """
        return await self._get_json("/api/device_controls_schema")

    async def status(self) -> dict[str, Any]:
        """Liefert den letzten HEMS-Regelzyklus (`GET /api/status`).

        Format: `{"status": {pool_w, current_deficit_w, devices: [...], ...},
        "last_cycle_at", "cycle_count", "error", "interval_s"}` (gegen
        SkytechHEMS `app/main.py` verifiziert). Wirft bei Nichterreichbarkeit/
        Fehlerstatus – der Aufrufer (Status-Collector) fängt das fehlertolerant ab.
        """
        return await self._get_json("/api/status")

    async def controls(self) -> dict[str, Any]:
        """Liefert die Live-States aller `ems_*`-Helfer (`GET /api/controls`)."""
        return await self._get_json("/api/controls")

    async def _get_json(self, path: str) -> Any:
        """Gemeinsamer GET-Helfer: Session sicherstellen, Status prüfen, JSON liefern."""
        session = await self._ensure_session()
        async with session.get(f"{self.base_url}{path}", timeout=self._timeout) as resp:
            await raise_for_status(resp, service="HEMS")
            return await resp.json()
