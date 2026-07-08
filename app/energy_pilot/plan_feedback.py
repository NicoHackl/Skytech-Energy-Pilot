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
- `geschutzte_mindestleistung_w_vorschlag` ↔ `geschuetzte_mindestleistung_w` (roher
  Schutz-Sockel, Toleranz ±1 W) — **nicht** `schutz_w` (= Sockel + Reserve + Puffer, geklemmt),
- `geschutzte_mindestleistung_a_vorschlag` ↔ `geschuetzte_mindestleistung_a` (roher
  Schutz-Sockel in Ampere, Toleranz ±0.1 A),
- `freigabe_vorschlag` ↔ `eligible` (weich: HEMS-`eligible` umfasst zusätzlich
  technische Freigabe + Modus, daher „Vorschlag frei, HEMS nicht eligible" = unbekannt).
Felder ohne HEMS-Pendant (Heizstab-`max_temperatur` D-035) sind nur
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
# Ampere-Pendant: die HEMS-seitige W→A-Umrechnung (Phasen × gemessene Spannung) bringt mehr
# Drift als der reine Watt-Vergleich, daher gröber. 0.1 A ≈ 23 W bei 230 V.
AMP_TOLERANCE_A = 0.1


# Vergleichs-Slug für das Geräte-Matching: casefold + HA-Umlaut-Faltung
# (ü→u, ä→a, ö→o, ß→ss) + nur Alphanumerik. Robust gegen die typischen
# HA-Naming-Divergenzen zwischen EP- und HEMS-Config (ü/u, `_`/Leerzeichen,
# Groß/Klein), die sonst ein „nicht im HEMS gefunden" trotz gleicher Geräte
# verursachen. Die Faltung folgt der HA-Slugifizierung (vgl. HEMS-Residual-Entity).
_UMLAUT_MAP = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def _slug(value: object) -> str:
    s = str(value or "").strip().casefold().translate(_UMLAUT_MAP)
    return "".join(ch for ch in s if ch.isalnum())


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
    """Findet das HEMS-Statusgerät zum EP-Gerät über Label oder Name/id (slug-tolerant).

    Beide EP-Achsen (Label, Name) werden gegen beide HEMS-Achsen (Label, id)
    geprüft – jeweils slug-gefaltet, damit ein Umlaut-/Trenner-/Groß-Klein-Unterschied
    (z.B. EP-Label „Heizlüfter 1" ↔ HEMS-id „heizlufter_1") nicht zu „nicht gefunden" führt.
    """
    keys = {_slug(label), _slug(name)} - {""}
    for hd in hems_devices:
        if isinstance(hd, dict) and ({_slug(hd.get("label")), _slug(hd.get("id"))} & keys):
            return hd
    return None


def _compare(field: str, suggested: object, hd: dict) -> tuple[str, object]:
    """Vergleicht ein Vorschlagsfeld mit dem HEMS-Ist-Wert. Liefert (Status, Ist-Wert)."""
    if field == "prio_vorschlag":
        ist = hd.get("priority")
        if _is_number(ist) and int(ist) == int(suggested):
            return "match", ist
        return ("abweichend", ist) if ist is not None else ("unbekannt", None)

    if field.startswith("geschutzte_mindestleistung"):
        # Vergleich gegen den ROHEN Schutz-Sockel je Einheit (geschuetzte_mindestleistung_w
        # bzw. _a) – NICHT gegen den effektiven HEMS-Schutz schutz_w/schutz_a. schutz_w =
        # Sockel + reserve_w + global_puffer_w (geklemmt); ein Vergleich dagegen meldete
        # fälschlich „abweichend" und zeigte einen anderen Wert als der User im Helfer sieht.
        # Fehlt das Rohfeld (älterer HEMS-Stand) -> None -> „unbekannt"
        # (bewusst kein Rückfall auf schutz_w, sonst wäre der Bug zurück).
        is_ampere = field.endswith("_a_vorschlag")
        ist = (
            hd.get("geschuetzte_mindestleistung_a")
            if is_ampere
            else hd.get("geschuetzte_mindestleistung_w")
        )
        tolerance = AMP_TOLERANCE_A if is_ampere else POWER_TOLERANCE_W
        if _is_number(ist):
            if abs(float(ist) - float(suggested)) <= tolerance:
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

    # Kein HEMS-Pendant (z.B. Heizstab-Temperatur D-035): nur informativ.
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
