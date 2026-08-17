"""Home-Assistant-Connector: REST- und WebSocket-Zugriff über den Supervisor-Proxy.

Authentifizierung erfolgt mit dem vom Supervisor bereitgestellten Token. Lesezugriffe
laufen gegen die Entity Allowlist: nicht freigegebene Entitäten werden protokolliert
und auditiert, aber **nicht blockiert** (Soft-Durchsetzung, D-038).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import aiohttp

from energy_pilot.http_errors import raise_for_status

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
            await raise_for_status(resp, service="Home Assistant")
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
            await raise_for_status(resp, service="Home Assistant")
            return await resp.json()

    async def get_history(
        self,
        entity_id: str,
        start: datetime,
        end: datetime | None = None,
        *,
        minimal: bool = True,
    ) -> list[dict[str, Any]]:
        """Liest den Verlauf einer Entität (`GET /api/history/period/<start>`, D-065).

        Der einzige Weg, an Werte zu kommen, die älter als der 60-Minuten-Aggregator sind
        (`aggregation.py`) — nötig, um Tagesbilanzen zu bilden: „wie viel Wärme kam gestern ohne
        Strom in den Speicher?" ist ohne Verlauf nicht beantwortbar.

        `minimal_response` und `significant_changes_only` sind gesetzt, weil ein einzelner
        Temperaturfühler leicht fünfstellige Zeilenzahlen pro Woche erzeugt und EP je Wert nur
        Minimum, Maximum und Differenz braucht. Liefert die flache Liste der Zustände (HA
        antwortet mit einer Liste **pro** Entität; hier wird genau eine abgefragt).

        Wie `get_state` läuft der weiche Allowlist-Guard mit (D-038): protokollieren, nicht
        blockieren.
        """
        if self._allowlist is not None:
            self._allowlist.check(entity_id)
        params: dict[str, str] = {
            "filter_entity_id": entity_id,
            "minimal_response": "true" if minimal else "false",
            "significant_changes_only": "true" if minimal else "false",
        }
        if end is not None:
            params["end_time"] = end.isoformat()
        session = await self._ensure_session()
        async with session.get(
            f"{self.base_url}/history/period/{start.isoformat()}",
            headers=self.headers,
            params=params,
        ) as resp:
            await raise_for_status(resp, service="Home Assistant")
            payload = await resp.json()
        # HA liefert eine Liste von Listen (eine je Entität). Bei einer angefragten Entität ist
        # das entweder [[...]] oder – wenn nichts aufgezeichnet wurde – [].
        if not isinstance(payload, list) or not payload:
            return []
        first = payload[0]
        return [row for row in first if isinstance(row, dict)] if isinstance(first, list) else []

    async def set_state(
        self, entity_id: str, state: str, attributes: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Schreibt einen Zustand nach HA (POST /api/states/<entity_id>).

        Wird für die EP-eigenen `sensor.ep_*`-Vorschlagsentitäten genutzt (V1-Schreibweg,
        siehe user-beispiele/variablen-zugriff.md). **Kein** Allowlist-Guard: die Allowlist
        ist die Lese-Domäne (D-038); Schreibziele sind ausschließlich EP-eigene Ausgaben.
        """
        session = await self._ensure_session()
        body: dict[str, Any] = {"state": state}
        if attributes:
            body["attributes"] = attributes
        async with session.post(
            f"{self.base_url}/states/{entity_id}", headers=self.headers, json=body
        ) as resp:
            await raise_for_status(resp, service="Home Assistant")
            return await resp.json()

    async def call_service(
        self, domain: str, service: str, entity_id: str, data: dict[str, Any] | None = None
    ) -> Any:
        """Ruft einen HA-Service auf (POST /api/services/<domain>/<service>).

        Genutzt für den Original-Schreibweg „In Original schreiben" (D-052): schreibt einen
        KI-Vorschlag über den passenden Helfer-Service (z.B. `input_number.set_value`,
        `input_select.select_option`) statt eines rohen State-Overwrites zurück in die
        Original-Entität – damit greifen HAs eigene Validierung/Min-Max/Optionspool.
        """
        session = await self._ensure_session()
        body: dict[str, Any] = {"entity_id": entity_id, **(data or {})}
        async with session.post(
            f"{self.base_url}/services/{domain}/{service}", headers=self.headers, json=body
        ) as resp:
            await raise_for_status(resp, service="Home Assistant")
            return await resp.json()

    async def open_websocket(self) -> aiohttp.ClientWebSocketResponse:
        """Öffnet die WebSocket-Verbindung (Auth-Handshake folgt in M1)."""
        session = await self._ensure_session()
        return await session.ws_connect(self.ws_url)
