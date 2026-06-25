"""Wetterprognose: Config-Parsing und normalisierte Datenstrukturen (OpenWeatherMap).

Die Wettervorhersage wird in V1 **direkt** über die OpenWeatherMap-„5 day / 3 hour
forecast"-API abgerufen (User-Vorgabe). Im Gegensatz zur PV-Prognose (HA-Sensoren,
siehe [forecast.py]) ist Wetter eine **eigene externe Quelle** des EP. Längen-/
Breitengrad kommen aus einer **HA-Zone** (`zone.*`, Attribute `latitude`/`longitude`),
der API-Schlüssel und alle Parameter werden über die Addon-Config gepflegt.

Die Daten werden in V1 **nur im EP** genutzt (UI/API) — nicht als HA-Sensoren und
nicht über die interne API an das HEMS übergeben.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Standard-Zone, falls nichts konfiguriert ist (HA legt `zone.home` automatisch an).
DEFAULT_ZONE_ENTITY = "zone.home"
DEFAULT_UNITS = "metric"
DEFAULT_LANG = "de"
# Mindestabstand zweier OWM-Aufrufe (min). Die 5-Tage-Prognose ändert sich serverseitig
# nur alle paar Stunden; häufigere Abrufe wären reine Verschwendung (Rate-Limit-Schutz).
DEFAULT_REFRESH_MIN = 30


@dataclass(frozen=True)
class WeatherConfig:
    """Aus der Addon-Option `weather` geparste Wetter-Konfiguration."""

    api_key: str
    zone_entity: str
    units: str
    lang: str
    refresh_min: int

    @property
    def enabled(self) -> bool:
        """Wetterabruf nur aktiv, wenn ein API-Schlüssel gepflegt ist (Iron Rule 8)."""
        return bool(self.api_key)


def weather_config_from_options(values: dict) -> WeatherConfig:
    """Baut die `WeatherConfig` aus der (verschachtelten) Addon-Option `weather`.

    Fehlende Felder fallen auf die Defaults zurück; der Schlüssel wird hier nur
    durchgereicht und nie geloggt (Iron Rule 6).
    """
    raw = values.get("weather")
    cfg = raw if isinstance(raw, dict) else {}

    api_key = str(cfg.get("api_key") or "").strip()
    zone_entity = str(cfg.get("zone_entity") or "").strip() or DEFAULT_ZONE_ENTITY
    units = str(cfg.get("units") or "").strip() or DEFAULT_UNITS
    lang = str(cfg.get("lang") or "").strip() or DEFAULT_LANG
    try:
        refresh_min = int(cfg.get("refresh_min") or DEFAULT_REFRESH_MIN)
    except (TypeError, ValueError):
        refresh_min = DEFAULT_REFRESH_MIN
    if refresh_min < 1:
        refresh_min = DEFAULT_REFRESH_MIN

    return WeatherConfig(
        api_key=api_key,
        zone_entity=zone_entity,
        units=units,
        lang=lang,
        refresh_min=refresh_min,
    )


@dataclass(frozen=True)
class WeatherSlot:
    """Ein normalisierter 3-Stunden-Prognoseschritt (nur energierelevante Felder)."""

    dt: int  # Unix-Zeitstempel (UTC)
    time: str  # ISO-Zeit (dt_txt) aus der OWM-Antwort
    temp: float | None
    feels_like: float | None
    clouds: float | None  # Bewölkung % – wesentlich für die PV-Erwartung
    pop: float | None  # Niederschlagswahrscheinlichkeit 0–1
    wind_speed: float | None
    humidity: float | None
    rain_3h: float | None  # mm
    snow_3h: float | None  # mm
    condition: str | None  # weather[0].description (lokalisiert)
    condition_id: int | None  # weather[0].id (sprachunabhängig)

    def as_dict(self) -> dict:
        return {
            "dt": self.dt,
            "time": self.time,
            "temp": self.temp,
            "feels_like": self.feels_like,
            "clouds": self.clouds,
            "pop": self.pop,
            "wind_speed": self.wind_speed,
            "humidity": self.humidity,
            "rain_3h": self.rain_3h,
            "snow_3h": self.snow_3h,
            "condition": self.condition,
            "condition_id": self.condition_id,
        }


@dataclass(frozen=True)
class WeatherForecast:
    """Normalisierte 5-Tage-Prognose: Standortmetadaten + 3-Stunden-Schritte."""

    city: str | None
    country: str | None
    timezone_offset_s: int | None
    sunrise: int | None
    sunset: int | None
    slots: list[WeatherSlot] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "city": self.city,
            "country": self.country,
            "timezone_offset_s": self.timezone_offset_s,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "slots": [slot.as_dict() for slot in self.slots],
        }
