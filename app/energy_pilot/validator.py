"""Lokaler Plan-Validator: Sicherheits-Gate vor jeder Übergabe (docs/sicherheit-datenschutz.md).

Sicherheit hat Vorrang vor Optimierung. Der Validator klemmt oder verwirft einen
Kandidatenplan **lokal** gegen Schema + harte Grenzen — bevor irgendeine KI
angebunden wird. Implementiert sind die jetzt schon möglichen Pipeline-Stufen:

1. **Schema** – Plan gegen `PLAN_JSON_SCHEMA` + korrekte `schema_version`.
2. **Harte Grenzen** – jeder Geräte-Vorschlag gegen `DeviceConstraint` (Schreib-
   vertrag, Leistungs-/Temperaturgrenzen) klemmen oder ablehnen. `technische_freigabe`
   ist nur der AKTUELLE Ist-Zustand des Geräts (kein Vorschlags-Blocker, D-054): sie
   beschreibt nicht, ob das Gerät im Gültigkeitszeitraum des Plans arbeiten darf.
3. **Zeitlogik** – `valid_from < valid_until`, nicht abgelaufen.
4. **Datenaktualität** (D-064) – die vom Modell gelieferte `datenlage`-Teilnote wird gegen die
   real gemessene Datenlage des Kontexts gedeckelt. Selbsteinschätzung kann die Messung nie
   übertreffen.
6. **Mindestkonfidenz** (D-064) – die Teilnoten werden als schwächstes Glied aggregiert; liegt
   das Ergebnis unter `min_confidence_percent`, wird der Plan **nicht veröffentlicht**
   (`publish_blocked`). Er bleibt gültig, gespeichert und sichtbar.

TODO: Stufe 5 Delta-Limit zum Vorplan (D-021) bleibt bewusst offen — nachgelagerte Dämpfung der
KI-Ausgabe ist als Ansatz verworfen (D-060); Stabilität entsteht im Aufruf, nicht dahinter.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from energy_pilot.constraints import DeviceConstraint
from energy_pilot.plan_schema import (
    CONFIDENCE_PARTS,
    EXPLANATION_FIELDS,
    aggregate_confidence,
    schema_errors,
    suggestion_keys,
)

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
    """Ergebnis der Validierung: ok, Fehler (Ablehnung), geklemmte Felder, Normalplan.

    `publish_blocked` ist die Begründung, warum ein **gültiger** Plan trotzdem nicht nach HA
    geschrieben wird (Stufe 6, D-064). Bewusst getrennt von `ok`: der Plan ist nicht falsch, die
    KI war nur zu unsicher — er bleibt sichtbar und gespeichert, wirkt aber nicht.
    """

    ok: bool
    errors: list[str]
    clamped: list[str]
    normalized_plan: dict | None
    publish_blocked: str | None = None


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
    # Binärlast keine geschützte Mindestleistung; korrekte Einheit w/a). Die Begründungsfelder
    # (D-060) sind keine Vorschlagswerte und werden nie nach HA geschrieben — sie unterliegen
    # deshalb keinem Schreibvertrag.
    for key in entry:
        if key != "name" and key not in allowed and key not in EXPLANATION_FIELDS:
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


def _context_data_quality(context: dict | None) -> int | None:
    """EP-eigene `datenlage`-Note aus dem Kontext (Stufe 4, D-064).

    `plan_context._data_quality` hat den Anteil frischer, belegter Werte bereits gezählt; hier
    wird er nur gelesen. Damit hängt die Note an der gemessenen Realität und nicht an der
    Selbsteinschätzung des Modells.
    """
    if not isinstance(context, dict):
        return None
    datenlage = context.get("datenlage")
    if not isinstance(datenlage, dict):
        return None
    raw = datenlage.get("frische_prozent")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return max(0, min(100, int(round(float(raw)))))


def _resolve_confidence(
    normalized: dict, context: dict | None, clamped: list[str]
) -> int | None:
    """Stufen 4/6 (D-064): Teilnoten gegenrechnen und zur Gesamtkonfidenz aggregieren.

    Drei Schritte, alle in Code und damit prüfbar:
    1. Die vom Modell gelieferte `datenlage`-Note wird gegen die real gemessene Datenlage
       gedeckelt (`min`). Behauptet das Modell 90 bei 40 % veralteten Werten, gewinnt EP — und
       die Abweichung wird wie eine Klemmung protokolliert.
    2. Aggregation als **schwächstes Glied** über alle Teilnoten (siehe `aggregate_confidence`).
    3. Fehlen Teilnoten ganz (älterer Prompt/Template), bleibt eine vom Modell gelieferte
       Gesamtnote unangetastet — kein stiller Wechsel des Verhaltens.
    """
    parts = normalized.get("konfidenz_teilnoten")
    if not isinstance(parts, dict) or not parts:
        return normalized.get("confidence")

    ep_note = _context_data_quality(context)
    model_note = parts.get("datenlage")
    if (
        ep_note is not None
        and not isinstance(model_note, bool)
        and isinstance(model_note, int | float)
        and model_note > ep_note
    ):
        clamped.append(
            f"konfidenz.datenlage: {int(model_note)} -> {ep_note} "
            "(EP-Messung der Datenlage schlägt die Selbsteinschätzung)"
        )
        parts["datenlage"] = ep_note

    # Nur die definierten Teilnoten behalten — erfundene Schlüssel gehen nicht in die Aggregation.
    normalized["konfidenz_teilnoten"] = {
        key: value for key, value in parts.items() if key in CONFIDENCE_PARTS
    }
    return aggregate_confidence(normalized["konfidenz_teilnoten"])


def validate(
    plan_dict: dict,
    constraints: list[DeviceConstraint],
    *,
    now: datetime | None = None,
    context: dict | None = None,
    min_confidence: int | None = None,
) -> ValidationResult:
    """Validiert einen Kandidatenplan gegen Schema + harte Grenzen (Stufen 1–4 und 6).

    Liefert bei Strukturfehlern `ok=False` ohne Normalplan; sonst einen normalisierten
    (geklemmten) Plan plus Liste der Klemmungen und etwaiger Ablehnungsgründe.

    `context` ist der Kontext, aus dem der Plan entstand — daraus stammt die gemessene Datenlage
    für die Konfidenz-Gegenrechnung (Stufe 4). `min_confidence` ist die Schwelle, unterhalb der
    ein gültiger Plan **nicht veröffentlicht** wird (Stufe 6, `publish_blocked`).
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

    # Stufe 4 + 6 (D-064): Konfidenz gegenrechnen, aggregieren und als Veröffentlichungs-Gate
    # auswerten. Ein zu unsicherer Plan ist nicht ungültig — er wird nur nicht wirksam.
    confidence = _resolve_confidence(normalized, context, clamped)
    normalized["confidence"] = confidence
    publish_blocked: str | None = None
    if (
        min_confidence is not None
        and confidence is not None
        and confidence < int(min_confidence)
    ):
        parts = normalized.get("konfidenz_teilnoten") or {}
        schwaechste = min(parts, key=lambda k: parts[k]) if parts else None
        grund = f"Konfidenz {confidence} % unter der Schwelle {int(min_confidence)} %"
        publish_blocked = f"{grund} (schwächste Teilnote: {schwaechste})" if schwaechste else grund

    return ValidationResult(
        ok=not errors,
        errors=errors,
        clamped=clamped,
        normalized_plan=normalized,
        publish_blocked=publish_blocked,
    )
