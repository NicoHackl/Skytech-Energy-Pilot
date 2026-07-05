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
# Paginierte Calls je Timeline (O2, D-045): wie viele Seiten je Refresh geholt werden.
# Jede Seite ist ein eigener bezahlter Call → bewusst eng begrenzt (1–5), Default 1 (erste Seite).
DEFAULT_PAGES = 1
MIN_PAGES = 1
MAX_PAGES = 5
# Tages-Call-Budget (O2, D-045): harte Obergrenze bezahlter One-Call-Anfragen pro Tag (UTC).
# Default = OWM-Freikontingent „One Call by Call". Schützt vor versehentlichem Überschreiten.
DEFAULT_DAILY_CALL_BUDGET = 1000
# Unwetter-Alerts (O3, D-045): standardmäßig an (User: „definitiv mitnehmen"); eigener Refresh.
DEFAULT_ENABLE_ALERTS = True
DEFAULT_REFRESH_ALERTS = 30


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


def _parse_pages(value: object, default: int = DEFAULT_PAGES) -> int:
    """Liest die Seitenzahl je Timeline; ungültig → Default, sonst auf 1–5 begrenzt (O2)."""
    try:
        pages = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_PAGES, min(MAX_PAGES, pages))


def _parse_budget(value: object, default: int = DEFAULT_DAILY_CALL_BUDGET) -> int:
    """Liest das Tages-Call-Budget; ungültig/<1 → Default (mind. 1 Call/Tag)."""
    try:
        budget = int(value)
    except (TypeError, ValueError):
        return default
    return budget if budget >= 1 else default


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
    # Paginierte Calls je Timeline (1–5, O2): wie viele Seiten je Refresh geholt werden.
    pages_15min: int = DEFAULT_PAGES
    pages_1h: int = DEFAULT_PAGES
    pages_1day: int = DEFAULT_PAGES
    # Harte Tagesobergrenze bezahlter One-Call-Anfragen (Timelines + Alerts), O2-Pflichtschutz.
    daily_call_budget: int = DEFAULT_DAILY_CALL_BUDGET
    # Unwetter-Alerts (O3): eigener Schalter + Refresh-Intervall.
    enable_alerts: bool = DEFAULT_ENABLE_ALERTS
    refresh_alerts: int = DEFAULT_REFRESH_ALERTS

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

    def pages_for(self, resolution: str) -> int:
        """Wie viele Seiten je Refresh für diese Timeline geholt werden (1–5)."""
        return {
            "15min": self.pages_15min,
            "1h": self.pages_1h,
            "1day": self.pages_1day,
        }.get(resolution, DEFAULT_PAGES)

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
        pages_15min=_parse_pages(oc.get("pages_15min"), defaults.pages_15min),
        pages_1h=_parse_pages(oc.get("pages_1h"), defaults.pages_1h),
        pages_1day=_parse_pages(oc.get("pages_1day"), defaults.pages_1day),
        daily_call_budget=_parse_budget(oc.get("daily_call_budget"), defaults.daily_call_budget),
        enable_alerts=_parse_bool(oc.get("enable_alerts"), defaults.enable_alerts),
        refresh_alerts=_parse_refresh(oc.get("refresh_alerts"), defaults.refresh_alerts),
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
class OneCallAlert:
    """Eine behördliche Unwetterwarnung der One Call API 4.0 (O3, D-045).

    Vorerst werden die Daten nur mitgeführt/angezeigt – noch keine Einspeisung in die Planung.
    Der Zukunftsaspekt (z.B. Batterieladung bei drohendem Gewitter priorisieren) baut darauf auf.
    """

    sender_name: str | None
    event: str | None
    start: int | None  # Unix-Zeitstempel (UTC) – Beginn der Warnung
    end: int | None  # Unix-Zeitstempel (UTC) – Ende der Warnung
    description: str | None
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "sender_name": self.sender_name,
            "event": self.event,
            "start": self.start,
            "end": self.end,
            "description": self.description,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class OneCallTimeline:
    """Ergebnis eines One-Call-Timeline-Abrufs: Standortmeta + normalisierte Schritte."""

    resolution: str  # "15min" | "1h" | "1day"
    lat: float | None
    lon: float | None
    timezone_offset_s: int | None
    slots: list[OneCallSlot] = field(default_factory=list)
    # Aktive Alert-IDs aus den `data[].alerts`-Feldern der Antwort (One Call 4.0). Die
    # eigentlichen Warnungen werden je ID separat über den Alert-Detail-Endpunkt aufgelöst.
    alert_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "resolution": self.resolution,
            "lat": self.lat,
            "lon": self.lon,
            "timezone_offset_s": self.timezone_offset_s,
            "slots": [slot.as_dict() for slot in self.slots],
            "alert_ids": list(self.alert_ids),
        }
