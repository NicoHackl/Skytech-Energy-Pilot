"""Lokaler Plan-Validator: Sicherheits-Gate vor jeder Übergabe (08-validierung-sicherheit.md).

Sicherheit hat Vorrang vor Optimierung. Der Validator klemmt oder verwirft einen
Kandidatenplan **lokal** gegen Schema + harte Grenzen — bevor irgendeine KI
angebunden wird. Implementiert sind die jetzt schon möglichen Pipeline-Stufen:

1. **Schema** – Plan gegen `PLAN_JSON_SCHEMA` + korrekte `schema_version`.
2. **Harte Grenzen** – jeder Geräte-Vorschlag gegen `DeviceConstraint` (Schreib-
   vertrag, Freigabe, Leistungs-/Temperaturgrenzen) klemmen oder ablehnen.
3. **Zeitlogik** – `valid_from < valid_until`, nicht abgelaufen.

TODO(M2-Folge): Stufe 4 Datenaktualität, Stufe 5 Delta-Limit (braucht Vorplan),
Stufe 6 Mindestkonfidenz (braucht KI-Konfidenz; `min_confidence_percent` liegt
bereits in der Addon-Config). Bewusst noch nicht verdrahtet (Eingaben fehlen).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from energy_pilot.constraints import DeviceConstraint
from energy_pilot.plan_schema import schema_errors, suggestion_keys

# Geschützte-Mindestleistung-Felder (Watt/Ampere), die gegen [min_power, max_power] geklemmt werden.
_PROTECTED_MIN_KEYS = (
    "geschutzte_mindestleistung_w_vorschlag",
    "geschutzte_mindestleistung_a_vorschlag",
)

# Prioritäten bilden eine eindeutige, lückenlose Rangfolge in 10er-Schritten ab 10
# (10 = höchste). Gilt für alle Prio-Geräte; die Batterie hat keine Priorität (D-037).
_PRIO_KEY = "prio_vorschlag"
_PRIO_STEP = 10


@dataclass
class ValidationResult:
    """Ergebnis der Validierung: ok, Fehler (Ablehnung), geklemmte Felder, Normalplan."""

    ok: bool
    errors: list[str]
    clamped: list[str]
    normalized_plan: dict | None


def _parse_dt(value: object) -> datetime | None:
    """Parst einen ISO-8601-Zeitstempel; ein fehlendes Zeitzonen-Offset gilt als UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _clamp(value: float, lo: float | None, hi: float | None) -> tuple[float, bool]:
    """Klemmt einen Wert in [lo, hi] (Grenzen optional); liefert (Wert, wurde_geklemmt)."""
    if lo is not None and value < lo:
        return lo, True
    if hi is not None and value > hi:
        return hi, True
    return value, False


def _clamp_field(
    entry: dict, key: str, lo: float | None, hi: float | None, clamped: list[str], name: str
) -> None:
    """Klemmt ein einzelnes numerisches Feld in-place und protokolliert die Klemmung."""
    value = entry.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        return
    new_value, was_clamped = _clamp(float(value), lo, hi)
    if was_clamped:
        clamped.append(f"{name}.{key}: {value} -> {new_value}")
        entry[key] = new_value


def _check_time_logic(plan: dict, now: datetime, errors: list[str]) -> None:
    """Stufe 3: Zeitfenster plausibel und nicht abgelaufen."""
    start = _parse_dt(plan.get("valid_from"))
    end = _parse_dt(plan.get("valid_until"))
    if start is None or end is None:
        errors.append("Zeitlogik: valid_from/valid_until nicht als ISO-Zeit lesbar")
        return
    if start >= end:
        errors.append("Zeitlogik: valid_from muss vor valid_until liegen")
    if end <= now:
        errors.append("Zeitlogik: Plan ist bereits abgelaufen (valid_until <= jetzt)")


def _check_device(
    entry: dict, constraint: DeviceConstraint, errors: list[str], clamped: list[str]
) -> None:
    """Stufe 2 für ein Gerät: Schreibvertrag + harte Grenzen klemmen/ablehnen (in-place)."""
    name = constraint.name
    allowed = set(suggestion_keys(constraint))

    # Schreibvertrag: nur erlaubte Felder je Gerät (z.B. Batterie keine Priorität, D-037;
    # Binärlast keine geschützte Mindestleistung; korrekte Einheit w/a).
    for key in entry:
        if key != "name" and key not in allowed:
            errors.append(f"{name}: Feld '{key}' nicht im Schreibvertrag dieses Geräts")

    # Freigabe: EP darf eine technisch gesperrte Last nicht freigeben (harte Grenze).
    if entry.get("freigabe_vorschlag") is True and constraint.freigabe is False:
        errors.append(f"{name}: freigabe_vorschlag=true trotz technischer Sperre")

    # Geschützte Mindestleistung in [min_power, max_power] klemmen (Batterie: <= max. Ladeleistung).
    for key in _PROTECTED_MIN_KEYS:
        if key in allowed:
            _clamp_field(entry, key, constraint.min_power, constraint.max_power, clamped, name)

    # Heizstab-Wassertemperatur <= harte Obergrenze klemmen (D-035).
    if "max_temperatur_vorschlag" in allowed:
        _clamp_field(
            entry, "max_temperatur_vorschlag", 0.0, constraint.max_water_temp, clamped, name
        )


def _normalize_priorities(
    devices: list[dict], by_name: dict[str, DeviceConstraint], clamped: list[str]
) -> None:
    """Erzwingt die strikte 10er-Rangfolge (10, 20, 30 …) über alle Prio-Geräte (in-place).

    Die KI-Werte gelten nur als **relative Reihenfolge** (kleinster Wert = höchste
    Priorität). EP kanonisiert sie auf Rang*10 — eindeutig und lückenlos; geänderte
    Werte werden wie andere Klemmungen protokolliert. Prio-Verstöße verwerfen einen
    Plan also nie (konsistent mit der Klemm-Logik). Die Batterie trägt keine Priorität
    (Schreibvertrag D-037) und bleibt außen vor.
    """
    # Nur Geräte, deren Schreibvertrag eine Priorität erlaubt und die einen
    # ganzzahligen Prio-Wert tragen (float wie 2.0 wird mitgenommen, bool nicht).
    ranked: list[tuple[int, int, dict]] = []  # (KI-Prio, ursprünglicher Index, Eintrag)
    for index, entry in enumerate(devices):
        constraint = by_name.get(entry.get("name"))
        if constraint is None or _PRIO_KEY not in suggestion_keys(constraint):
            continue
        value = entry.get(_PRIO_KEY)
        if isinstance(value, bool):
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, int):
            continue
        ranked.append((value, index, entry))

    # Stabil nach (KI-Priorität, ursprüngliche Reihenfolge) sortieren = gemeinte Rangfolge.
    # Hinweis: >10 Prio-Geräte sprengen das 10–100-Band; für V1 (≤10 Geräte) irrelevant.
    ranked.sort(key=lambda item: (item[0], item[1]))
    for rank, (old_value, _index, entry) in enumerate(ranked, start=1):
        new_value = rank * _PRIO_STEP
        if new_value != old_value:
            clamped.append(f"{entry['name']}.{_PRIO_KEY}: {old_value} -> {new_value}")
        entry[_PRIO_KEY] = new_value  # immer den kanonischen int schreiben


def validate(
    plan_dict: dict,
    constraints: list[DeviceConstraint],
    *,
    now: datetime | None = None,
) -> ValidationResult:
    """Validiert einen Kandidatenplan gegen Schema + harte Grenzen (Stufen 1–3).

    Liefert bei Strukturfehlern `ok=False` ohne Normalplan; sonst einen normalisierten
    (geklemmten) Plan plus Liste der Klemmungen und etwaiger Ablehnungsgründe.
    """
    now = now or datetime.now(UTC)

    # Stufe 1: Struktur/Typen. Bei Schemafehlern ist keine sinnvolle Normalisierung möglich.
    structural = schema_errors(plan_dict)
    if structural:
        return ValidationResult(ok=False, errors=structural, clamped=[], normalized_plan=None)

    errors: list[str] = []
    clamped: list[str] = []
    normalized = deepcopy(plan_dict)

    # Stufe 3: Zeitlogik.
    _check_time_logic(normalized, now, errors)

    # Stufe 2: harte Grenzen je Gerät.
    by_name = {c.name: c for c in constraints}
    for entry in normalized["devices"]:
        constraint = by_name.get(entry["name"])
        if constraint is None:
            errors.append(f"{entry['name']}: unbekanntes Gerät (nicht in den erkannten Geräten)")
            continue
        _check_device(entry, constraint, errors, clamped)

    # Stufe 2b: Prioritäten geräteübergreifend auf die strikte 10er-Rangfolge bringen.
    _normalize_priorities(normalized["devices"], by_name, clamped)

    return ValidationResult(
        ok=not errors, errors=errors, clamped=clamped, normalized_plan=normalized
    )
