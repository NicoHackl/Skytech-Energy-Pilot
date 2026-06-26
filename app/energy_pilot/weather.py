"""Wetterprognose: Config-Parsing und normalisierte Datenstrukturen (OpenWeatherMap).

Die Wettervorhersage wird **direkt im EP** über OpenWeatherMap abgerufen (User-Vorgabe).
Es gibt zwei umschaltbare Quellen (`weather.source`):
- `forecast3h` (**Default**): die „5 day / 3 hour forecast"-API (3-Stunden-Raster, 40 Werte).
- `onecall`: die **One Call API 4.0** mit getrennten Timelines (15min/1h/1day), je einzeln
  aktivierbar mit eigenem Abrufintervall. Erfordert das kostenpflichtige Abo „One Call by Call".

Im Gegensatz zur PV-Prognose (HA-Sensoren, siehe [forecast.py]) ist Wetter eine **eigene externe
Quelle** des EP. Längen-/Breitengrad kommen aus einer **HA-Zone** (`zone.*`, Attribute
`latitude`/`longitude`), der API-Schlüssel und alle Parameter werden über die Addon-Config gepflegt.

Die Daten werden in V1 **nur im EP** genutzt (UI/API + KI-Kontext) — nicht als HA-Sensoren und
nicht über die interne API an das HEMS übergeben.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Standard-Zone, falls nichts konfiguriert ist (HA legt `zone.home` automatisch an).
DEFAULT_ZONE_ENTITY = "zone.home"
DEFAULT_UNITS = "metric"
DEFAULT_LANG = "de"
# Mindestabstand zweier OWM-Aufrufe (min) für `forecast3h`. Die 5-Tage-Prognose ändert sich
# serverseitig nur alle paar Stunden; häufigere Abrufe wären reine Verschwendung (W3, D-044).
DEFAULT_REFRESH_MIN = 60
# Detailgrad der Wetterdaten, die ans LLM gehen (in der Addon-Config umschaltbar):
# "compact" = Bewölkung/Regen/Temp bis Planungshorizont (Datenminimum, Iron Rule 7),
# "full" = volle 5-Tage-Prognose mit allen Feldern (mehr Tokens, mehr Kontext).
DEFAULT_LLM_DETAIL = "compact"
LLM_DETAIL_CHOICES = ("compact", "full")

# Datenquelle (D-044): bestehende 3h/5-Tage-API oder One Call API 4.0.
SOURCE_FORECAST3H = "forecast3h"
SOURCE_ONECALL = "onecall"
DEFAULT_SOURCE = SOURCE_FORECAST3H
SOURCE_CHOICES = (SOURCE_FORECAST3H, SOURCE_ONECALL)

# One-Call-Timelines (Auflösungen) der 4.0-API. Reihenfolge = fein → grob.
ONECALL_TIMELINES = ("15min", "1h", "1day")
# Default: 1h+1day aktiv, 15min opt-in (spart bezahlte Calls/Tokens). Welche Timeline ins LLM geht,
# ist konfigurierbar; Default 1h (entspricht dem bisherigen compact-Horizontverhalten).
DEFAULT_LLM_TIMELINE = "1h"
# Default-Refresh je Timeline (Minuten); jede Timeline ist ein eigener bezahlter Call.
DEFAULT_ONECALL_REFRESH = {"15min": 15, "1h": 60, "1day": 180}


def _parse_bool(value: object, default: bool) -> bool:
    """Liest einen Bool-Wert aus der Config defensiv (akzeptiert true/false-Strings)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return default


def _parse_refresh(value: object, default: int) -> int:
    """Liest ein Refresh-Intervall (Minuten); ungültig/<1 → Default."""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return default
    return minutes if minutes >= 1 else default


@dataclass(frozen=True)
class OneCallConfig:
    """One-Call-4.0-Einstellungen: je Timeline aktivierbar mit eigenem Refresh-Intervall."""

    enable_15min: bool = False
    enable_1h: bool = True
    enable_1day: bool = True
    refresh_15min: int = DEFAULT_ONECALL_REFRESH["15min"]
    refresh_1h: int = DEFAULT_ONECALL_REFRESH["1h"]
    refresh_1day: int = DEFAULT_ONECALL_REFRESH["1day"]
    llm_timeline: str = DEFAULT_LLM_TIMELINE

    def is_enabled(self, resolution: str) -> bool:
        return {
            "15min": self.enable_15min,
            "1h": self.enable_1h,
            "1day": self.enable_1day,
        }.get(resolution, False)

    def refresh_for(self, resolution: str) -> int:
        return {
            "15min": self.refresh_15min,
            "1h": self.refresh_1h,
            "1day": self.refresh_1day,
        }.get(resolution, DEFAULT_ONECALL_REFRESH.get(resolution, DEFAULT_REFRESH_MIN))

    @property
    def enabled_timelines(self) -> tuple[str, ...]:
        """Aktivierte Timelines in fester Reihenfolge (fein → grob)."""
        return tuple(r for r in ONECALL_TIMELINES if self.is_enabled(r))


@dataclass(frozen=True)
class WeatherConfig:
    """Aus der Addon-Option `weather` geparste Wetter-Konfiguration."""

    api_key: str
    zone_entity: str
    units: str
    lang: str
    refresh_min: int
    llm_detail: str = DEFAULT_LLM_DETAIL
    source: str = DEFAULT_SOURCE
    onecall: OneCallConfig = field(default_factory=OneCallConfig)

    @property
    def enabled(self) -> bool:
        """Wetterabruf nur aktiv, wenn ein API-Schlüssel gepflegt ist (Iron Rule 8)."""
        return bool(self.api_key)


def _onecall_config_from_options(cfg: dict) -> OneCallConfig:
    """Liest die Untergruppe `weather.onecall` defensiv (fehlende Felder → Defaults)."""
    raw = cfg.get("onecall")
    oc = raw if isinstance(raw, dict) else {}
    defaults = OneCallConfig()
    llm_timeline = str(oc.get("llm_timeline") or "").strip().lower()
    if llm_timeline not in ONECALL_TIMELINES:
        llm_timeline = DEFAULT_LLM_TIMELINE
    return OneCallConfig(
        enable_15min=_parse_bool(oc.get("enable_15min"), defaults.enable_15min),
        enable_1h=_parse_bool(oc.get("enable_1h"), defaults.enable_1h),
        enable_1day=_parse_bool(oc.get("enable_1day"), defaults.enable_1day),
        refresh_15min=_parse_refresh(oc.get("refresh_15min"), defaults.refresh_15min),
        refresh_1h=_parse_refresh(oc.get("refresh_1h"), defaults.refresh_1h),
        refresh_1day=_parse_refresh(oc.get("refresh_1day"), defaults.refresh_1day),
        llm_timeline=llm_timeline,
    )


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
    refresh_min = _parse_refresh(cfg.get("refresh_min"), DEFAULT_REFRESH_MIN)
    llm_detail = str(cfg.get("llm_detail") or "").strip().lower()
    if llm_detail not in LLM_DETAIL_CHOICES:
        llm_detail = DEFAULT_LLM_DETAIL
    source = str(cfg.get("source") or "").strip().lower()
    if source not in SOURCE_CHOICES:
        source = DEFAULT_SOURCE

    return WeatherConfig(
        api_key=api_key,
        zone_entity=zone_entity,
        units=units,
        lang=lang,
        refresh_min=refresh_min,
        llm_detail=llm_detail,
        source=source,
        onecall=_onecall_config_from_options(cfg),
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


@dataclass(frozen=True)
class OneCallSlot:
    """Ein normalisierter One-Call-Schritt (passt für 15min/1h/1day-Auflösung).

    `temp_min`/`temp_max` werden nur bei der Tages-Timeline (`1day`) gefüllt; bei 15min/1h
    bleibt `temp` der Punktwert und min/max sind None.
    """

    dt: int  # Unix-Zeitstempel (UTC)
    time: str  # ISO-Zeit (aus dt abgeleitet, UTC)
    temp: float | None
    feels_like: float | None
    temp_min: float | None  # nur daily
    temp_max: float | None  # nur daily
    clouds: float | None  # Bewölkung %
    pop: float | None  # Niederschlagswahrscheinlichkeit 0–1
    wind_speed: float | None
    humidity: float | None
    rain: float | None  # mm (rain.1h bzw. Tagesniederschlag)
    snow: float | None  # mm
    condition: str | None  # weather[0].description (lokalisiert)
    condition_id: int | None  # weather[0].id (sprachunabhängig)

    def as_dict(self) -> dict:
        return {
            "dt": self.dt,
            "time": self.time,
            "temp": self.temp,
            "feels_like": self.feels_like,
            "temp_min": self.temp_min,
            "temp_max": self.temp_max,
            "clouds": self.clouds,
            "pop": self.pop,
            "wind_speed": self.wind_speed,
            "humidity": self.humidity,
            "rain": self.rain,
            "snow": self.snow,
            "condition": self.condition,
            "condition_id": self.condition_id,
        }


@dataclass(frozen=True)
class OneCallTimeline:
    """Ergebnis eines One-Call-Timeline-Abrufs: Standortmeta + normalisierte Schritte."""

    resolution: str  # "15min" | "1h" | "1day"
    lat: float | None
    lon: float | None
    timezone_offset_s: int | None
    slots: list[OneCallSlot] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "resolution": self.resolution,
            "lat": self.lat,
            "lon": self.lon,
            "timezone_offset_s": self.timezone_offset_s,
            "slots": [slot.as_dict() for slot in self.slots],
        }
