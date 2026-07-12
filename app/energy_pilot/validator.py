"""Lokaler Plan-Validator: Sicherheits-Gate vor jeder Übergabe (08-validierung-sicherheit.md).

Sicherheit hat Vorrang vor Optimierung. Der Validator klemmt oder verwirft einen
Kandidatenplan **lokal** gegen Schema + harte Grenzen — bevor irgendeine KI
angebunden wird. Implementiert sind die jetzt schon möglichen Pipeline-Stufen:

1. **Schema** – Plan gegen `PLAN_JSON_SCHEMA` + korrekte `schema_version`.
2. **Harte Grenzen** – jeder Geräte-Vorschlag gegen `DeviceConstraint` (Schreib-
   vertrag, Leistungs-/Temperaturgrenzen) klemmen oder ablehnen. `technische_freigabe`
   ist nur der AKTUELLE Ist-Zustand des Geräts (kein Vorschlags-Blocker, D-054): sie
   beschreibt nicht, ob das Gerät im Gültigkeitszeitraum des Plans arbeiten darf.
3. **Zeitlogik** – `valid_from < valid_until`, nicht abgelaufen.
6. **Mindestkonfidenz** (A4) – `confidence < min_confidence` lehnt den Plan ab
   (nicht veröffentlichen), behält aber den normalisierten Plan für UI/DB.

Zusätzlich stellt dieses Modul die **deterministische Anti-Flatter-Schicht**
(A2 / Stufe 5) als reine Funktion `smooth_plan()` bereit: Delta-Limit gegen den
Vorplan + Freigabe-Hysterese + Mindesthaltezeit. Sie ist DB-frei; der Planner
lädt/speichert den Pro-Gerät-Zustand und ruft sie nach `validate()` auf gültigen
Plänen auf. So bleibt der Validator testbar und die Persistenz getrennt.

TODO(M2-Folge): Stufe 4 Datenaktualität (braucht Zeitstempel-/Qualitäts-Mitführung
im Collector). Bewusst noch nicht verdrahtet (Eingaben fehlen).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

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


def _is_num(value: object) -> bool:
    """True für echte Zahlen (bool zählt NICHT als Zahl)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


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
    min_confidence: int | None = None,
) -> ValidationResult:
    """Validiert einen Kandidatenplan gegen Schema + harte Grenzen (Stufen 1–3, 6).

    Liefert bei Strukturfehlern `ok=False` ohne Normalplan; sonst einen normalisierten
    (geklemmten) Plan plus Liste der Klemmungen und etwaiger Ablehnungsgründe.
    `min_confidence` (Prozent) aktiviert Stufe 6: liegt die KI-Konfidenz darunter, wird der
    Plan abgelehnt (aber normalisiert zurückgegeben). Fehlt die Konfidenz, wird nicht abgelehnt.
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

    # Stufe 6 (A4): Mindestkonfidenz. Unsichere Pläne ablehnen (nicht veröffentlichen), den
    # normalisierten Plan aber behalten. Fehlende Konfidenz lehnt NICHT ab (Iron Rule 8).
    if min_confidence is not None:
        confidence = plan_dict.get("confidence")
        if _is_num(confidence) and confidence < min_confidence:
            errors.append(
                f"Mindestkonfidenz: {int(confidence)}% < {int(min_confidence)}% erforderlich"
            )

    return ValidationResult(
        ok=not errors, errors=errors, clamped=clamped, normalized_plan=normalized
    )


# --- Stufe 5 (A2): deterministische Anti-Flatter-Schicht -------------------------------------
# Rein deterministisch und DB-frei. Der Planner lädt den Pro-Gerät-Zustand aus der DB, ruft
# smooth_plan() NUR auf gültigen (validierten) Plänen auf, hängt die Notizen an result.clamped
# und speichert den zurückgegebenen Zustand wieder in die DB. So bleibt der Validator testbar.


@dataclass
class StabilityLimits:
    """Konfigurierbare Grenzen der Anti-Flatter-Schicht (Defaults = D-021)."""

    power_percent: float = 20.0  # Delta-Limit geschützte Mindestleistung je Lauf
    battery_percent: float = 10.0  # engerer Satz für die Batterie
    hysteresis_runs: int = 2  # Freigabe-Wechsel erst nach N konsistenten Läufen
    min_hold_minutes: float = 15.0  # keine erneute Freigabe-Änderung in diesem Fenster


@dataclass
class SmoothResult:
    """Ergebnis der Glättung: angepasste Geräte, neuer Pro-Gerät-Zustand, Notizen."""

    devices: list[dict]
    state: dict[str, dict]
    notes: list[str] = field(default_factory=list)


def _within_hold(last_change_ts: object, now: datetime, minutes: float) -> bool:
    """True, wenn die letzte akzeptierte Änderung weniger als `minutes` zurückliegt."""
    if minutes <= 0:
        return False
    changed = _parse_dt(last_change_ts)
    if changed is None:
        return False
    return (now - changed) < timedelta(minutes=minutes)


def _prio_of(entry: dict, state: dict) -> int | None:
    """Kanonische Prio des Eintrags (int) für die Zustandsfortschreibung; sonst der letzte Wert."""
    value = entry.get(_PRIO_KEY)
    if isinstance(value, bool):
        value = None
    elif isinstance(value, float) and value.is_integer():
        value = int(value)
    return value if isinstance(value, int) else state.get("last_prio")


def _delta_clamp_protected(
    entry: dict, constraint: DeviceConstraint, prev: dict, limits: StabilityLimits,
    notes: list[str],
) -> None:
    """Begrenzt die Änderung der geschützten Mindestleistung ggü. dem Vorplan (Delta-Limit)."""
    name = constraint.name
    pct = limits.battery_percent if constraint.is_battery else limits.power_percent
    for key in _PROTECTED_MIN_KEYS:
        new_val = entry.get(key)
        prev_val = prev.get(key)
        if not _is_num(new_val) or not _is_num(prev_val) or prev_val == 0:
            continue
        span = abs(float(prev_val)) * pct / 100.0
        clamped_val, was_clamped = _clamp(float(new_val), prev_val - span, prev_val + span)
        if was_clamped:
            clamped_val = round(clamped_val, 3)
            notes.append(f"{name}.{key}: {new_val} -> {clamped_val} (Delta-Limit ±{pct:g}%)")
            entry[key] = clamped_val


def _apply_freigabe_hysteresis(
    entry: dict, constraint: DeviceConstraint, state: dict, limits: StabilityLimits,
    now: datetime, notes: list[str],
) -> dict:
    """Hysterese + Mindesthaltezeit auf `freigabe_vorschlag`; liefert den neuen Gerätezustand.

    Ein Freigabe-Wechsel wird erst nach `hysteresis_runs` konsistenten Läufen UND außerhalb der
    Mindesthaltezeit übernommen; sonst wird die Freigabe auf den zuletzt veröffentlichten Wert
    zurückgesetzt. `constraint.freigabe` (aktuelle technische Freigabe) fließt bewusst NICHT mehr
    hart ein (D-054): sie beschreibt nur den JETZT-Zustand, nicht die Gültigkeit im Planzeitraum.
    """
    new_state: dict = {
        "last_freigabe": state.get("last_freigabe"),
        "last_prio": _prio_of(entry, state),
        "pending_freigabe": None,
        "pending_count": 0,
        "last_change_ts": state.get("last_change_ts"),
    }
    new_frei = entry.get("freigabe_vorschlag")
    if not isinstance(new_frei, bool):  # kein Freigabe-Vertrag (z.B. Batterie) → nichts zu glätten
        return new_state

    last = state.get("last_freigabe")
    last_bool = bool(last) if last is not None else None
    name = constraint.name

    # Erstbeobachtung oder unveränderte Freigabe → übernehmen, Kandidat zurücksetzen.
    if last_bool is None or new_frei == last_bool:
        new_state["last_freigabe"] = int(new_frei)
        return new_state

    pending = state.get("pending_freigabe")
    pending_bool = bool(pending) if pending is not None else None
    count = (int(state.get("pending_count") or 0) + 1) if pending_bool == new_frei else 1
    within_hold = _within_hold(state.get("last_change_ts"), now, limits.min_hold_minutes)

    if count >= limits.hysteresis_runs and not within_hold:
        entry["freigabe_vorschlag"] = new_frei
        new_state["last_freigabe"] = int(new_frei)
        new_state["last_change_ts"] = now.isoformat()
        notes.append(
            f"{name}.freigabe_vorschlag: {last_bool} -> {new_frei} "
            f"(Hysterese bestätigt nach {count} Läufen)"
        )
    else:
        entry["freigabe_vorschlag"] = last_bool  # Wechsel halten
        reason = "Mindesthaltezeit" if within_hold else f"Lauf {count}/{limits.hysteresis_runs}"
        notes.append(f"{name}.freigabe_vorschlag: Wechsel gehalten ({reason})")
        new_state["last_freigabe"] = int(last_bool)
        new_state["pending_freigabe"] = int(new_frei)
        new_state["pending_count"] = count
    return new_state


def smooth_plan(
    devices: list[dict],
    previous_by_name: dict[str, dict],
    constraints_by_name: dict[str, DeviceConstraint],
    state: dict[str, dict],
    *,
    limits: StabilityLimits,
    now: datetime | None = None,
) -> SmoothResult:
    """Glättet einen validierten Plan gegen Vorplan + Zustand (A2, in-place auf `devices`).

    `previous_by_name` = Geräteeinträge des zuletzt veröffentlichten Plans (Delta-Limit-Basis);
    `state` = persistierter Pro-Gerät-Zustand (Hysterese-Zähler, letzte Änderung). Gibt die
    angepassten Geräte, den neuen Zustand (vom Planner zu persistieren) und die Notizen zurück.
    """
    now = now or datetime.now(UTC)
    notes: list[str] = []
    new_state: dict[str, dict] = {}
    for entry in devices:
        constraint = constraints_by_name.get(entry.get("name"))
        if constraint is None:
            continue
        prev = previous_by_name.get(constraint.name) or {}
        st = state.get(constraint.name) or {}
        _delta_clamp_protected(entry, constraint, prev, limits, notes)
        new_state[constraint.name] = _apply_freigabe_hysteresis(
            entry, constraint, st, limits, now, notes
        )
    return SmoothResult(devices=devices, state=new_state, notes=notes)
