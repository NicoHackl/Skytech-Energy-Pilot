"""Lokaler Plan-Validator: Sicherheits-Gate vor jeder Übergabe (doc/validation-safety.md).

Sicherheit hat Vorrang vor Optimierung. Der Validator klemmt oder verwirft einen
Kandidatenplan **lokal** gegen Schema + harte Grenzen — bevor irgendeine KI
angebunden wird. Implementiert sind die jetzt schon möglichen Pipeline-Stufen:

1. **Schema** – Plan gegen `PLAN_JSON_SCHEMA` + korrekte `schema_version`.
2. **Harte Grenzen** – jeder Geräte-Vorschlag gegen `DeviceConstraint` (Schreib-
   vertrag, Leistungs-/Temperaturgrenzen) klemmen oder ablehnen. `technische_freigabe`
   ist nur der AKTUELLE Ist-Zustand des Geräts (kein Vorschlags-Blocker, D-054): sie
   beschreibt nicht, ob das Gerät im Gültigkeitszeitraum des Plans arbeiten darf.
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


def _fallback_value(constraint: DeviceConstraint, key: str) -> object:
    """Sicherer Default für ein fehlendes Pflicht-Vorschlagsfeld (deterministische Füllung, D-050).

    Behebt schwankende Ausgabefelder: statt ein vom Modell vergessenes Vertragsfeld lautlos zu
    übergehen, füllt EP es aus dem aktuellen Zustand. Bewusst sicherheitskonservativ:
    - `prio_vorschlag` => None (die Rangfolge vergibt `_normalize_priorities`, auch bei Lücken).
    - `freigabe_vorschlag` => aktuelle technische Freigabe als sicherer Startwert (kein hartes
      Verbot, D-054: nur Fallback, falls die KI das Feld ausgelassen hat).
    - geschützte Mindestleistung => technische Mindestleistung bzw. 0 (wird ohnehin geklemmt).
    - Zusatzfeld => aktueller Lesewert, sonst typ-abhängiger Default (Zahl 0/min, Bool False,
      Auswahl erste Option, Text leer). `datetime` ohne Lesewert bleibt offen (kein sinnvoller
      Default; advisorisch und selten – ein Repair-Aufruf soll es nachreichen).
    """
    if key == _PRIO_KEY:
        return None
    if key == "freigabe_vorschlag":
        return constraint.freigabe if isinstance(constraint.freigabe, bool) else False
    if key in _PROTECTED_MIN_KEYS:
        return constraint.min_power if constraint.min_power is not None else 0.0
    ce = next((c for c in constraint.extras if c.extra.plan_field == key), None)
    if ce is None:
        return None
    if ce.value is not None:
        return ce.value
    if ce.kind == "number":
        return ce.min if ce.min is not None else 0.0
    if ce.kind == "bool":
        return False
    if ce.kind == "select" and ce.options:
        return ce.options[0]
    if ce.kind == "text":
        return ""
    return None


def _fill_missing_fields(
    entry: dict, constraint: DeviceConstraint, clamped: list[str]
) -> None:
    """Ergänzt fehlende Pflicht-Vorschlagsfelder deterministisch (Vollständigkeitsgarantie, D-050).

    Läuft VOR der Vertrags-/Grenzprüfung, damit gefüllte Werte anschließend regulär geklemmt
    werden. Prio wird bewusst ausgelassen (Rangfolge kommt aus `_normalize_priorities`). Jede
    Füllung wird wie eine Klemmung protokolliert – Transparenz in UI/Audit, dass EP (nicht die
    KI) den Wert gesetzt hat.
    """
    for key in suggestion_keys(constraint):
        if entry.get(key) is not None:
            continue
        value = _fallback_value(constraint, key)
        if value is None:
            continue
        entry[key] = value
        clamped.append(f"{constraint.name}.{key}: fehlt -> {value!r} (Fallback aus Ist-Zustand)")


def missing_suggestion_fields(
    plan_dict: dict, constraints: list[DeviceConstraint]
) -> dict[str, list[str]]:
    """Liefert je Gerät die noch fehlenden Pflicht-Vorschlagsfelder (Basis für den Repair-Aufruf).

    Grundlage ist der Schreibvertrag (`suggestion_keys`); ein komplett fehlendes Gerät zählt mit
    allen seinen Feldern. Wird VOR der Validierung/Füllung auf dem montierten Modell-Plan
    ausgewertet, damit der Planner gezielt genau die Lücken nachfordern kann (D-050).
    """
    by_entry = {
        e.get("name"): e for e in plan_dict.get("devices", []) if isinstance(e, dict)
    }
    missing: dict[str, list[str]] = {}
    for constraint in constraints:
        entry = by_entry.get(constraint.name) or {}
        gaps = [key for key in suggestion_keys(constraint) if entry.get(key) is None]
        if gaps:
            missing[constraint.name] = gaps
    return missing


def _check_device(
    entry: dict, constraint: DeviceConstraint, errors: list[str], clamped: list[str]
) -> None:
    """Stufe 2 je Gerät: fehlende Felder füllen, dann Schreibvertrag + harte Grenzen (in-place)."""
    name = constraint.name
    allowed = set(suggestion_keys(constraint))

    # Stufe 2a (D-050): fehlende Pflichtfelder deterministisch auffüllen, bevor geprüft wird.
    _fill_missing_fields(entry, constraint, clamped)

    # Schreibvertrag: nur erlaubte Felder je Gerät (z.B. Batterie keine Priorität, D-037;
    # Binärlast keine geschützte Mindestleistung; korrekte Einheit w/a).
    for key in entry:
        if key != "name" and key not in allowed:
            errors.append(f"{name}: Feld '{key}' nicht im Schreibvertrag dieses Geräts")

    # Geschützte Mindestleistung in [min_power, max_power] klemmen (Batterie: <= max. Ladeleistung).
    for key in _PROTECTED_MIN_KEYS:
        if key in allowed:
            _clamp_field(entry, key, constraint.min_power, constraint.max_power, clamped, name)

    # Zusatz-Vorschläge (D-047/D-048/D-049) sind advisorisch (nur HA-Sensor). input_number-Zusätze
    # werden auf den `min`/`max`-Bereich geklemmt (D-048); input_select-Zusätze müssen aus dem
    # Auswahlpool stammen – ein Wert außerhalb wird verworfen (D-049). Bool/Datum/Text laufen durch.
    for ce in constraint.extras:
        if not ce.extra.ai_suggestion:
            continue
        field = ce.extra.plan_field
        if ce.kind == "number":
            _clamp_field(entry, field, ce.min, ce.max, clamped, name)
        elif ce.kind == "select" and ce.options and field in entry:
            if entry[field] not in ce.options:
                clamped.append(f"{name}.{field}: {entry[field]!r} nicht im Wertepool -> entfernt")
                del entry[field]


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
    # Alle Geräte, deren Schreibvertrag eine Priorität erlaubt. Fehlt/ungültig der KI-Wert
    # (kein int; float wie 2.0 wird mitgenommen, bool nicht), gilt die Prio als „fehlend" und
    # wird ans Ende gereiht – so bleibt die Ausgabe vollständig (D-050), statt das Feld zu
    # verlieren. `None`-Prio sortiert nach den vorhandenen, stabil nach ursprünglichem Index.
    ranked: list[tuple[int | None, int, dict]] = []  # (KI-Prio | None, Index, Eintrag)
    for index, entry in enumerate(devices):
        constraint = by_name.get(entry.get("name"))
        if constraint is None or _PRIO_KEY not in suggestion_keys(constraint):
            continue
        value = entry.get(_PRIO_KEY)
        if isinstance(value, bool):
            value = None
        elif isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, int):
            value = None
        ranked.append((value, index, entry))

    # Sortierschlüssel: vorhandene Prios (kleiner=höher) vor fehlenden; innerhalb stabil per Index.
    # Hinweis: >10 Prio-Geräte sprengen das 10–100-Band; für V1 (≤10 Geräte) irrelevant.
    ranked.sort(key=lambda item: (item[0] is None, item[0] or 0, item[1]))
    for rank, (old_value, _index, entry) in enumerate(ranked, start=1):
        new_value = rank * _PRIO_STEP
        if old_value is None:
            clamped.append(
                f"{entry['name']}.{_PRIO_KEY}: fehlt -> {new_value} (Fallback, ans Ende gereiht)"
            )
        elif new_value != old_value:
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

    # Vollständigkeit (D-050): fehlt ein bekanntes Gerät ganz im Plan, wird ein leerer Eintrag
    # ergänzt (die Felder füllt `_check_device` deterministisch). So liefert EP nie „mal nur
    # manche Geräte", ohne dass ein ausgelassenes Gerät lautlos verschwindet.
    present = {e["name"] for e in normalized["devices"] if isinstance(e, dict) and "name" in e}
    for constraint in constraints:
        if constraint.name not in present:
            normalized["devices"].append({"name": constraint.name})
            clamped.append(f"{constraint.name}: Gerät fehlte im Plan -> Fallback ergänzt")

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
