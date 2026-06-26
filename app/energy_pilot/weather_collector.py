"""Weather Collector: löst die HA-Zone in Koordinaten auf und ruft OWM ab.

Der Collector wird wie die übrigen Sammler im Poller-Zyklus aufgerufen
(`collect_once`), drosselt OWM-Aufrufe aber selbst auf `refresh_min` Minuten
(serverseitig ändert sich die 5-Tage-Prognose nur alle paar Stunden). Die
Koordinaten kommen aus den Attributen `latitude`/`longitude` der konfigurierten
HA-Zone (`zone.*`); fehlt der API-Schlüssel oder die Zone, bleibt der Collector
inaktiv und blockiert nichts (Iron Rule 8).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time

from energy_pilot import onecall_budget
from energy_pilot.conversion import safe_float
from energy_pilot.ha_client import HAClient
from energy_pilot.logging_setup import log
from energy_pilot.onecall_client import OneCallClient
from energy_pilot.weather import (
    ONECALL_TIMELINES,
    OneCallAlert,
    WeatherConfig,
    WeatherForecast,
)
from energy_pilot.weather_client import OpenWeatherClient, WeatherClientError


async def resolve_zone_coords(
    ha_client: HAClient | None,
    zone_entity: str,
    logger: logging.Logger | None = None,
) -> tuple[tuple[float, float] | None, str | None]:
    """Liest latitude/longitude aus einer HA-Zone. Rückgabe: `(coords, fehlertext)`.

    Geteilt von `WeatherCollector` und `OneCallCollector` (keine Duplizierung). Bei Erfolg
    `((lat, lon), None)`, sonst `(None, "<Grund>")` mit einer klaren, schlüsselfreien Meldung.
    """
    if ha_client is None:
        return None, "Keine HA-Verbindung für die Zone verfügbar"
    try:
        state = await ha_client.get_state(zone_entity)
    except Exception as exc:
        if logger:
            log(logger, "warning", "HA-Zone konnte nicht gelesen werden",
                context={"zone": zone_entity, "error": str(exc)})
        return None, f"Zone {zone_entity}: {exc}"
    attrs = state.get("attributes") or {}
    lat = safe_float(attrs.get("latitude"))
    lon = safe_float(attrs.get("longitude"))
    if lat is None or lon is None:
        if logger:
            log(logger, "warning", "HA-Zone ohne Koordinaten", context={"zone": zone_entity})
        return None, f"Zone {zone_entity} ohne gültige latitude/longitude"
    return (lat, lon), None


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

    async def test_fetch(self, now: float | None = None) -> dict:
        """Einmaliger Live-Abruf für die UI – umgeht den Refresh-Guard.

        Liefert ein strukturiertes Ergebnis statt zu werfen (Muster wie
        `AIProvider.test_connection`, aber fehlertolerant): so sieht der User im
        Test sofort den echten OWM-Grund (z.B. „Invalid API key…") und die
        maskierte Anfrage-URL – ohne dass der Schlüssel sichtbar wird.
        """
        now = time.time() if now is None else now
        if not self.config.enabled:
            return {"ok": False, "reason": "Kein OpenWeatherMap-Schlüssel konfiguriert"}
        if self.client is None or self.ha_client is None:
            return {"ok": False, "reason": "Keine HA-Verbindung für die Zone verfügbar"}

        coords = await self._resolve_coords()
        if coords is None:
            return {"ok": False, "reason": self.last_error or "Koordinaten nicht ermittelbar"}
        self.coords = coords
        request_url = self.client.masked_request_url(coords[0], coords[1])

        try:
            self.forecast = await self.client.fetch_forecast(coords[0], coords[1])
            self.last_fetch_ts = now
            self.last_error = None
            return {
                "ok": True,
                "city": self.forecast.city,
                "slots": len(self.forecast.slots),
                "coords": {"lat": coords[0], "lon": coords[1]},
                "request_url": request_url,
            }
        except WeatherClientError as exc:
            self.last_error = str(exc)
            return {
                "ok": False,
                "reason": str(exc),
                "coords": {"lat": coords[0], "lon": coords[1]},
                "request_url": request_url,
            }

    def _refresh_due(self, now: float) -> bool:
        if self.last_fetch_ts is None:
            return True
        return (now - self.last_fetch_ts) >= self.config.refresh_min * 60

    async def _resolve_coords(self) -> tuple[float, float] | None:
        """Liest latitude/longitude aus der konfigurierten HA-Zone (geteilte Hilfsfunktion)."""
        coords, err = await resolve_zone_coords(
            self.ha_client, self.config.zone_entity, self.logger
        )
        if err is not None:
            self.last_error = err
        return coords

    def snapshot(self) -> dict:
        """Read-only Momentaufnahme für UI/API (kein Schreibweg, kein HEMS)."""
        return {
            "enabled": self.enabled,
            "source": "forecast3h",
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


class OneCallCollector:
    """Ruft die One-Call-4.0-Timelines ab – je Timeline mit eigenem Refresh-Intervall.

    Identische öffentliche Schnittstelle wie `WeatherCollector` (`enabled`, `collect_once`,
    `test_fetch`, `snapshot`, `last_fetch_ts`, `last_error`), damit `main.py`/Webserver/Planner
    je nach `weather.source` denselben Collector-Platzhalter verwenden können. Jede aktivierte
    Timeline wird unabhängig gedrosselt; Fehler bleiben pro Timeline isoliert (Iron Rule 8).
    """

    def __init__(
        self,
        ha_client: HAClient | None,
        config: WeatherConfig,
        client: OneCallClient | None,
        logger: logging.Logger | None = None,
        db: sqlite3.Connection | None = None,
    ) -> None:
        self.ha_client = ha_client
        self.config = config
        self.client = client
        self.logger = logger
        # DB für den persistenten Tages-Call-Zähler (O2). Ohne DB läuft alles weiter, aber das
        # Tagesbudget wird nicht über Neustarts hinweg gezählt (in Produktion ist die DB stets da).
        self.db = db
        self.coords: tuple[float, float] | None = None
        self.last_error: str | None = None
        # Pro Timeline: zuletzt geholtes Ergebnis + eigener Refresh-/Fehlerzustand.
        self._timelines: dict[str, dict] = {
            res: {"timeline": None, "last_fetch_ts": None, "last_error": None}
            for res in ONECALL_TIMELINES
        }
        # Unwetter-Alerts (O3): eigener Refresh-/Fehlerzustand.
        self._alerts: list[OneCallAlert] = []
        self._alerts_last_fetch_ts: float | None = None
        self._alerts_last_error: str | None = None
        # Latch, damit die Budget-Erschöpfung nur einmal je Ereignis auditiert/geloggt wird.
        self._budget_exhausted = False

    @property
    def enabled(self) -> bool:
        """Aktiv mit Schlüssel/Client/HA und mind. einer aktiven Timeline **oder** Alerts."""
        oc = self.config.onecall
        return (
            self.config.enabled
            and self.client is not None
            and self.ha_client is not None
            and (bool(oc.enabled_timelines) or oc.enable_alerts)
        )

    @property
    def last_fetch_ts(self) -> float | None:
        """Jüngster erfolgreicher Abruf über Timelines + Alerts (für die Diagnose-Anzeige)."""
        stamps = [
            st["last_fetch_ts"]
            for st in self._timelines.values()
            if st["last_fetch_ts"] is not None
        ]
        if self._alerts_last_fetch_ts is not None:
            stamps.append(self._alerts_last_fetch_ts)
        return max(stamps) if stamps else None

    async def collect_once(self, now: float | None = None) -> None:
        """Holt je fällige Timeline + Alerts; sonst No-op (Rate-Limit-/Budget-Schutz)."""
        now = time.time() if now is None else now
        if not self.enabled:
            return
        self._refresh_budget_latch()
        oc = self.config.onecall
        due = [res for res in oc.enabled_timelines if self._refresh_due(res, now)]
        alerts_due = oc.enable_alerts and self._alerts_refresh_due(now)
        if not due and not alerts_due:
            return
        coords = await self._resolve_coords()
        if coords is None:
            return
        self.coords = coords
        for res in due:
            await self._fetch_timeline(res, coords, now)
        if alerts_due:
            await self._fetch_alerts(coords, now)

    async def test_fetch(self, now: float | None = None) -> dict:
        """Einmaliger Live-Abruf je aktivierter Timeline + Alerts (umgeht den Refresh-Guard).

        Macht echte **bezahlte** Calls → wird wie der reguläre Abruf gegen das Tagesbudget geprüft
        und abgebucht (sonst ließe sich das Budget per Mehrfachklick umgehen).
        """
        now = time.time() if now is None else now
        if not self.config.enabled:
            return {"ok": False, "reason": "Kein OpenWeatherMap-Schlüssel konfiguriert"}
        if self.client is None or self.ha_client is None:
            return {"ok": False, "reason": "Keine HA-Verbindung für die Zone verfügbar"}
        oc = self.config.onecall
        timelines = oc.enabled_timelines
        if not timelines and not oc.enable_alerts:
            return {"ok": False, "reason": "Keine One-Call-Timeline aktiviert"}

        coords = await self._resolve_coords()
        if coords is None:
            return {"ok": False, "reason": self.last_error or "Koordinaten nicht ermittelbar"}
        self.coords = coords
        self._refresh_budget_latch()

        results: list[dict] = []
        any_ok = False
        for res in timelines:
            request_url = self.client.masked_request_url(res, coords[0], coords[1])
            max_calls = min(oc.pages_for(res), self._budget_remaining())
            if max_calls <= 0:
                self._note_budget_exhausted()
                results.append({
                    "resolution": res, "ok": False,
                    "reason": "Tages-Call-Budget erschöpft", "request_url": request_url,
                })
                continue
            try:
                timeline, calls_used = await self.client.fetch_timeline(
                    res, coords[0], coords[1], max_calls=max_calls
                )
                onecall_budget.consume(self.db, calls_used)
                st = self._timelines[res]
                st["timeline"] = timeline
                st["last_fetch_ts"] = now
                st["last_error"] = None
                any_ok = True
                results.append({
                    "resolution": res, "ok": True, "slots": len(timeline.slots),
                    "pages": calls_used, "request_url": request_url,
                })
            except WeatherClientError as exc:
                self._timelines[res]["last_error"] = str(exc)
                results.append({
                    "resolution": res, "ok": False,
                    "reason": str(exc), "request_url": request_url,
                })

        alerts_result: dict | None = None
        if oc.enable_alerts:
            alert_url = self.client.masked_alert_url(coords[0], coords[1])
            if self._budget_remaining() <= 0:
                self._note_budget_exhausted()
                alerts_result = {
                    "ok": False, "reason": "Tages-Call-Budget erschöpft", "request_url": alert_url,
                }
            else:
                try:
                    alerts = await self.client.fetch_alerts(coords[0], coords[1])
                    onecall_budget.consume(self.db, 1)
                    self._alerts = alerts
                    self._alerts_last_fetch_ts = now
                    self._alerts_last_error = None
                    any_ok = True
                    alerts_result = {"ok": True, "count": len(alerts), "request_url": alert_url}
                except WeatherClientError as exc:
                    self._alerts_last_error = str(exc)
                    alerts_result = {"ok": False, "reason": str(exc), "request_url": alert_url}

        return {
            "ok": any_ok,
            "coords": {"lat": coords[0], "lon": coords[1]},
            "timelines": results,
            "alerts": alerts_result,
            "calls_today": onecall_budget.calls_today(self.db),
            "daily_call_budget": oc.daily_call_budget,
        }

    async def _fetch_timeline(
        self, resolution: str, coords: tuple[float, float], now: float
    ) -> None:
        assert self.client is not None  # durch enabled garantiert
        max_calls = min(self.config.onecall.pages_for(resolution), self._budget_remaining())
        if max_calls <= 0:
            self._note_budget_exhausted()
            return
        st = self._timelines[resolution]
        try:
            timeline, calls_used = await self.client.fetch_timeline(
                resolution, coords[0], coords[1], max_calls=max_calls
            )
            onecall_budget.consume(self.db, calls_used)
            st["timeline"] = timeline
            st["last_fetch_ts"] = now
            st["last_error"] = None
            if self.logger:
                log(self.logger, "info", "One-Call-Timeline aktualisiert",
                    context={"resolution": resolution, "slots": len(timeline.slots),
                             "pages": calls_used})
        except WeatherClientError as exc:
            st["last_error"] = str(exc)
            self.last_error = str(exc)
            if self.logger:
                log(self.logger, "warning", "One-Call-Abruf fehlgeschlagen",
                    context={"resolution": resolution, "error": str(exc)})

    async def _fetch_alerts(self, coords: tuple[float, float], now: float) -> None:
        """Holt die Unwetterwarnungen (O3); ein bezahlter Call gegen dasselbe Tagesbudget."""
        assert self.client is not None  # durch enabled garantiert
        if self._budget_remaining() <= 0:
            self._note_budget_exhausted()
            return
        try:
            alerts = await self.client.fetch_alerts(coords[0], coords[1])
            onecall_budget.consume(self.db, 1)
            self._alerts = alerts
            self._alerts_last_fetch_ts = now
            self._alerts_last_error = None
            if self.logger:
                log(self.logger, "info", "One-Call-Alerts aktualisiert",
                    context={"alerts": len(alerts)})
        except WeatherClientError as exc:
            self._alerts_last_error = str(exc)
            self.last_error = str(exc)
            if self.logger:
                log(self.logger, "warning", "One-Call-Alert-Abruf fehlgeschlagen",
                    context={"error": str(exc)})

    def _refresh_due(self, resolution: str, now: float) -> bool:
        st = self._timelines[resolution]
        if st["last_fetch_ts"] is None:
            return True
        return (now - st["last_fetch_ts"]) >= self.config.onecall.refresh_for(resolution) * 60

    def _alerts_refresh_due(self, now: float) -> bool:
        if self._alerts_last_fetch_ts is None:
            return True
        return (now - self._alerts_last_fetch_ts) >= self.config.onecall.refresh_alerts * 60

    # --- Tages-Call-Budget (O2, D-045) -------------------------------------------------------

    def _budget_remaining(self) -> int:
        return onecall_budget.remaining(self.db, self.config.onecall.daily_call_budget)

    def _refresh_budget_latch(self) -> None:
        """Latch zurücksetzen, sobald wieder Budget frei ist (z.B. nach UTC-Tageswechsel)."""
        if self._budget_remaining() > 0:
            self._budget_exhausted = False

    def _note_budget_exhausted(self) -> None:
        """Loggt/auditiert die Budget-Erschöpfung genau einmal je Ereignis (kein Spam)."""
        if self._budget_exhausted:
            return
        self._budget_exhausted = True
        if self.logger:
            log(self.logger, "warning",
                "One-Call-Tagesbudget erschöpft – keine weiteren bezahlten Abrufe heute",
                context={"budget": self.config.onecall.daily_call_budget})
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO audit (actor, action, subject, detail_json) VALUES (?, ?, ?, ?)",
                ("onecall", "onecall_budget_exhausted", None,
                 json.dumps({"budget": self.config.onecall.daily_call_budget})),
            )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - defensiv, Audit darf nie crashen
            pass

    async def _resolve_coords(self) -> tuple[float, float] | None:
        coords, err = await resolve_zone_coords(
            self.ha_client, self.config.zone_entity, self.logger
        )
        if err is not None:
            self.last_error = err
        return coords

    def snapshot(self) -> dict:
        """Read-only Momentaufnahme für UI/API: je Timeline Status + Schritte, Budget, Alerts."""
        oc = self.config.onecall
        timelines: dict[str, dict] = {}
        for res in ONECALL_TIMELINES:
            st = self._timelines[res]
            timeline = st["timeline"]
            timelines[res] = {
                "enabled": oc.is_enabled(res),
                "refresh_min": oc.refresh_for(res),
                "pages": oc.pages_for(res),
                "last_fetch_ts": st["last_fetch_ts"],
                "last_error": st["last_error"],
                "slots": [s.as_dict() for s in timeline.slots] if timeline else [],
            }
        remaining = self._budget_remaining()
        return {
            "enabled": self.enabled,
            "source": "onecall",
            "zone_entity": self.config.zone_entity,
            "units": self.config.units,
            "llm_timeline": oc.llm_timeline,
            "coords": (
                {"lat": self.coords[0], "lon": self.coords[1]} if self.coords else None
            ),
            "last_fetch_ts": self.last_fetch_ts,
            "last_error": self.last_error,
            "daily_call_budget": oc.daily_call_budget,
            "calls_today": onecall_budget.calls_today(self.db),
            "budget_remaining": remaining,
            "budget_exhausted": remaining <= 0,
            "alerts_enabled": oc.enable_alerts,
            "alerts_refresh_min": oc.refresh_alerts,
            "alerts_last_fetch_ts": self._alerts_last_fetch_ts,
            "alerts_last_error": self._alerts_last_error,
            "alerts": [a.as_dict() for a in self._alerts],
            "timelines": timelines,
        }
