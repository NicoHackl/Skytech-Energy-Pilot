"""OpenWeatherMap One Call API 4.0 – Client für die Timeline-Endpunkte (15min/1h/1day).

Direkter REST-Aufruf via aiohttp (Muster wie `weather_client.py`), bewusst ohne SDK. Jede
Timeline ist ein eigener Endpunkt (`/timeline/15min`, `/timeline/1h`, `/timeline/1day`) und ein
eigener **bezahlter** API-Call (Abo „One Call by Call"). Es wird je Abruf bewusst **nur die erste
Seite** geholt (kein `next`-Folgen) – Kosten-/Budget-Schutz (D-044).

Der API-Schlüssel steht ausschließlich in der Addon-Config, geht als Query-Parameter `appid`
(OWM kennt keine Header-Auth) und wird **nie geloggt** (Iron Rule 6): die `appid` wird über
`params=` übergeben und taucht in keinem von uns protokollierten String auf.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import aiohttp

from energy_pilot.weather import (
    ONECALL_TIMELINES,
    OneCallAlert,
    OneCallSlot,
    OneCallTimeline,
)
from energy_pilot.weather_client import (
    WeatherClientError,
    _int,
    _num,
    raise_for_owm_status,
)

DEFAULT_BASE_URL = "https://api.openweathermap.org/data/4.0/onecall"
DEFAULT_TIMEOUT_S = 15.0


def _iso_utc(dt: int) -> str:
    """ISO-Zeit (UTC) aus einem Unix-Zeitstempel – die 4.0-API liefert kein `dt_txt`."""
    return datetime.fromtimestamp(dt, tz=UTC).strftime("%Y-%m-%d %H:%M")


def _volume(value: object) -> float | None:
    """Niederschlagsvolumen mm: akzeptiert `{"1h": x}` (15min/1h) oder eine Zahl (Tagesmenge)."""
    if isinstance(value, dict):
        return _num(value.get("1h"))
    return _num(value)


def parse_timeline(resolution: str, payload: dict) -> OneCallTimeline:
    """Normalisiert eine One-Call-Timeline-Antwort auf `OneCallTimeline`.

    Bei der Tages-Timeline (`1day`) sind `temp`/`feels_like` Objekte (`temp.day/min/max`),
    bei 15min/1h Punktwerte. Nur energierelevante Felder werden behalten.
    """
    slots: list[OneCallSlot] = []
    alert_ids: list[str] = []
    for entry in payload.get("data") or []:
        if not isinstance(entry, dict):
            continue
        # `data[].alerts` trägt in 4.0 nur die Alert-IDs (Strings); Details separat je ID.
        for aid in entry.get("alerts") or []:
            if isinstance(aid, str) and aid and aid not in alert_ids:
                alert_ids.append(aid)
        temp_raw = entry.get("temp")
        if isinstance(temp_raw, dict):  # daily
            temp = _num(temp_raw.get("day"))
            temp_min = _num(temp_raw.get("min"))
            temp_max = _num(temp_raw.get("max"))
        else:
            temp = _num(temp_raw)
            temp_min = temp_max = None
        feels_raw = entry.get("feels_like")
        feels = _num(feels_raw.get("day")) if isinstance(feels_raw, dict) else _num(feels_raw)
        weather_list = entry.get("weather") if isinstance(entry.get("weather"), list) else []
        weather0 = weather_list[0] if weather_list and isinstance(weather_list[0], dict) else {}
        dt = _int(entry.get("dt")) or 0
        slots.append(
            OneCallSlot(
                dt=dt,
                time=_iso_utc(dt) if dt else "",
                temp=temp,
                feels_like=feels,
                temp_min=temp_min,
                temp_max=temp_max,
                clouds=_num(entry.get("clouds")),
                pop=_num(entry.get("pop")),
                wind_speed=_num(entry.get("wind_speed")),
                humidity=_num(entry.get("humidity")),
                rain=_volume(entry.get("rain")),
                snow=_volume(entry.get("snow")),
                condition=str(weather0.get("description")) if weather0.get("description") else None,
                condition_id=_int(weather0.get("id")),
            )
        )
    return OneCallTimeline(
        resolution=resolution,
        lat=_num(payload.get("lat")),
        lon=_num(payload.get("lon")),
        timezone_offset_s=_int(payload.get("timezone_offset")),
        slots=slots,
        alert_ids=alert_ids,
    )


def parse_alert(payload: dict) -> OneCallAlert:
    """Normalisiert **eine** Alert-Detail-Antwort (`/alert/{id}`) auf `OneCallAlert` (O3).

    Der Alert-Detail-Endpunkt der One Call API 4.0 liefert ein **einzelnes** Objekt
    (`id`, `sender_name`, `event`, `start`, `end`, `description`; `tags` optional). Tolerant
    gegenüber fehlenden Feldern (Iron Rule 8).
    """
    tags = payload.get("tags")
    return OneCallAlert(
        sender_name=str(payload["sender_name"]) if payload.get("sender_name") else None,
        event=str(payload["event"]) if payload.get("event") else None,
        start=_int(payload.get("start")),
        end=_int(payload.get("end")),
        description=str(payload["description"]) if payload.get("description") else None,
        tags=[str(t) for t in tags] if isinstance(tags, list) else [],
    )


class OneCallClient:
    """Schlanker Async-Client für die One-Call-4.0-Timelines (erste Seite je Abruf)."""

    def __init__(
        self,
        api_key: str,
        *,
        units: str = "metric",
        lang: str = "de",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._api_key = api_key
        self.units = units
        self.lang = lang
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._session = session
        self._owns_session = session is None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Schließt die selbst angelegte Session (nicht eine injizierte)."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    def _endpoint(self, resolution: str) -> str:
        return f"{self.base_url}/timeline/{resolution}"

    def _alert_endpoint(self, alert_id: str) -> str:
        # One Call 4.0: die Warnung wird je ID über den Detail-Endpunkt aufgelöst.
        return f"{self.base_url}/alert/{alert_id}"

    def _base_params(self, lat: float, lon: float) -> dict[str, str]:
        # appid bewusst als params-Eintrag → erscheint in keinem von uns geloggten String.
        return {
            "lat": f"{lat}",
            "lon": f"{lon}",
            "appid": self._api_key,
            "units": self.units,
            "lang": self.lang,
        }

    def masked_request_url(self, resolution: str, lat: float, lon: float) -> str:
        """Request-URL mit maskiertem Schlüssel (Transparenz-Anzeige, ohne echten Key)."""
        return (
            f"{self._endpoint(resolution)}?lat={lat}&lon={lon}"
            f"&appid=***&units={self.units}&lang={self.lang}"
        )

    def masked_alert_url(self, alert_id: str | None = None) -> str:
        """Alert-Detail-Request-URL mit maskiertem Schlüssel (Transparenz-Anzeige).

        Ohne konkrete ID wird das Endpunkt-Muster (`/alert/{id}`) gezeigt – der Detail-Endpunkt
        nimmt keine Koordinaten, nur die Alert-ID im Pfad.
        """
        return f"{self._alert_endpoint(alert_id or '{id}')}?appid=***&lang={self.lang}"

    async def _get(self, url: str, params: dict[str, str]) -> dict:
        """Ein GET mit OWM-Fehlerbehandlung; liefert das JSON-Objekt (schlüsselfrei im Log)."""
        session = await self._ensure_session()
        try:
            async with session.get(url, params=params, timeout=self._timeout) as resp:
                await raise_for_owm_status(resp)
                payload = await resp.json()
        except TimeoutError as exc:
            total = self._timeout.total
            detail = f" nach {total:.0f}s" if total else ""
            raise WeatherClientError(f"OpenWeatherMap-Zeitüberschreitung{detail}") from exc
        except aiohttp.ClientError as exc:
            raise WeatherClientError(f"OpenWeatherMap-Verbindungsfehler: {exc}") from exc
        if not isinstance(payload, dict):
            raise WeatherClientError("OpenWeatherMap lieferte kein JSON-Objekt")
        return payload

    async def fetch_timeline(
        self, resolution: str, lat: float, lon: float, *, max_calls: int = 1
    ) -> tuple[OneCallTimeline, int]:
        """Holt eine Timeline (bis zu `max_calls` paginierte Seiten) normalisiert.

        Folgt dem `next`-Cursor der Antwort bis maximal `max_calls` Seiten (jede Seite = ein
        eigener bezahlter Call, O2). Stoppt früher, wenn die API keinen `next`-Link mehr liefert.
        Rückgabe: `(kombinierte Timeline, tatsächlich abgerufene Seiten)` – damit der Aufrufer
        exakt gegen das Tagesbudget abbuchen kann. Fehler (ungültiger Schlüssel, Rate-Limit, Netz)
        werden als `WeatherClientError` mit klarer, schlüsselfreier Meldung gemeldet.
        """
        if resolution not in ONECALL_TIMELINES:
            raise WeatherClientError(f"Unbekannte One-Call-Timeline: {resolution}")
        payload = await self._get(self._endpoint(resolution), self._base_params(lat, lon))
        timeline = parse_timeline(resolution, payload)
        slots = list(timeline.slots)
        calls_used = 1
        next_url = payload.get("next")
        while calls_used < max_calls and isinstance(next_url, str) and next_url:
            # Der `next`-Link trägt die Folge-Parameter, aber nie den Schlüssel → appid ergänzen.
            payload = await self._get(next_url, {"appid": self._api_key})
            slots.extend(parse_timeline(resolution, payload).slots)
            calls_used += 1
            next_url = payload.get("next")
        return replace(timeline, slots=slots), calls_used

    async def fetch_alert(self, alert_id: str) -> OneCallAlert:
        """Holt die Detaildaten **einer** behördlichen Unwetterwarnung (O3); ein bezahlter Call.

        Die Alert-ID stammt aus den `data[].alerts`-Feldern einer Timeline-Antwort
        (`OneCallTimeline.alert_ids`); der Detail-Endpunkt (`/alert/{id}`) nimmt keine Koordinaten,
        nur `appid`/`lang`. API-Fehler werden als `WeatherClientError` (schlüsselfrei) gemeldet.
        """
        params = {"appid": self._api_key, "lang": self.lang}
        payload = await self._get(self._alert_endpoint(alert_id), params)
        return parse_alert(payload)
