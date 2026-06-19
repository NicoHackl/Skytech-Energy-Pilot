"""HEMS-Connector: liest das Geräteschema des Skytech-HEMS-Addons.

Das HEMS stellt die technischen Gerätewerte (`ems_*`) bereit und erzeugt die
Entity-IDs dynamisch pro Gerät aus `entity_prefix`/`class`/`output_unit`
(Decision D-036). EP fragt darum `GET /api/device_controls_schema` ab, statt die
Namen zu raten. Ist das HEMS nicht erreichbar, fällt die Discovery auf die
Addon-Config zurück (siehe devices.discover).
"""

from __future__ import annotations

from typing import Any

import aiohttp

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
        Wirft bei Nichterreichbarkeit/Fehlerstatus – der Aufrufer entscheidet über
        den Config-Fallback.
        """
        session = await self._ensure_session()
        async with session.get(
            f"{self.base_url}/api/device_controls_schema", timeout=self._timeout
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
