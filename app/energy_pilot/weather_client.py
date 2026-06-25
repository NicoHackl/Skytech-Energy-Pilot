"""OpenWeatherMap-Client für die „5 day / 3 hour forecast"-API (Doc 06, User-Vorgabe).

Direkter REST-Aufruf via aiohttp (Muster wie `gemini_provider.py`/`hems_client.py`) –
bewusst ohne SDK. Der API-Schlüssel steht ausschließlich in der Addon-Config und wird
als Query-Parameter `appid` übergeben (OWM unterstützt keine Header-Auth). Er wird
**nie geloggt** und taucht in keiner Fehlermeldung auf (Iron Rule 6): wir bauen die URL
über `params=` und protokollieren ausschließlich Koordinaten/Einheiten, niemals die
vollständige Request-URL.
"""

from __future__ import annotations

import json

import aiohttp

from energy_pilot.weather import WeatherForecast, WeatherSlot

DEFAULT_BASE_URL = "https://api.openweathermap.org/data/2.5"
DEFAULT_TIMEOUT_S = 15.0


async def _error_message(resp: aiohttp.ClientResponse) -> str:
    """Holt den OWM-Originalgrund aus dem Fehler-Body.

    OWM antwortet bei Fehlern mit `{"cod":<n>,"message":"…"}`; wir reichen genau diese
    `message` durch, damit der echte Grund sichtbar wird (z.B. „Invalid API key…").
    Der Body enthält **nie** den Schlüssel → Iron Rule 6 bleibt gewahrt.
    """
    text = await resp.text()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text[:200]
    if isinstance(data, dict) and data.get("message"):
        return str(data["message"])
    return text[:200]


class WeatherClientError(Exception):
    """Kontrollierter Wetter-Abruffehler (nie der nackte aiohttp-Fehler nach außen)."""


def _num(value: object) -> float | None:
    """Wandelt einen OWM-Zahlwert defensiv in float; None bei fehlend/ungültig."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int | float)):
        return float(value)
    return None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_forecast(payload: dict) -> WeatherForecast:
    """Normalisiert die OWM-Antwort auf `WeatherForecast` (nur energierelevante Felder)."""
    city = payload.get("city") if isinstance(payload.get("city"), dict) else {}
    slots: list[WeatherSlot] = []
    for entry in payload.get("list") or []:
        if not isinstance(entry, dict):
            continue
        main = entry.get("main") if isinstance(entry.get("main"), dict) else {}
        clouds = entry.get("clouds") if isinstance(entry.get("clouds"), dict) else {}
        wind = entry.get("wind") if isinstance(entry.get("wind"), dict) else {}
        rain = entry.get("rain") if isinstance(entry.get("rain"), dict) else {}
        snow = entry.get("snow") if isinstance(entry.get("snow"), dict) else {}
        weather_list = entry.get("weather") if isinstance(entry.get("weather"), list) else []
        weather0 = weather_list[0] if weather_list and isinstance(weather_list[0], dict) else {}
        slots.append(
            WeatherSlot(
                dt=_int(entry.get("dt")) or 0,
                time=str(entry.get("dt_txt") or ""),
                temp=_num(main.get("temp")),
                feels_like=_num(main.get("feels_like")),
                clouds=_num(clouds.get("all")),
                pop=_num(entry.get("pop")),
                wind_speed=_num(wind.get("speed")),
                humidity=_num(main.get("humidity")),
                rain_3h=_num(rain.get("3h")),
                snow_3h=_num(snow.get("3h")),
                condition=str(weather0.get("description")) if weather0.get("description") else None,
                condition_id=_int(weather0.get("id")),
            )
        )
    return WeatherForecast(
        city=str(city.get("name")) if city.get("name") else None,
        country=str(city.get("country")) if city.get("country") else None,
        timezone_offset_s=_int(city.get("timezone")),
        sunrise=_int(city.get("sunrise")),
        sunset=_int(city.get("sunset")),
        slots=slots,
    )


class OpenWeatherClient:
    """Schlanker Async-Client für die OWM-5-Tage-/3-Stunden-Prognose."""

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

    def masked_request_url(self, lat: float, lon: float) -> str:
        """Die Request-URL mit maskiertem Schlüssel (für die Transparenz-Anzeige im Test).

        Zeigt exakt die gebaute URL-Form, aber `appid=***` statt des echten Schlüssels –
        damit der User die Aufrufstruktur prüfen kann, ohne dass der Key sichtbar wird.
        """
        return (
            f"{self.base_url}/forecast?lat={lat}&lon={lon}"
            f"&appid=***&units={self.units}&lang={self.lang}"
        )

    async def fetch_forecast(self, lat: float, lon: float) -> WeatherForecast:
        """Holt die 5-Tage-Prognose für die Koordinaten und liefert sie normalisiert.

        Fehler (ungültiger Schlüssel, Rate-Limit, Netz) werden als
        `WeatherClientError` mit klarer, schlüsselfreier Meldung gemeldet.
        """
        session = await self._ensure_session()
        url = f"{self.base_url}/forecast"
        # appid bewusst als params-Eintrag → erscheint in keinem von uns geloggten String.
        params = {
            "lat": f"{lat}",
            "lon": f"{lon}",
            "appid": self._api_key,
            "units": self.units,
            "lang": self.lang,
        }
        try:
            async with session.get(url, params=params, timeout=self._timeout) as resp:
                if resp.status == 401:
                    msg = await _error_message(resp)
                    raise WeatherClientError(
                        "OpenWeatherMap: API-Schlüssel ungültig oder noch nicht aktiviert "
                        f"(HTTP 401): {msg}"
                    )
                if resp.status == 429:
                    msg = await _error_message(resp)
                    raise WeatherClientError(
                        f"OpenWeatherMap-Rate-Limit erreicht (HTTP 429): {msg}"
                    )
                if resp.status == 404:
                    msg = await _error_message(resp)
                    raise WeatherClientError(
                        f"OpenWeatherMap: Koordinaten nicht gefunden (HTTP 404): {msg}"
                    )
                if resp.status >= 400:
                    msg = await _error_message(resp)
                    raise WeatherClientError(
                        f"OpenWeatherMap-Fehler HTTP {resp.status}: {msg}"
                    )
                payload = await resp.json()
        except TimeoutError as exc:
            total = self._timeout.total
            detail = f" nach {total:.0f}s" if total else ""
            raise WeatherClientError(f"OpenWeatherMap-Zeitüberschreitung{detail}") from exc
        except aiohttp.ClientError as exc:
            raise WeatherClientError(f"OpenWeatherMap-Verbindungsfehler: {exc}") from exc
        if not isinstance(payload, dict):
            raise WeatherClientError("OpenWeatherMap lieferte kein JSON-Objekt")
        return parse_forecast(payload)
