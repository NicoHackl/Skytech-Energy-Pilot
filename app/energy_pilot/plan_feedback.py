"""Plan-Rückkopplung (M3): vergleicht EP-Vorschläge mit dem HEMS-Ist-Zustand.

Reine, testbare Ableitung (kein IO): nimmt den zuletzt gespeicherten EP-Plan
(`planner.latest_plan()`), die erkannten Geräte und den HEMS-`/api/status`-Payload und
leitet je Gerät **und** gesamt eine **beobachtete** Übereinstimmung ab.

Bewusst „beobachtend", nicht „bestätigt": In V1 (D-032/D-033) verdrahtet der User die
Vorschläge selbst in HA-Automationen — EP kann keine echte Annahme durch HEMS kennen,
nur ob die HEMS-Ist-Werte im Gültigkeitsfenster zu den Vorschlägen passen. Das
EP↔HEMS-Feld-Mapping hier dient **nur dem Lesen/Vergleichen** (nicht dem in B4 offenen
Schreibweg) und ist zentral gehalten, damit Ebene 2 (versionierte Plan-API) es
wiederverwenden kann.

Feld-Mapping (EP-Vorschlag ↔ HEMS-`to_status_dict`):
- `prio_vorschlag` ↔ `priority` (Gleichheit),
- `geschutzte_mindestleistung_w_vorschlag` ↔ `schutz_w` (Toleranz ±1 W),
- `freigabe_vorschlag` ↔ `eligible` (weich: HEMS-`eligible` umfasst zusätzlich
  technische Freigabe + Modus, daher „Vorschlag frei, HEMS nicht eligible" = unbekannt).
Felder ohne HEMS-Pendant (`_a`-Schutz, Heizstab-`max_temperatur` D-035) sind nur
informativ (Status `unbekannt`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from energy_pilot.devices import Device
from energy_pilot.plan_schema import SUGGESTION_FIELDS

# Gesamtstatus (für sensor.ep_plan_status + UI-Badge).
KEIN_PLAN = "kein_plan"
UNBEKANNT = "unbekannt"
KONFORM = "beobachtet_konform"
ABWEICHEND = "beobachtet_abweichend"

# Toleranz beim Leistungsvergleich (Rundung/Float-Drift).
POWER_TOLERANCE_W = 1.0


def _norm(value: object) -> str:
    return str(value or "").strip().casefold()


def _is_number(value: object) -> bool:
    """True für echte Zahlen (bool ist in Python ein int – hier ausgeschlossen)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _parse_dt(value: object) -> datetime | None:
    """Parst einen ISO-Zeitstempel tz-bewusst (naiv ⇒ UTC); None bei Fehlern."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _in_window(valid_from: object, valid_until: object, now: datetime) -> bool | None:
    start = _parse_dt(valid_from)
    end = _parse_dt(valid_until)
    if start is None or end is None:
        return None
    return start <= now <= end


def _match_hems_device(label: str, name: str, hems_devices: list) -> dict | None:
    """Findet das HEMS-Statusgerät zum EP-Gerät: primär über Label, sonst über id==Name."""
    tgt_label, tgt_name = _norm(label), _norm(name)
    for hd in hems_devices:
        if isinstance(hd, dict) and tgt_label and _norm(hd.get("label")) == tgt_label:
            return hd
    for hd in hems_devices:
        if isinstance(hd, dict) and tgt_name and _norm(hd.get("id")) == tgt_name:
            return hd
    return None


def _compare(field: str, suggested: object, hd: dict) -> tuple[str, object]:
    """Vergleicht ein Vorschlagsfeld mit dem HEMS-Ist-Wert. Liefert (Status, Ist-Wert)."""
    if field == "prio_vorschlag":
        ist = hd.get("priority")
        if _is_number(ist) and int(ist) == int(suggested):
            return "match", ist
        return ("abweichend", ist) if ist is not None else ("unbekannt", None)

    if field == "geschutzte_mindestleistung_w_vorschlag":
        ist = hd.get("schutz_w")
        if _is_number(ist):
            if abs(float(ist) - float(suggested)) <= POWER_TOLERANCE_W:
                return "match", ist
            return "abweichend", ist
        return "unbekannt", None

    if field == "freigabe_vorschlag":
        ist = hd.get("eligible")
        if isinstance(ist, bool):
            if bool(suggested) == ist:
                return "match", ist
            # Vorschlag frei, aber HEMS nicht eligible: kann an technischer Freigabe /
            # Modus liegen (nicht an der Freigabe selbst) ⇒ nicht als Abweichung werten.
            if bool(suggested) and not ist:
                return "unbekannt", ist
            return "abweichend", ist
        return "unbekannt", None

    # Kein HEMS-Pendant (z.B. `_a`-Schutz, Heizstab-Temperatur D-035): nur informativ.
    return "unbekannt", None


def _verdict(fields: list[dict]) -> str:
    statuses = {f["status"] for f in fields}
    if "abweichend" in statuses:
        return "abweichend"
    if "match" in statuses:
        return "konform"
    return "unbekannt"


def _overall(device_results: list[dict], in_window: bool | None) -> str:
    # Außerhalb des Gültigkeitsfensters ist keine belastbare Aussage möglich.
    if in_window is False:
        return UNBEKANNT
    verdicts = {d["verdict"] for d in device_results}
    if "abweichend" in verdicts:
        return ABWEICHEND
    if "konform" in verdicts:
        return KONFORM
    return UNBEKANNT


def derive_plan_feedback(
    latest: dict | None,
    devices: list[Device],
    hems_status: dict | None,
    *,
    now: datetime | None = None,
) -> dict:
    """Leitet die beobachtete Plan-Übereinstimmung ab (siehe Modul-Docstring).

    `latest` = `planner.latest_plan()` ({ok, plan, ...} oder None),
    `hems_status` = `/api/status`-Payload (oder None, wenn HEMS offline).
    """
    now = now or datetime.now(UTC)

    if not latest or not latest.get("ok") or not isinstance(latest.get("plan"), dict):
        return {
            "overall": KEIN_PLAN,
            "reason": "kein gültiger Plan vorhanden",
            "plan_id": None,
            "valid_until": None,
            "in_window": None,
            "devices": [],
        }

    plan = latest["plan"]
    plan_id = plan.get("plan_id")
    valid_until = plan.get("valid_until")
    in_window = _in_window(plan.get("valid_from"), valid_until, now)

    inner = hems_status.get("status") if isinstance(hems_status, dict) else None
    hems_devices = inner.get("devices") if isinstance(inner, dict) else None
    if not hems_devices:
        return {
            "overall": UNBEKANNT,
            "reason": "HEMS-Status nicht verfügbar",
            "plan_id": plan_id,
            "valid_until": valid_until,
            "in_window": in_window,
            "devices": [],
        }

    label_by_name = {d.name: d.label for d in devices}
    device_results: list[dict] = []
    for entry in plan.get("devices", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        label = label_by_name.get(name, name)
        hd = _match_hems_device(label, name, hems_devices)

        fields: list[dict] = []
        for field in SUGGESTION_FIELDS:
            value = entry.get(field)
            if value is None:
                continue
            if hd is None:
                fields.append(
                    {"feld": field, "vorschlag": value, "ist": None, "status": "unbekannt"}
                )
                continue
            status, ist = _compare(field, value, hd)
            fields.append({"feld": field, "vorschlag": value, "ist": ist, "status": status})

        device_results.append(
            {
                "name": name,
                "label": label,
                "matched": hd is not None,
                "verdict": _verdict(fields),
                "fields": fields,
            }
        )

    reason = "" if in_window is not False else "außerhalb Gültigkeitsfenster"
    return {
        "overall": _overall(device_results, in_window),
        "reason": reason,
        "plan_id": plan_id,
        "valid_until": valid_until,
        "in_window": in_window,
        "devices": device_results,
    }
