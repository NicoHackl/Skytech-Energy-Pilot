"""Tests für das Holen und Speichern des Tages-Rückblicks (D-065)."""

from datetime import UTC, date, datetime

import pytest

from energy_pilot.database import init_db
from energy_pilot.history import LOCAL_TZ
from energy_pilot.history_collector import HistoryCollector, HistorySource

# 15.08.2026, 12:00 Ortszeit — mitten im laufenden Tag, damit „heute" unvollständig bleibt.
NOW = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
NOW_TS = NOW.timestamp()


class _FakeHA:
    """HA-Doppel: liefert je Entität einen festen Verlauf und zählt die Abfragen."""

    def __init__(self, verlauf=None):
        self._verlauf = verlauf or {}
        self.calls: list[tuple[str, str, str]] = []

    async def get_history(self, entity_id, start, end=None, *, minimal=True):
        self.calls.append((entity_id, start.isoformat(), end.isoformat() if end else ""))
        return list(self._verlauf.get(entity_id, []))


def _rows(tag: date, *pairs):
    return [
        {
            "state": str(value),
            "last_changed": datetime(
                tag.year, tag.month, tag.day, hour, tzinfo=LOCAL_TZ
            ).isoformat(),
        }
        for hour, value in pairs
    ]


def _collector(ha, db, *, days=3):
    collector = HistoryCollector(ha, db, days=days)
    collector.set_sources(
        [HistorySource("warmwasser", "sensor.ww", unit="°C", label="Warmwasser")]
    )
    return collector


@pytest.mark.asyncio
async def test_collects_and_stores_daily_values():
    db = init_db(":memory:")
    verlauf = {
        "sensor.ww": _rows(date(2026, 8, 13), (6, 50.0), (18, 70.0))
        + _rows(date(2026, 8, 14), (6, 60.0), (18, 80.0))
        + _rows(date(2026, 8, 15), (6, 65.0), (9, 68.0)),
    }
    collector = _collector(_FakeHA(verlauf), db)

    await collector.collect_once(now=NOW_TS)
    tage = collector.snapshot(now=NOW)

    assert [t["tag"] for t in tage] == ["2026-08-13", "2026-08-14", "2026-08-15"]
    ww = tage[1]["groessen"]["warmwasser"]
    assert ww["min"] == 60.0 and ww["max"] == 80.0 and ww["delta"] == 20.0
    assert ww["energie_kwh"] is None  # Temperatur hat keine Energie
    # Abgeschlossene Tage sind vollständig, der laufende nicht.
    assert tage[0]["vollstaendig"] is True
    assert tage[2]["vollstaendig"] is False


@pytest.mark.asyncio
async def test_complete_days_are_not_fetched_again():
    """Kernbedingung für die Last: ein abgeschlossener Tag wird genau einmal geholt."""
    db = init_db(":memory:")
    ha = _FakeHA({"sensor.ww": _rows(date(2026, 8, 14), (6, 60.0), (18, 80.0))})
    collector = _collector(ha, db)

    await collector.collect_once(now=NOW_TS)
    erste_runde = len(ha.calls)
    assert erste_runde == 3  # drei Tage im Fenster

    # Drossel umgehen, um einen zweiten echten Lauf zu erzwingen.
    collector.last_collect_ts = None
    await collector.collect_once(now=NOW_TS)

    # Nur der laufende Tag wird erneut angefragt, die beiden abgeschlossenen nicht.
    neue_calls = ha.calls[erste_runde:]
    assert len(neue_calls) == 1
    assert neue_calls[0][0] == "sensor.ww"


@pytest.mark.asyncio
async def test_running_day_is_queried_only_until_now():
    """Der laufende Tag darf nicht bis Mitternacht abgefragt werden — sonst friert er halb ein."""
    db = init_db(":memory:")
    ha = _FakeHA()
    collector = _collector(ha, db, days=1)

    await collector.collect_once(now=NOW_TS)

    _entity, _start, ende = ha.calls[0]
    assert ende == NOW.isoformat()


@pytest.mark.asyncio
async def test_throttle_prevents_a_second_run():
    db = init_db(":memory:")
    ha = _FakeHA()
    collector = _collector(ha, db)

    await collector.collect_once(now=NOW_TS)
    vorher = len(ha.calls)
    await collector.collect_once(now=NOW_TS + 60)  # weit unter dem Stundenintervall

    assert len(ha.calls) == vorher


@pytest.mark.asyncio
async def test_read_error_leaves_the_day_open_and_never_raises():
    """Eiserne Regel 13: ein fehlgeschlagener Verlaufsabruf blockiert nichts."""

    class _Boom(_FakeHA):
        async def get_history(self, entity_id, start, end=None, *, minimal=True):
            raise RuntimeError("Recorder weg")

    db = init_db(":memory:")
    collector = _collector(_Boom(), db)

    await collector.collect_once(now=NOW_TS)

    assert collector.snapshot(now=NOW) == []
    assert "Recorder weg" in (collector.last_error or "")
    # Der Tag bleibt offen und wird beim nächsten Lauf erneut versucht.
    collector.last_collect_ts = None
    await collector.collect_once(now=NOW_TS)


@pytest.mark.asyncio
async def test_disabled_without_client_db_or_sources():
    db = init_db(":memory:")
    assert HistoryCollector(None, db).enabled is False
    assert HistoryCollector(_FakeHA(), None).enabled is False
    assert HistoryCollector(_FakeHA(), db).enabled is False  # keine Quellen
    leer = HistoryCollector(_FakeHA(), db)
    await leer.collect_once(now=NOW_TS)  # No-op, kein Fehler
    assert leer.snapshot(now=NOW) == []


def test_duplicate_sources_are_collapsed():
    """Zwei Quellen mit gleichem Schlüssel würden sich in der Tabelle überschreiben (PK)."""
    collector = HistoryCollector(_FakeHA(), init_db(":memory:"))
    collector.set_sources(
        [
            HistorySource("warmwasser", "sensor.a"),
            HistorySource("warmwasser", "sensor.b"),
            HistorySource("", "sensor.c"),
            HistorySource("pv", ""),
        ]
    )
    assert [(s.groesse, s.entity_id) for s in collector.sources] == [("warmwasser", "sensor.a")]


def test_source_kind_follows_unit():
    assert HistorySource("pv", "sensor.pv", unit="W").kind == "power"
    assert HistorySource("zaehler", "sensor.z", unit="kWh").kind == "counter"
    assert HistorySource("ww", "sensor.ww", unit="°C").kind == "level"


@pytest.mark.asyncio
async def test_energy_source_reports_kwh():
    db = init_db(":memory:")
    verlauf = {"sensor.heizstab_w": _rows(date(2026, 8, 14), (10, 1000.0), (11, 0.0))}
    collector = HistoryCollector(_FakeHA(verlauf), db, days=2)
    collector.set_sources([HistorySource("heizstab_leistung", "sensor.heizstab_w", unit="W")])

    await collector.collect_once(now=NOW_TS)
    tage = {t["tag"]: t for t in collector.snapshot(now=NOW)}

    assert tage["2026-08-14"]["groessen"]["heizstab_leistung"]["energie_kwh"] == 1.0


# --- Quellenableitung ------------------------------------------------------------------------


def _devices():
    from energy_pilot.devices import CONTROLLABLE, Device, DeviceExtra

    extras = (
        DeviceExtra(read_entity_id="sensor.elwa_modbus_istleistung", unit="W", label="Istleistung"),
        DeviceExtra(read_entity_id="input_number.e3dc_max", unit="°C", label="Obergrenze"),
    )
    return [Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt", extras=extras)]


def test_sources_cover_roles_and_extras_but_not_technical_limits():
    """Regression: `max_technisch` trägt die Einheit W, ist aber ein Grenzwert.

    Als Leistung integriert ergäbe ein 3500-W-Limit rund 84 kWh am Tag — jeder Tag sähe wie
    „geheizt" aus und die Fremdwärme-Messung wäre dauerhaft leer.
    """
    from energy_pilot.entity_map import EntityMapping
    from energy_pilot.history_collector import sources_from

    mapping = {
        "hot_water_temp": EntityMapping("hot_water_temp", "sensor.ww"),
        "house_load": EntityMapping("house_load", "sensor.haus"),
    }
    quellen = {s.groesse: s for s in sources_from(mapping, _devices())}

    assert quellen["hot_water_temp"].unit == "°C"
    assert quellen["house_load"].kind == "power"  # Einheit W aus roles.py
    assert "heizstab.extra_elwa_modbus_istleistung" in quellen
    # Standardfelder des Geräts sind bewusst nicht dabei.
    assert not any(g.endswith(".max_technisch") for g in quellen)
    assert not any(g.endswith(".technische_freigabe") for g in quellen)


def test_energy_sources_only_include_energy_carrying_extras():
    from energy_pilot.history_collector import energy_sources_for, sources_from

    quellen = tuple(sources_from({}, _devices()))
    assert energy_sources_for("heizstab", quellen) == (
        "heizstab.extra_elwa_modbus_istleistung",
    )
    assert energy_sources_for("wallbox", quellen) == ()


def test_sources_skip_entries_without_entity():
    from energy_pilot.entity_map import EntityMapping
    from energy_pilot.history_collector import sources_from

    mapping = {"pv_power": EntityMapping("pv_power", None)}
    assert sources_from(mapping, []) == []


# --- Verwaiste Größen nach dem Entfernen einer Rolle ------------------------------------------


def _insert_orphan(db, tag: str, groesse: str = "grid_power"):
    """Zeile einer Größe einfügen, die es nicht mehr gibt (z. B. nach Wegfall von `grid_power`)."""
    db.execute(
        "INSERT INTO daily_history (tag, groesse, entity_id, wert_min, wert_max, wert_mittel, "
        "wert_delta, energie_kwh, proben, vollstaendig) "
        "VALUES (?, ?, 'sensor.alt', 1.0, 2.0, 1.5, 0.5, NULL, 5, 1)",
        (tag, groesse),
    )
    db.commit()


@pytest.mark.asyncio
async def test_orphan_size_does_not_mark_an_incomplete_day_as_done():
    """Regression: sonst gilt ein Tag als fertig, obwohl eine echte Quelle fehlt.

    `_complete_days` verglich die reine Zeilenzahl mit der Anzahl der Quellen. Eine Zeile einer
    entfernten Größe blähte den Zähler auf — der Tag wurde nie nachgeholt.
    """
    db = init_db(":memory:")
    ha = _FakeHA({"sensor.ww": _rows(date(2026, 8, 13), (6, 60.0), (18, 80.0))})
    collector = HistoryCollector(ha, db, days=2)
    collector.set_sources(
        [
            HistorySource("warmwasser", "sensor.ww", unit="°C"),
            HistorySource("aussen", "sensor.aussen", unit="°C"),
        ]
    )
    # Nur EINE echte Quelle ist für den 13.08. abgeschlossen, dazu eine verwaiste Zeile.
    _insert_orphan(db, "2026-08-13")
    db.execute(
        "INSERT INTO daily_history (tag, groesse, entity_id, wert_min, wert_max, wert_mittel, "
        "wert_delta, energie_kwh, proben, vollstaendig) "
        "VALUES ('2026-08-13', 'warmwasser', 'sensor.ww', 60.0, 80.0, 70.0, 20.0, NULL, 9, 1)"
    )
    db.commit()

    await collector.collect_once(now=NOW_TS)

    # Der 13.08. war offen (die Größe `aussen` fehlte) und wurde erneut angefragt.
    assert any(call[0] == "sensor.aussen" for call in ha.calls)


@pytest.mark.asyncio
async def test_orphan_size_is_not_reported_in_the_snapshot():
    """Eine entfernte Messgröße darf nicht als Geisterwert im Rückblick und im KI-Kontext landen."""
    db = init_db(":memory:")
    collector = _collector(_FakeHA(), db)
    _insert_orphan(db, "2026-08-14")

    tage = collector.snapshot(now=NOW)

    assert all("grid_power" not in tag["groessen"] for tag in tage)


def test_migration_16_removes_orphan_rows_of_the_dropped_role():
    """Migration v16 räumt die Altlast der entfernten Rolle auf.

    Dafür wird eine Datenbank auf dem Stand **vor** v16 aufgebaut, die Altlast eingefügt und dann
    migriert — sonst prüft der Test die Migration nicht, sondern nur das eigene DELETE.
    """
    from energy_pilot.database import MIGRATIONS, connect, current_version, migrate

    db = connect(":memory:")
    current_version(db)  # legt `schema_migrations` an
    for version, sql in MIGRATIONS:
        if version >= 16:
            break
        db.executescript(sql)
        db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
    db.commit()
    assert current_version(db) == 15

    _insert_orphan(db, "2026-08-14")
    db.execute("INSERT INTO entity_map (role, ha_entity_id) VALUES ('grid_power', 'sensor.alt')")
    # Eine noch gültige Größe daneben, damit der Test das Löschen nicht mit „Tabelle leeren"
    # verwechselt.
    _insert_orphan(db, "2026-08-14", groesse="warmwasser")
    db.commit()

    assert migrate(db) == [16]

    assert db.execute(
        "SELECT COUNT(*) AS n FROM daily_history WHERE groesse = 'grid_power'"
    ).fetchone()["n"] == 0
    assert db.execute(
        "SELECT COUNT(*) AS n FROM entity_map WHERE role = 'grid_power'"
    ).fetchone()["n"] == 0
    assert db.execute(
        "SELECT COUNT(*) AS n FROM daily_history WHERE groesse = 'warmwasser'"
    ).fetchone()["n"] == 1
