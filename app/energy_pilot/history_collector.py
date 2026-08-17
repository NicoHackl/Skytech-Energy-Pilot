"""Tages-Rückblick aus der HA-Historie holen und persistieren (D-065).

Der Grund steht in `history.py`: für „schafft die Solarthermie die nächsten drei Tage?" braucht
es Tageswerte, und die hat EP bisher nirgends — der `RollingAggregator` reicht 60 Minuten weit
und ist nach einem Neustart leer.

Zwei Eigenschaften, die den Aufwand begrenzen:

- **Abgeschlossene Tage werden genau einmal geholt.** Ein Tag mit `vollstaendig = 1` wird nie
  erneut angefragt. Nur der laufende Tag (und ein noch offener Vortag) werden nachgerechnet.
  Ohne das wären es je Lauf fünfstellige Zeilenzahlen allein für einen Temperaturfühler.
- **Die eigene Tabelle wächst über den Recorder hinaus.** HA hält Rohdaten üblicherweise ~10
  Tage; ein einmal aggregierter Tag bleibt in `daily_history` dauerhaft erhalten.

Fehler blockieren nie (eiserne Regel 13): ein fehlgeschlagener Verlaufsabruf lässt den Tag
unvollständig und wird beim nächsten Lauf erneut versucht.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

from energy_pilot.history import (
    KIND_COUNTER,
    KIND_POWER,
    DayAggregate,
    aggregate_day,
    day_bounds,
    days_in_window,
    kind_for_unit,
    local_date,
    parse_samples,
)
from energy_pilot.logging_setup import log

# Standard-Rückblickfenster: sieben Tage. Genug, um „die letzten Tage" gegen die Bewölkung zu
# stellen, und klein genug, dass der Kontext schlank bleibt (eiserne Regel 12).
DEFAULT_DAYS = 7
# Abstand zweier Aggregationsläufe. Tageswerte ändern sich langsam; stündlich reicht und hält
# die Last auf dem HA-Recorder klein.
DEFAULT_INTERVAL_S = 3600.0


@dataclass(frozen=True)
class HistorySource:
    """Eine zu historisierende Messgröße: sprechender Schlüssel + HA-Entität + Einheit."""

    groesse: str
    entity_id: str
    unit: str = ""
    label: str = ""

    @property
    def kind(self) -> str:
        """Verdichtungsart (`level`/`power`/`counter`) aus der Einheit."""
        return kind_for_unit(self.unit)


def sources_from(mapping: dict, devices: list) -> list[HistorySource]:
    """Leitet die zu historisierenden Größen ab — **ohne** neue Konfiguration.

    Zwei Quellen, beide schon vorhanden:

    - die Mess-Rollen aus der Addon-Config (`entity_map.mapping_from_options`) — darunter die
      Warmwasser- und die Außentemperatur (D-061) sowie PV-Leistung und Hausverbrauch, aus denen
      Tagesertrag und Grundlast folgen,
    - je Gerät die user-gepflegten **Zusatzwerte** (D-047). Erst dadurch kennt der Rückblick die
      elektrische Energie eines Geräts und kann Tage mit Heizbetrieb von Tagen ohne trennen.

    Die `ems_*`-Standardfelder bleiben bewusst **draußen**: `min_technisch`/`max_technisch` tragen
    die Einheit W, sind aber **Grenzwerte** und keine Leistung — als Leistung integriert ergäbe
    ein 3500-W-Limit rund 84 kWh am Tag und jeder Tag sähe wie „geheizt" aus. `leistung_w` einer
    Binärlast ist die Nennleistung, ebenfalls keine Messung, und `technische_freigabe` ist ein
    Schalter. Ein Verlauf über konstante Werte hätte ohnehin keinen Erkenntniswert.

    Der Schlüssel eines Gerätewerts ist `<gerät>.<feld>`, damit er stabil und eindeutig ist.
    """
    out: list[HistorySource] = []
    for role_key, eintrag in (mapping or {}).items():
        entity_id = getattr(eintrag, "entity_id", None)
        if entity_id:
            out.append(
                HistorySource(
                    groesse=str(role_key),
                    entity_id=str(entity_id),
                    unit=_role_unit(str(role_key)),
                    label=str(role_key),
                )
            )
    for device in devices or []:
        for extra in getattr(device, "extras", ()):
            if not extra.read_entity_id:
                continue
            out.append(
                HistorySource(
                    groesse=f"{device.name}.{extra.read_key}",
                    entity_id=extra.read_entity_id,
                    unit=extra.unit or "",
                    label=f"{device.label} – {extra.display_label}",
                )
            )
    return out


def _role_unit(role_key: str) -> str:
    """Einheit einer Mess-Rolle (bestimmt die Verdichtungsart); unbekannt => leer."""
    from energy_pilot.roles import ROLES_BY_KEY

    role = ROLES_BY_KEY.get(role_key)
    return role.unit if role is not None else ""


def energy_sources_for(device_name: str, sources: tuple[HistorySource, ...]) -> tuple[str, ...]:
    """Rückblick-Schlüssel eines Geräts, die eine **Energie** tragen (Leistung oder Zähler).

    Grundlage für `features.build_device_features`: nur damit lassen sich Tage mit elektrischem
    Eintrag von Tagen ohne unterscheiden — und nur letztere messen die Fremdwärme.
    """
    prefix = f"{device_name}."
    return tuple(
        source.groesse
        for source in sources
        if source.groesse.startswith(prefix) and source.kind in (KIND_POWER, KIND_COUNTER)
    )


class HistoryCollector:
    """Holt Tageswerte aus der HA-Historie und legt sie in `daily_history` ab."""

    def __init__(
        self,
        ha_client: object | None,
        db: sqlite3.Connection | None,
        logger: logging.Logger | None = None,
        *,
        days: int = DEFAULT_DAYS,
        interval_s: float = DEFAULT_INTERVAL_S,
    ) -> None:
        self.ha_client = ha_client
        self.db = db
        self.logger = logger
        self.days = max(1, int(days))
        self.interval_s = float(interval_s)
        self.sources: tuple[HistorySource, ...] = ()
        self.last_collect_ts: float | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        """Ohne HA-Client, DB oder Quellen gibt es nichts zu tun."""
        return self.ha_client is not None and self.db is not None and bool(self.sources)

    def set_sources(self, sources: list[HistorySource]) -> None:
        """Legt die zu historisierenden Größen fest (aus Rollen-Mapping und Geräten abgeleitet)."""
        # Doppelte Schlüssel würden sich in der Tabelle gegenseitig überschreiben (PK tag+groesse).
        seen: dict[str, HistorySource] = {}
        for source in sources:
            if source.groesse and source.entity_id and source.groesse not in seen:
                seen[source.groesse] = source
        self.sources = tuple(seen.values())

    def _refresh_due(self, now: float) -> bool:
        return self.last_collect_ts is None or (now - self.last_collect_ts) >= self.interval_s

    async def collect_once(self, now: float | None = None) -> None:
        """Rechnet alle offenen Tage des Fensters nach; sonst No-op (Drossel)."""
        now = time.time() if now is None else now
        if not self.enabled or not self._refresh_due(now):
            return
        moment = datetime.fromtimestamp(now, tz=UTC)
        heute = local_date(moment)
        offen = self._open_days(moment)
        if not offen:
            self.last_collect_ts = now
            return

        geschrieben = 0
        for source in self.sources:
            for tag in offen:
                if await self._aggregate_and_store(source, tag, heute=heute, jetzt=moment):
                    geschrieben += 1
        self.last_collect_ts = now
        if self.logger and geschrieben:
            log(
                self.logger, "info", "Tages-Rückblick aktualisiert",
                context={"tage": [t.isoformat() for t in offen], "eintraege": geschrieben},
            )

    def _open_days(self, moment: datetime) -> list[date]:
        """Tage des Fensters, für die noch nicht alle Größen abgeschlossen vorliegen."""
        fenster = days_in_window(moment, self.days)
        fertig = self._complete_days()
        return [tag for tag in fenster if tag.isoformat() not in fertig]

    def _complete_days(self) -> set[str]:
        """Tage, für die **jede aktuell konfigurierte** Größe als abgeschlossen gespeichert ist.

        Die Einschränkung auf die aktuellen Quellen ist wesentlich, nicht kosmetisch: würde hier
        einfach die Zeilenzahl gezählt, blähten Zeilen einer **entfernten** Größe den Zähler auf
        (z.B. `grid_power` nach dem Wegfall der Rolle). Ein Tag könnte dadurch als abgeschlossen
        gelten, obwohl eine echte Quelle noch fehlt — und würde nie nachgeholt.
        """
        if self.db is None or not self.sources:
            return set()
        keys = [source.groesse for source in self.sources]
        platzhalter = ",".join("?" for _ in keys)
        try:
            rows = self.db.execute(
                "SELECT tag, COUNT(*) AS fertig FROM daily_history "
                f"WHERE vollstaendig = 1 AND groesse IN ({platzhalter}) GROUP BY tag",
                keys,
            ).fetchall()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive, blockiert nie
            return set()
        return {row["tag"] for row in rows if row["fertig"] >= len(keys)}

    async def _aggregate_and_store(
        self, source: HistorySource, tag: date, *, heute: date, jetzt: datetime
    ) -> bool:
        """Holt den Verlauf eines Tages, verdichtet ihn und speichert das Ergebnis."""
        start, ende = day_bounds(tag)
        # Der laufende Tag ist noch nicht abgeschlossen — nur bis jetzt abfragen und **nicht**
        # als vollständig markieren, sonst friert der halbe Tag ein.
        laufend = tag >= heute
        bis = min(ende, jetzt) if laufend else ende
        try:
            rows = await self.ha_client.get_history(source.entity_id, start, bis)  # type: ignore[union-attr]
        except Exception as exc:  # kontrolliert: nie Crash (eiserne Regel 13)
            self.last_error = f"{source.entity_id}: {exc}"
            if self.logger:
                log(
                    self.logger, "warning", "Verlauf konnte nicht gelesen werden",
                    context={"entity": source.entity_id, "tag": tag.isoformat(),
                             "error": str(exc)},
                )
            return False
        aggregat = aggregate_day(parse_samples(rows), tag, source.kind)
        self._store(source, aggregat, vollstaendig=not laufend)
        return True

    def _store(
        self, source: HistorySource, aggregat: DayAggregate, *, vollstaendig: bool
    ) -> None:
        """Speichert (UPSERT) die Tageskennzahlen einer Größe."""
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO daily_history (tag, groesse, entity_id, wert_min, wert_max, "
                "wert_mittel, wert_delta, energie_kwh, proben, vollstaendig, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')) "
                "ON CONFLICT(tag, groesse) DO UPDATE SET "
                "entity_id = excluded.entity_id, wert_min = excluded.wert_min, "
                "wert_max = excluded.wert_max, wert_mittel = excluded.wert_mittel, "
                "wert_delta = excluded.wert_delta, energie_kwh = excluded.energie_kwh, "
                "proben = excluded.proben, vollstaendig = excluded.vollstaendig, "
                "updated_at = datetime('now')",
                (
                    aggregat.tag.isoformat(), source.groesse, source.entity_id,
                    aggregat.wert_min, aggregat.wert_max, aggregat.wert_mittel,
                    aggregat.wert_delta, aggregat.energie_kwh, aggregat.proben,
                    1 if vollstaendig else 0,
                ),
            )
            self.db.commit()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive
            pass

    def snapshot(self, days: int | None = None, now: datetime | None = None) -> list[dict]:
        """Tageszeilen für Kontext und UI, ältester Tag zuerst.

        Je Tag ein Eintrag mit allen Größen als Unterobjekt. Tage ohne jede Probe entfallen —
        ein leerer Tag trägt keine Information und würde nur Kontext kosten.

        Es werden nur die **aktuell konfigurierten** Größen ausgegeben. Andernfalls schleppte eine
        entfernte Messgröße (z.B. `grid_power` nach dem Wegfall der Rolle) ihre alten Zeilen
        dauerhaft in Rückblick, UI und KI-Kontext — ein Geisterwert mit einem Namen, den das System
        nicht mehr kennt.
        """
        if self.db is None:
            return []
        fenster = days_in_window(now or datetime.now(UTC), days or self.days)
        erlaubt = {tag.isoformat() for tag in fenster}
        bekannt = {source.groesse for source in self.sources}
        try:
            rows = self.db.execute(
                "SELECT tag, groesse, wert_min, wert_max, wert_mittel, wert_delta, "
                "energie_kwh, proben, vollstaendig FROM daily_history ORDER BY tag"
            ).fetchall()
        except sqlite3.Error:  # pragma: no cover - DB-Defensive
            return []
        nach_tag: dict[str, dict] = {}
        for row in rows:
            if row["tag"] not in erlaubt or not row["proben"]:
                continue
            if bekannt and row["groesse"] not in bekannt:
                continue  # entfernte Messgröße: nicht mehr ausgeben
            eintrag = nach_tag.setdefault(
                row["tag"], {"tag": row["tag"], "vollstaendig": bool(row["vollstaendig"]),
                             "groessen": {}}
            )
            eintrag["groessen"][row["groesse"]] = {
                "min": row["wert_min"],
                "max": row["wert_max"],
                "mittel": row["wert_mittel"],
                "delta": row["wert_delta"],
                "energie_kwh": row["energie_kwh"],
            }
            if not row["vollstaendig"]:
                eintrag["vollstaendig"] = False
        return [nach_tag[tag] for tag in sorted(nach_tag)]
