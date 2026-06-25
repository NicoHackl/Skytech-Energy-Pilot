"""Weather Collector: löst die HA-Zone in Koordinaten auf und ruft OWM ab.

Der Collector wird wie die übrigen Sammler im Poller-Zyklus aufgerufen
(`collect_once`), drosselt OWM-Aufrufe aber selbst auf `refresh_min` Minuten
(serverseitig ändert sich die 5-Tage-Prognose nur alle paar Stunden). Die
Koordinaten kommen aus den Attributen `latitude`/`longitude` der konfigurierten
HA-Zone (`zone.*`); fehlt der API-Schlüssel oder die Zone, bleibt der Collector
inaktiv und blockiert nichts (Iron Rule 8).
"""

from __future__ import annotations

import logging
import time

from energy_pilot.conversion import safe_float
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import log
from energy_pilot.weather import WeatherConfig, WeatherForecast
from energy_pilot.weather_client import OpenWeatherClient, WeatherClientError


class WeatherCollector:
    """Ruft die OWM-Wetterprognose ab und stellt eine Momentaufnahme bereit."""

    def __init__(
        self,
        ha_client: HAClient | None,
        config: WeatherConfig,
        client: OpenWeatherClient | None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.ha_client = ha_client
        self.config = config
        self.client = client
        self.logger = logger
        self.forecast: WeatherForecast | None = None
        self.coords: tuple[float, float] | None = None
        self.last_fetch_ts: float | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        """Aktiv nur mit API-Schlüssel, Client und HA-Verbindung (für die Zone)."""
        return self.config.enabled and self.client is not None and self.ha_client is not None

    async def collect_once(self, now: float | None = None) -> None:
        """Holt bei fälligem Refresh die Prognose; sonst No-op (Rate-Limit-Schutz)."""
        now = time.time() if now is None else now
        if not self.enabled:
            return
        if not self._refresh_due(now):
            return

        coords = await self._resolve_coords()
        if coords is None:
            return
        self.coords = coords

        try:
            assert self.client is not None  # durch enabled garantiert
            self.forecast = await self.client.fetch_forecast(coords[0], coords[1])
            self.last_fetch_ts = now
            self.last_error = None
            if self.logger:
                log(
                    self.logger, "info", "Wetterprognose aktualisiert",
                    context={"slots": len(self.forecast.slots), "city": self.forecast.city},
                )
        except WeatherClientError as exc:
            self.last_error = str(exc)
            if self.logger:
                log(self.logger, "warning", "Wetterabruf fehlgeschlagen",
                    context={"error": str(exc)})

    def _refresh_due(self, now: float) -> bool:
        if self.last_fetch_ts is None:
            return True
        return (now - self.last_fetch_ts) >= self.config.refresh_min * 60

    async def _resolve_coords(self) -> tuple[float, float] | None:
        """Liest latitude/longitude aus der konfigurierten HA-Zone."""
        if self.ha_client is None:
            return None
        try:
            state = await self.ha_client.get_state(self.config.zone_entity)
        except Exception as exc:
            self.last_error = f"Zone {self.config.zone_entity}: {exc}"
            if self.logger:
                log(self.logger, "warning", "HA-Zone konnte nicht gelesen werden",
                    context={"zone": self.config.zone_entity, "error": str(exc)})
            return None
        attrs = state.get("attributes") or {}
        lat = safe_float(attrs.get("latitude"))
        lon = safe_float(attrs.get("longitude"))
        if lat is None or lon is None:
            self.last_error = (
                f"Zone {self.config.zone_entity} ohne gültige latitude/longitude"
            )
            if self.logger:
                log(self.logger, "warning", "HA-Zone ohne Koordinaten",
                    context={"zone": self.config.zone_entity})
            return None
        return lat, lon

    def snapshot(self) -> dict:
        """Read-only Momentaufnahme für UI/API (kein Schreibweg, kein HEMS)."""
        return {
            "enabled": self.enabled,
            "zone_entity": self.config.zone_entity,
            "units": self.config.units,
            "refresh_min": self.config.refresh_min,
            "coords": (
                {"lat": self.coords[0], "lon": self.coords[1]} if self.coords else None
            ),
            "last_fetch_ts": self.last_fetch_ts,
            "last_error": self.last_error,
            "forecast": self.forecast.as_dict() if self.forecast else None,
        }
