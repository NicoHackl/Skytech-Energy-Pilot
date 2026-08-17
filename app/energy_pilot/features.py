"""Gerechnete Geräte- und Systemmerkmale (D-066) — reine Funktionen, kein I/O.

Der Anlass in einem Satz: **derselbe Messwert kann zwei entgegengesetzte richtige Entscheidungen
begründen.** Ein Pufferspeicher mit 65 °C und drei sonnigen Tagen davor braucht keinen Strom; mit
65 °C und zwei trüben Tagen davor schon — sonst fällt er unter das Komfortminimum, wenn kein
Überschuss mehr kommt. Eine Schwelle auf 65 °C kann das nicht ausdrücken, eine **Bilanz** schon.

Diese Datei rechnet deshalb die Größen, aus denen die Bilanz folgt (`plan/longterm_plan.md`
§3.2/§3.3, dort als B1/B5 geführt und nie gebaut):

- je Speichergerät: Reserve über dem Komfortminimum, Bedarf bis zum Zielwert, der beobachtete
  **nicht-elektrische** Wärmeeintrag je Tag und daraus die Deckung in Tagen,
- systemweit: geglättete Grundlast und der daraus folgende PV-Überschuss.

Was hier **nicht** passiert: entscheiden. Es entstehen Zahlen, keine Vorschläge — die Abwägung
bleibt bei der KI (D-060). Fehlt eine Eingangsgröße, bleibt das Merkmal `None` und wird als
fehlend benannt; nie ein stiller Nullwert, der wie eine Messung aussieht (eiserne Regel 13).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from energy_pilot.device_speicher import SpeicherDaten
from energy_pilot.history import water_energy_kwh

# Mess-Rolle, auf die sich die Speicher-Kennwerte beziehen (D-061). EP führt genau eine
# Warmwasser-Rolle; die Kennwerte eines Geräts beschreiben also diesen einen Speicher.
HOT_WATER_ROLE = "hot_water_temp"
HOUSE_LOAD_ROLE = "house_load"

# Ab welcher Tagesenergie ein Tag als „mit elektrischem Eintrag" gilt. Ein Zähler rauscht im
# Hundertstel-Bereich (beim User real ~0,014 kWh/Tag ohne jeden Heizbetrieb) — das ist kein
# Heizen, sondern Messrauschen und Standby.
ELEKTRISCH_SCHWELLE_KWH = 0.1


@dataclass(frozen=True)
class FremdwaermeTag:
    """Beobachteter nicht-elektrischer Wärmeeintrag eines Tages."""

    tag: str
    delta_c: float
    energie_kwh: float | None
    wolken_mittel: float | None = None
    elektrisch_kwh: float | None = None


@dataclass(frozen=True)
class DeviceFeatures:
    """Bilanz-Merkmale eines Speichergeräts. `None` heißt jeweils „nicht bestimmbar"."""

    name: str
    ist_c: float | None = None
    komfort_min_c: float | None = None
    ziel_c: float | None = None
    volumen_liter: float | None = None
    reserve_kwh: float | None = None
    energiebedarf_kwh: float | None = None
    fremdwaerme_tage: tuple[FremdwaermeTag, ...] = ()
    fremdwaerme_mittel_kwh: float | None = None
    deckung_tage: float | None = None
    fehlt: tuple[str, ...] = ()
    hinweise: tuple[str, ...] = field(default_factory=tuple)


def _state_value(state: dict, role: str) -> float | None:
    """Letztwert einer Mess-Rolle aus dem Collector-Snapshot (`latest` oder `value`)."""
    info = state.get(role)
    if not isinstance(info, dict):
        return None
    for key in ("latest", "value"):
        raw = info.get(key)
        if isinstance(raw, int | float) and not isinstance(raw, bool):
            return float(raw)
    return None


def _day_value(tag: dict, groesse: str, feld: str) -> float | None:
    """Einzelwert einer Größe aus einer Rückblick-Tageszeile."""
    eintrag = (tag.get("groessen") or {}).get(groesse)
    if not isinstance(eintrag, dict):
        return None
    raw = eintrag.get(feld)
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw)
    return None


def _electric_kwh(tag: dict, quellen: tuple[str, ...]) -> float | None:
    """Summe der elektrischen Tagesenergie eines Geräts über seine Energie-Quellen."""
    werte = [_day_value(tag, groesse, "energie_kwh") for groesse in quellen]
    vorhanden = [w for w in werte if w is not None]
    return sum(vorhanden) if vorhanden else None


def build_device_features(
    name: str,
    speicher: SpeicherDaten,
    state: dict,
    rueckblick: list[dict],
    *,
    strom_quellen: tuple[str, ...] = (),
    wolken_groesse: str = "wolken",
) -> DeviceFeatures:
    """Bilanz-Merkmale eines Speichergeräts aus Kennwerten, Ist-Zustand und Rückblick.

    `strom_quellen` sind die Rückblick-Schlüssel, unter denen der **elektrische** Eintrag dieses
    Geräts liegt (Leistungs- oder Zählergröße). Nur Tage ohne nennenswerten elektrischen Eintrag
    taugen als Messung des Fremdwärme-Gewinns — an einem Tag mit laufendem Heizstab lässt sich
    nicht trennen, woher die Wärme kam.
    """
    ist = _state_value(state, HOT_WATER_ROLE)
    fehlt: list[str] = list(speicher.fehlende_felder)
    hinweise: list[str] = []
    if ist is None:
        fehlt.append(f"Mess-Rolle {HOT_WATER_ROLE}")

    volumen = speicher.volumen_liter
    reserve = bedarf = None
    if volumen is not None and ist is not None and speicher.komfort_min_c is not None:
        reserve = round(water_energy_kwh(volumen, ist - speicher.komfort_min_c), 2)
    if volumen is not None and ist is not None and speicher.ziel_c is not None:
        bedarf = round(max(0.0, water_energy_kwh(volumen, speicher.ziel_c - ist)), 2)

    # Fremdwärme: nur Tage ohne elektrischen Eintrag zählen als Messung.
    tage: list[FremdwaermeTag] = []
    for eintrag in rueckblick:
        delta = _day_value(eintrag, HOT_WATER_ROLE, "delta")
        if delta is None:
            continue
        elektrisch = _electric_kwh(eintrag, strom_quellen)
        if elektrisch is not None and elektrisch > ELEKTRISCH_SCHWELLE_KWH:
            continue
        tage.append(
            FremdwaermeTag(
                tag=str(eintrag.get("tag")),
                delta_c=round(delta, 2),
                energie_kwh=(
                    round(water_energy_kwh(volumen, delta), 2) if volumen is not None else None
                ),
                wolken_mittel=_day_value(eintrag, wolken_groesse, "mittel"),
                elektrisch_kwh=elektrisch,
            )
        )
    if not strom_quellen:
        hinweise.append(
            "Für dieses Gerät ist keine elektrische Energiegröße im Rückblick hinterlegt — die "
            "Fremdwärme-Tage konnten nicht gegen den Heizbetrieb geprüft werden."
        )

    mittel = None
    energien = [t.energie_kwh for t in tage if t.energie_kwh is not None]
    if energien:
        mittel = round(sum(energien) / len(energien), 2)

    # Deckung: nur sinnvoll, wenn der Speicher ohne Strom tatsächlich verliert.
    deckung = None
    if reserve is not None and mittel is not None:
        if mittel < 0:
            deckung = round(reserve / abs(mittel), 1)
        else:
            hinweise.append(
                "Der Speicher hat an den ausgewerteten Tagen ohne Strom gewonnen, nicht verloren "
                "— eine Deckungsdauer ist daraus nicht ableitbar."
            )

    if volumen is not None:
        hinweise.append(
            "Die kWh-Angaben sind eine Schätzung für einen durchmischten Speicher (m·c·ΔT). Ein "
            "geschichteter Puffer mit einem Fühler gibt nicht mehr her: gut für „reicht es einige "
            "Tage\", nicht für Feinregelung."
        )

    return DeviceFeatures(
        name=name,
        ist_c=ist,
        komfort_min_c=speicher.komfort_min_c,
        ziel_c=speicher.ziel_c,
        volumen_liter=volumen,
        reserve_kwh=reserve,
        energiebedarf_kwh=bedarf,
        fremdwaerme_tage=tuple(tage),
        fremdwaerme_mittel_kwh=mittel,
        deckung_tage=deckung,
        fehlt=tuple(dict.fromkeys(fehlt)),
        hinweise=tuple(hinweise),
    )


def base_load_w(rueckblick: list[dict], *, role: str = HOUSE_LOAD_ROLE) -> float | None:
    """Geglättete Grundlast aus dem Rückblick: Mittel der Tagesminima des Hausverbrauchs.

    Das Tagesminimum ist praktisch der Nachtwert — Kühlschrank, Standby, Umwälzpumpe. Über
    mehrere Tage gemittelt ist das eine belastbare Untergrenze, ohne dass EP dafür einen eigenen
    Verbrauchsprofil-Mechanismus braucht.
    """
    minima = [
        value
        for value in (_day_value(tag, role, "min") for tag in rueckblick)
        if value is not None
    ]
    return round(sum(minima) / len(minima), 1) if minima else None


def build_system_features(forecast: dict, rueckblick: list[dict]) -> dict:
    """Systemweite Merkmale: Grundlast und der daraus folgende PV-Überschuss (§3.2/B5).

    `forecast` ist der verdichtete PV-Prognoseblock (`plan_context._condense_forecast`). Der
    Überschuss ist bewusst konservativ: Prognose minus Grundlast über den jeweiligen Zeitraum.
    Ohne Grundlast bleibt der Überschuss `None` statt gleich der Bruttoprognose — eine
    Bruttozahl als Überschuss auszugeben wäre eine stille Übertreibung.
    """
    grundlast = base_load_w(rueckblick)
    out: dict[str, object] = {"grundlast_w": grundlast}
    if grundlast is None:
        out["hinweis"] = (
            "Ohne Grundlast (Rückblick des Hausverbrauchs fehlt) ist kein Überschuss berechenbar; "
            "die PV-Prognose ist ein Bruttowert."
        )
        return out

    werte = {v.get("key"): v.get("total") for v in (forecast.get("values") or [])}
    grundlast_kwh_tag = grundlast * 24 / 1000.0
    ueberschuss: dict[str, float] = {}
    # `remaining_today` deckt nur den Rest des Tages — die Grundlast dafür anteilig abziehen wäre
    # eine Scheingenauigkeit, weil EP die Reststunden hier nicht kennt. Deshalb nur `tomorrow`
    # als voller Tag, plus der Rest heute als Bruttowert mit Namen.
    morgen = werte.get("tomorrow")
    if isinstance(morgen, int | float) and not isinstance(morgen, bool):
        ueberschuss["morgen_kwh"] = round(float(morgen) - grundlast_kwh_tag, 2)
    if ueberschuss:
        out["ueberschuss"] = ueberschuss
    out["grundlast_kwh_pro_tag"] = round(grundlast_kwh_tag, 2)
    return out
