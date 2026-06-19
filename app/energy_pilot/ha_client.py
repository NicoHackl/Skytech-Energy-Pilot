"""Home-Assistant-Connector: REST- und WebSocket-Zugriff über den Supervisor-Proxy.

Authentifizierung erfolgt mit dem vom Supervisor bereitgestellten Token. Lesezugriffe
laufen gegen die Entity Allowlist: nicht freigegebene Entitäten werden protokolliert
und auditiert, aber **nicht blockiert** (Soft-Durchsetzung, D-038).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from energy_pilot.allowlist import EntityAllowlist

# Interne Supervisor-Endpunkte (innerhalb des Addon-Netzes erreichbar).
SUPERVISOR_CORE_URL = "http://supervisor/core/api"
SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"


class HAClient:
    """Schlanker Async-Client für die Home-Assistant-Core-API."""

    def __init__(
        self,
        token: str | None,
        base_url: str = SUPERVISOR_CORE_URL,
        ws_url: str = SUPERVISOR_WS_URL,
        session: aiohttp.ClientSession | None = None,
        allowlist: EntityAllowlist | None = None,
    ) -> None:
        self._token = token
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url
        self._session = session
        self._owns_session = session is None
        # Weicher Allowlist-Guard; None => kein Guard (z.B. in Tests/Selbsttest).
        self._allowlist = allowlist

    @property
    def headers(self) -> dict[str, str]:
        """Authorization-Header für den Supervisor-Proxy."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Schließt die selbst angelegte Session (nicht eine injizierte)."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def test_connection(self) -> dict[str, Any]:
        """Prüft die Verbindung über GET /api/ und liefert die Statusmeldung."""
        session = await self._ensure_session()
        async with session.get(f"{self.base_url}/", headers=self.headers) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Liest den aktuellen Zustand einer Entität.

        Vor dem Read prüft der weiche Allowlist-Guard die Entität: nicht
        freigegebene IDs werden protokolliert/auditiert, der Read läuft aber
        unverändert weiter (Soft-Durchsetzung, D-038).
        """
        if self._allowlist is not None:
            self._allowlist.check(entity_id)
        session = await self._ensure_session()
        async with session.get(
            f"{self.base_url}/states/{entity_id}", headers=self.headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def open_websocket(self) -> aiohttp.ClientWebSocketResponse:
        """Öffnet die WebSocket-Verbindung (Auth-Handshake folgt in M1)."""
        session = await self._ensure_session()
        return await session.ws_connect(self.ws_url)
