"""Tages-Aggregation eines Messwert-Verlaufs (D-065) — reine Funktionen, kein I/O.

Warum es das gibt: der `RollingAggregator` reicht 60 Minuten weit und liegt nur im
Prozessspeicher (`aggregation.py`). Für die Frage, die eine vorausschauende Planung wirklich
stellt — „wie viel Wärme kam in den letzten Tagen ohne Strom in den Speicher, und schafft das
die nächsten Tage auch?" — braucht es **Tage**, nicht Minuten. Diese Datei rechnet aus einem
HA-Verlauf die Tageskennzahlen; das Holen und Speichern macht `history_collector.py`.

Kalendertage werden in **Berliner Zeit** geschnitten (eiserne Regel 15), inklusive
Sommerzeitumstellung. Ein Tag ist damit nicht immer 24 Stunden lang — genau deshalb steht die
Fensterberechnung hier und nicht als `timedelta(days=1)` irgendwo im Collector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Berlin")

# Wie eine Größe über den Tag verdichtet wird. Ergibt sich aus der Einheit, nicht aus dem Namen:
# - `level`: Zustandsgröße (°C, %, SOC) -> Min/Max/Mittel/Differenz. Energie ist hier sinnlos.
# - `power`: Leistung (W) -> zusätzlich über die Zeit zu kWh integriert.
# - `counter`: monoton steigender Zähler (kWh) -> Energie = Differenz über den Tag.
KIND_LEVEL = "level"
KIND_POWER = "power"
KIND_COUNTER = "counter"

_UNIT_KIND: dict[str, str] = {
    "W": KIND_POWER,
    "kW": KIND_POWER,
    "kWh": KIND_COUNTER,
    "Wh": KIND_COUNTER,
}

# Zustände, die HA für „kein Wert" liefert; sie dürfen eine Tagesbilanz nicht verfälschen.
_INVALID_STATES = frozenset({"unknown", "unavailable", "none", ""})

# Obergrenze der Zeitspanne, über die ein einzelner Messpunkt noch als gültig gilt.
#
# Wichtig für das Verständnis: HA speichert mit `significant_changes_only` **Änderungen**, und ein
# Zustand gilt bis zur nächsten Änderung. Ein Abstand von einer Stunde ist damit der Normalfall
# und **keine** Lücke — eine Leistung von 1000 W, die eine Stunde lang nicht neu gemeldet wird,
# hat genau 1 kWh geliefert. Ein zu kleiner Wert hier würde also die halbe Tagesenergie
# verschlucken (genau dieser Fehler steckte in der ersten Fassung mit 900 s).
#
# Die Grenze schützt nur gegen den unplausiblen Fall: HA oder der Sensor waren stundenlang weg,
# und der letzte bekannte Wert würde bis zum nächsten Lebenszeichen hochgerechnet. Sechs Stunden
# sind für eine Leistungsgröße, die sich ständig ändert, jenseits jeder normalen Meldepause.
MAX_GAP_S = 21600.0


def kind_for_unit(unit: str | None) -> str:
    """Verdichtungsart aus der Einheit; unbekannt/leer gilt als Zustandsgröße."""
    return _UNIT_KIND.get((unit or "").strip(), KIND_LEVEL)


@dataclass(frozen=True)
class DayAggregate:
    """Tageskennzahlen einer Messgröße. `None` heißt „nicht bestimmbar", nie „null"."""

    tag: date
    wert_min: float | None = None
    wert_max: float | None = None
    wert_mittel: float | None = None
    wert_delta: float | None = None
    energie_kwh: float | None = None
    proben: int = 0

    @property
    def leer(self) -> bool:
        """True, wenn der Tag keine verwertbare Probe hatte."""
        return self.proben == 0


def day_bounds(tag: date) -> tuple[datetime, datetime]:
    """Start und Ende eines Kalendertags in Berliner Zeit, **als UTC** (Ende = Start des Folgetags).

    Zwei Fallen, die beide echte Rechenfehler verursacht haben:

    1. Über die Zeitumstellung ist ein Tag 23 bzw. 25 Stunden lang. Deshalb wird das Ende aus dem
       Folgetag gebildet und nie als `start + 24 h`.
    2. Python subtrahiert zwei aware Zeitpunkte mit **derselben** `tzinfo` als Wanduhr-Differenz
       und ignoriert die Umstellung dabei — `30.03. 00:00` minus `29.03. 00:00` ergäbe 24 h statt
       23 h. Da genau diese Differenzen in das zeitgewichtete Mittel und die Energie eingehen,
       werden die Grenzen nach UTC normalisiert. Vergleiche mit den (ebenfalls aware) Proben
       bleiben davon unberührt.
    """
    naechster = tag + timedelta(days=1)
    start = datetime(tag.year, tag.month, tag.day, tzinfo=LOCAL_TZ).astimezone(UTC)
    ende = datetime(naechster.year, naechster.month, naechster.day, tzinfo=LOCAL_TZ).astimezone(UTC)
    return start, ende


def local_date(moment: datetime) -> date:
    """Kalendertag eines Zeitpunkts in Berliner Zeit."""
    return moment.astimezone(LOCAL_TZ).date()


def _as_float(value: object) -> float | None:
    """Zahl aus einem HA-Zustand; `unknown`/`unavailable`/Text ergeben None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() in _INVALID_STATES:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _row_time(row: dict) -> datetime | None:
    """Zeitstempel einer Verlaufszeile (`last_changed`, sonst `last_updated`)."""
    for key in ("last_changed", "last_updated"):
        raw = row.get(key)
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(raw, datetime):
            return raw
    return None


def parse_samples(rows: list[dict]) -> list[tuple[datetime, float]]:
    """Verlaufszeilen von HA in eine sortierte Liste `(Zeit, Wert)` überführen.

    Unbrauchbare Zeilen (kein Zeitstempel, `unavailable`, Textzustand) entfallen still — sie
    sind der Normalfall bei Neustarts und dürfen die Bilanz nicht kippen.
    """
    samples: list[tuple[datetime, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        moment = _row_time(row)
        value = _as_float(row.get("state"))
        if moment is not None and value is not None:
            samples.append((moment, value))
    samples.sort(key=lambda item: item[0])
    return samples


def aggregate_day(
    samples: list[tuple[datetime, float]], tag: date, kind: str = KIND_LEVEL
) -> DayAggregate:
    """Verdichtet die Proben **eines** Kalendertags zu Tageskennzahlen.

    Erwartet die Proben des Tages (Fremdproben werden verworfen). Das Mittel ist
    **zeitgewichtet**: ein Temperaturfühler liefert unregelmäßig, und ein arithmetisches Mittel
    über Proben würde eine Phase mit dichten Meldungen überbewerten.

    `energie_kwh` je Verdichtungsart:
    - `power`: Integral der Leistung über die Zeit (Lücken über `MAX_GAP_S` werden ausgelassen,
      damit ein Ausfall nicht als konstante Last durchgeht).
    - `counter`: Differenz des Zählers über den Tag.
    - `level`: keine Energie (None) — eine Temperatur hat keine.
    """
    start, ende = day_bounds(tag)
    im_tag = [(m, v) for m, v in samples if start <= m < ende]
    if not im_tag:
        return DayAggregate(tag=tag)

    werte = [v for _m, v in im_tag]
    minimum = min(werte)
    maximum = max(werte)
    delta = werte[-1] - werte[0]

    # Zeitgewichtetes Mittel und (bei Leistung) Energie in einem Durchlauf.
    gewichtete_summe = 0.0
    dauer_s = 0.0
    energie_ws = 0.0
    for index, (moment, wert) in enumerate(im_tag):
        naechster = im_tag[index + 1][0] if index + 1 < len(im_tag) else ende
        spanne = (naechster - moment).total_seconds()
        if spanne <= 0:
            continue
        gewichtete_summe += wert * spanne
        dauer_s += spanne
        if kind == KIND_POWER and spanne <= MAX_GAP_S:
            energie_ws += wert * spanne
    mittel = gewichtete_summe / dauer_s if dauer_s > 0 else werte[-1]

    energie: float | None = None
    if kind == KIND_POWER:
        energie = energie_ws / 3_600_000.0  # Ws -> kWh
    elif kind == KIND_COUNTER:
        # Zählerstände können durch einen Geräte-Reset zurückspringen; ein negativer Zuwachs ist
        # dann kein Energierückfluss, sondern ein Artefakt.
        energie = max(0.0, delta)

    return DayAggregate(
        tag=tag,
        wert_min=round(minimum, 3),
        wert_max=round(maximum, 3),
        wert_mittel=round(mittel, 3),
        wert_delta=round(delta, 3),
        energie_kwh=None if energie is None else round(energie, 3),
        proben=len(im_tag),
    )


def days_in_window(now: datetime, tage: int) -> list[date]:
    """Die letzten `tage` Kalendertage in Berliner Zeit, ältester zuerst (heute eingeschlossen)."""
    heute = local_date(now)
    anzahl = max(1, int(tage))
    return [heute - timedelta(days=offset) for offset in range(anzahl - 1, -1, -1)]


def water_energy_kwh(volumen_liter: float, delta_c: float) -> float:
    """Wärmemenge in kWh für eine Temperaturdifferenz in einem Wasserspeicher (D-066).

    `m · c · ΔT` mit c = 4,182 kJ/(kg·K) und 1 Liter ≈ 1 kg. Bewusst eine **Schätzung** unter der
    Annahme eines durchmischten Speichers: ein geschichteter Puffer mit einem einzigen Fühler
    gibt nicht mehr her. Gut genug für „reicht der Inhalt drei Tage", nicht für Feinregelung —
    diese Einschränkung steht auch im KI-Kontext, damit das Modell die Zahl nicht überinterpretiert.
    """
    return volumen_liter * 4.182 * delta_c / 3600.0
