"""Tests für die Planning-Engine (Orchestrator) mit Fake-Provider."""

import io
from datetime import UTC, datetime

from energy_pilot.ai_provider import AIProvider, ProviderError, ProviderResponse
from energy_pilot.config import AddonConfig
from energy_pilot.database import init_db
from energy_pilot.devices import CONTROLLABLE, Device
from energy_pilot.logging_setup import setup_logging
from energy_pilot.planner import Planner

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


class _FakeProvider(AIProvider):
    name = "fake"

    def __init__(self, data=None, *, model="fake-1", exc=None):
        self.model = model
        self._data = data or {}
        self._exc = exc
        self.closed = False

    async def generate(self, prompt, response_schema):
        if self._exc is not None:
            raise self._exc
        return ProviderResponse(data=self._data, tokens_in=11, tokens_out=22)

    async def close(self):
        self.closed = True


class _SequenceProvider(AIProvider):
    """Liefert je Aufruf die nächste vorbereitete Antwort (für den Nachforder-Test).

    `exc_on` (0-basierter Aufrufindex) lässt genau diesen Aufruf scheitern – so lässt sich
    prüfen, dass eine fehlgeschlagene Nachforderung die deterministische Füllung nicht blockiert.
    """

    name = "seq"

    def __init__(self, responses, *, model="seq-1", exc_on=None):
        self.model = model
        self._responses = list(responses)
        self._exc_on = exc_on
        self.calls = 0

    async def generate(self, prompt, response_schema):
        idx = self.calls
        self.calls += 1
        if self._exc_on is not None and idx == self._exc_on:
            raise ProviderError("repair boom")
        return ProviderResponse(
            data=self._responses[min(idx, len(self._responses) - 1)], tokens_in=3, tokens_out=4
        )

    async def close(self):
        return None


class _Devices:
    def __init__(self):
        self.devices = [
            Device("batterie", "Batterie", "batterie", CONTROLLABLE, "watt"),
            Device("heizstab", "Heizstab", "heizstab", CONTROLLABLE, "watt"),
        ]
        self.last_values = {
            "batterie": {
                "technische_freigabe": {"value": True},
                "min_technisch": {"value": 0.0},
                "max_technisch": {"value": 5000.0},
            },
            "heizstab": {
                "technische_freigabe": {"value": True},
                "min_technisch": {"value": 500.0},
                "max_technisch": {"value": 3000.0},
                "ep_max_temperatur": {"value": 60.0},
            },
        }


class _FakeHA:
    """HA-Client-Doppel: zeichnet die set_state-Aufrufe des Publishers auf."""

    def __init__(self):
        self.calls = []

    async def set_state(self, entity_id, state, attributes=None):
        self.calls.append((entity_id, state, attributes))
        return {"entity_id": entity_id, "state": state}


# Gültiger Modell-Output (heizstab + batterie), wird in mehreren Tests genutzt.
_VALID_DATA = {
    "devices": [
        {
            "name": "heizstab",
            "prio_vorschlag": 10,
            "freigabe_vorschlag": True,
            "geschutzte_mindestleistung_w_vorschlag": 800.0,
            "max_temperatur_vorschlag": 55.0,
        },
        {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
    ],
    "confidence": 80,
    "reasoning": "Test",
    "warnings": [],
}


class _Weather:
    """Wetter-Collector-Doppel mit einem Snapshot wie WeatherCollector.snapshot()."""

    def snapshot(self):
        return {
            "enabled": True,
            "units": "metric",
            "forecast": {
                "city": "Wien",
                "slots": [
                    {"time": "2026-06-19 12:00:00", "temp": 24.0, "clouds": 20.0, "pop": 0.1,
                     "feels_like": 23.0, "wind_speed": 3.0, "humidity": 50.0,
                     "rain_3h": None, "snow_3h": None, "condition": "klar"},
                ],
            },
        }


def _planner(tmp_path, provider, *, ha_client=None, options=None, weather_collector=None):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    if options:
        config.values.update(options)
    logger, _ = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    planner = Planner(
        provider, config, db,
        ha_client=ha_client, device_collector=_Devices(),
        weather_collector=weather_collector, logger=logger,
    )
    return planner, db


async def test_run_produces_valid_plan(tmp_path):
    data = {
        "devices": [
            {
                "name": "heizstab",
                "prio_vorschlag": 10,
                "freigabe_vorschlag": True,
                "geschutzte_mindestleistung_w_vorschlag": 800.0,
                "max_temperatur_vorschlag": 55.0,
            },
            {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
        ],
        "confidence": 80,
        "reasoning": "Test",
        "warnings": [],
    }
    planner, db = _planner(tmp_path, _FakeProvider(data))

    result = await planner.run(now=NOW)

    assert result.ok
    assert result.validation["errors"] == []
    assert result.ai_call["tokens_in"] == 11
    assert db.execute("SELECT COUNT(*) AS n FROM ai_calls WHERE ok=1").fetchone()["n"] == 1
    assert db.execute("SELECT COUNT(*) AS n FROM plans WHERE ok=1").fetchone()["n"] == 1
    assert (
        db.execute("SELECT COUNT(*) AS n FROM audit WHERE action='plan_created'").fetchone()["n"]
        == 1
    )
    latest = planner.latest_plan()
    assert latest["ok"]
    assert latest["plan"]["devices"]


_INCOMPLETE_DATA = {
    "devices": [
        {"name": "heizstab", "prio_vorschlag": 10},  # freigabe + geschützte Mindestleistung fehlen
        {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
    ],
    "confidence": 70, "reasoning": "x", "warnings": [],
}
_COMPLETE_DATA = {
    "devices": [
        {"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True,
         "geschutzte_mindestleistung_w_vorschlag": 800.0},
        {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
    ],
    "confidence": 70, "reasoning": "x", "warnings": [],
}


async def test_run_repairs_missing_fields(tmp_path):
    # D-050: unvollständige Erstantwort -> genau eine gezielte Nachforderung; der vollständige
    # Zweitplan wird übernommen (echter KI-Wert 800, nicht der Fallback 500 = min_technisch).
    provider = _SequenceProvider([_INCOMPLETE_DATA, _COMPLETE_DATA])
    planner, db = _planner(tmp_path, provider)

    result = await planner.run(now=NOW)

    assert result.ok
    assert provider.calls == 2
    heizstab = next(d for d in result.plan["devices"] if d["name"] == "heizstab")
    assert heizstab["freigabe_vorschlag"] is True
    assert heizstab["geschutzte_mindestleistung_w_vorschlag"] == 800.0
    assert db.execute("SELECT COUNT(*) AS n FROM ai_calls WHERE ok=1").fetchone()["n"] == 2
    assert result.ai_call["tokens_in"] == 6  # Tokens beider Aufrufe summiert


async def test_run_repair_failure_falls_back_to_deterministic_fill(tmp_path):
    # Scheitert die Nachforderung, bleibt der erste Plan gültig und der Validator füllt die
    # Lücken deterministisch aus dem Ist-Zustand (Iron Rule 8 – EP blockiert nie).
    provider = _SequenceProvider([_INCOMPLETE_DATA], exc_on=1)
    planner, _ = _planner(tmp_path, provider)

    result = await planner.run(now=NOW)

    assert result.ok
    assert provider.calls == 2
    heizstab = next(d for d in result.plan["devices"] if d["name"] == "heizstab")
    assert heizstab["freigabe_vorschlag"] is True  # aus aktueller technischer Freigabe
    assert heizstab["geschutzte_mindestleistung_w_vorschlag"] == 500.0  # Fallback = min_technisch


async def test_run_no_repair_when_first_response_complete(tmp_path):
    # Vollständige Erstantwort -> keine Nachforderung (nur ein KI-Aufruf).
    provider = _SequenceProvider([_COMPLETE_DATA])
    planner, db = _planner(tmp_path, provider)

    result = await planner.run(now=NOW)

    assert result.ok
    assert provider.calls == 1
    assert db.execute("SELECT COUNT(*) AS n FROM ai_calls WHERE ok=1").fetchone()["n"] == 1


async def test_run_passes_previous_plan_as_anchor(tmp_path):
    # A1: erster Lauf ohne Anker; zweiter Lauf bekommt den gespeicherten Vorplan verdichtet
    # als `previous_plan` in den KI-Kontext (Stabilität über Aufrufe).
    planner, _ = _planner(tmp_path, _FakeProvider(_VALID_DATA))

    first = await planner.run(now=NOW)
    assert "previous_plan" not in first.context

    second = await planner.run(now=NOW)
    prev = second.context["previous_plan"]
    heizstab = next(d for d in prev["devices"] if d["name"] == "heizstab")
    assert heizstab["prio_vorschlag"] == 10
    assert heizstab["freigabe_vorschlag"] is True


# Vollständige, sonst gültige Pläne, die sich nur in der Heizstab-Freigabe unterscheiden.
_STABLE_TRUE = {
    "devices": [
        {"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": True,
         "geschutzte_mindestleistung_w_vorschlag": 800.0},
        {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
    ],
    "confidence": 80, "reasoning": "x", "warnings": [],
}
_STABLE_FALSE = {
    "devices": [
        {"name": "heizstab", "prio_vorschlag": 10, "freigabe_vorschlag": False,
         "geschutzte_mindestleistung_w_vorschlag": 800.0},
        {"name": "batterie", "geschutzte_mindestleistung_w_vorschlag": 3000.0},
    ],
    "confidence": 80, "reasoning": "x", "warnings": [],
}


async def test_run_hysteresis_holds_freigabe_flip(tmp_path):
    # A2-Kernbeweis: kippt das Modell die Freigabe, hält die Hysterese sie, bis N (=2) konsistente
    # Läufe den Wechsel bestätigen. Zwei quasi-identische Läufe → kein sofortiger Freigabe-Wechsel.
    provider = _SequenceProvider([_STABLE_TRUE, _STABLE_FALSE])
    planner, _ = _planner(tmp_path, provider)

    def _frei(result):
        return next(d for d in result.plan["devices"] if d["name"] == "heizstab")[
            "freigabe_vorschlag"
        ]

    r1 = await planner.run(now=NOW)
    assert _frei(r1) is True

    r2 = await planner.run(now=NOW)  # Modell will false -> gehalten (bleibt true)
    assert _frei(r2) is True
    assert any("gehalten" in c for c in r2.validation["clamped"])

    r3 = await planner.run(now=NOW)  # zweiter konsistenter false -> Wechsel bestätigt
    assert _frei(r3) is False
    assert any("Hysterese bestätigt" in c for c in r3.validation["clamped"])


async def test_run_rejects_low_confidence_and_does_not_publish(tmp_path):
    # A4: Konfidenz unter der Schwelle (Default 70 %) -> Plan abgelehnt, nichts nach HA geschrieben.
    low_conf = {**_STABLE_TRUE, "confidence": 50}
    ha = _FakeHA()
    planner, db = _planner(tmp_path, _FakeProvider(low_conf), ha_client=ha)

    result = await planner.run(now=NOW)

    assert not result.ok
    assert any("Mindestkonfidenz" in e for e in result.validation["errors"])
    assert result.published is None
    assert ha.calls == []
    assert (
        db.execute("SELECT COUNT(*) AS n FROM audit WHERE action='plan_rejected'").fetchone()["n"]
        == 1
    )


async def test_run_includes_weather_in_context(tmp_path):
    planner, _ = _planner(
        tmp_path, _FakeProvider(_VALID_DATA),
        weather_collector=_Weather(),
        options={"weather": {"llm_detail": "full"}},
    )

    result = await planner.run(now=NOW)

    assert result.ok
    weather = result.context["weather"]
    assert weather["city"] == "Wien"
    assert weather["detail"] == "full"
    assert weather["slots"][0]["temp"] == 24.0


async def test_run_rejects_contract_violation(tmp_path):
    # Batterie darf keine Priorität vorschlagen (D-037) -> Validierung lehnt ab.
    data = {
        "devices": [
            {"name": "batterie", "prio_vorschlag": 1,
             "geschutzte_mindestleistung_w_vorschlag": 1000.0}
        ],
        "confidence": 50,
        "reasoning": "x",
    }
    planner, db = _planner(tmp_path, _FakeProvider(data))

    result = await planner.run(now=NOW)

    assert not result.ok
    assert any("Schreibvertrag" in e for e in result.validation["errors"])
    assert db.execute("SELECT ok FROM plans ORDER BY id DESC LIMIT 1").fetchone()["ok"] == 0
    assert (
        db.execute("SELECT COUNT(*) AS n FROM audit WHERE action='plan_rejected'").fetchone()["n"]
        == 1
    )


async def test_run_handles_provider_error_gracefully(tmp_path):
    planner, db = _planner(tmp_path, _FakeProvider(exc=ProviderError("boom")))

    result = await planner.run(now=NOW)

    assert not result.ok
    assert result.error == "provider_error"
    assert db.execute("SELECT COUNT(*) AS n FROM ai_calls WHERE ok=0").fetchone()["n"] == 1
    # Ohne valide Ausgabe wird kein Plan gespeichert.
    assert db.execute("SELECT COUNT(*) AS n FROM plans").fetchone()["n"] == 0


async def test_run_reports_nonempty_error_on_timeout(tmp_path):
    # Regression: TimeoutError hat einen leeren str(); der Planner muss trotzdem eine
    # lesbare Meldung loggen/liefern (nie "error": "" in Log, UI oder ai_calls).
    planner, db = _planner(tmp_path, _FakeProvider(exc=TimeoutError()))

    result = await planner.run(now=NOW)

    assert not result.ok
    assert result.error == "provider_error"
    assert result.ai_call["error"].strip()
    assert all(e.strip() for e in result.validation["errors"])
    row = db.execute("SELECT error FROM ai_calls ORDER BY id DESC LIMIT 1").fetchone()
    assert row["error"] and row["error"].strip()


async def test_run_without_provider_reports_not_configured(tmp_path):
    planner, db = _planner(tmp_path, None)

    result = await planner.run(now=NOW)

    assert not result.ok
    assert result.error == "provider_not_configured"
    assert db.execute("SELECT COUNT(*) AS n FROM ai_calls").fetchone()["n"] == 0
    assert db.execute("SELECT COUNT(*) AS n FROM plans").fetchone()["n"] == 0


async def test_run_publishes_valid_plan_to_ha(tmp_path):
    ha = _FakeHA()
    planner, _ = _planner(tmp_path, _FakeProvider(_VALID_DATA), ha_client=ha)

    result = await planner.run(now=NOW)

    assert result.ok
    assert result.published is not None and result.published["ok"]
    written = set(result.published["written"])
    assert "sensor.ep_heizstab_prio_vorschlag" in written
    assert "sensor.ep_batterie_geschutzte_mindestleistung_w_vorschlag" in written
    # Es wurde tatsächlich nach HA geschrieben (nicht nur im Ergebnis gemeldet).
    assert any(call[0] == "sensor.ep_heizstab_freigabe_vorschlag" for call in ha.calls)


async def test_run_does_not_publish_rejected_plan(tmp_path):
    # Batterie mit Priorität verletzt den Schreibvertrag (D-037) -> Plan abgelehnt.
    data = {
        "devices": [
            {"name": "batterie", "prio_vorschlag": 1,
             "geschutzte_mindestleistung_w_vorschlag": 1000.0}
        ],
        "confidence": 50,
        "reasoning": "x",
    }
    ha = _FakeHA()
    planner, _ = _planner(tmp_path, _FakeProvider(data), ha_client=ha)

    result = await planner.run(now=NOW)

    assert not result.ok
    assert result.published is None
    assert ha.calls == []


async def test_run_respects_publish_disabled(tmp_path):
    ha = _FakeHA()
    planner, _ = _planner(
        tmp_path, _FakeProvider(_VALID_DATA), ha_client=ha,
        options={"publish_suggestions": False},
    )

    result = await planner.run(now=NOW)

    assert result.ok
    assert result.published is None
    assert ha.calls == []


async def test_publish_latest_rewrites_last_valid_plan(tmp_path):
    ha = _FakeHA()
    planner, _ = _planner(tmp_path, _FakeProvider(_VALID_DATA), ha_client=ha)
    await planner.run(now=NOW)
    ha.calls.clear()

    result = await planner.publish_latest()

    assert result["ok"]
    assert any(call[0].startswith("sensor.ep_") for call in ha.calls)


async def test_publish_latest_without_valid_plan_reports_reason(tmp_path):
    planner, _ = _planner(tmp_path, None, ha_client=_FakeHA())

    result = await planner.publish_latest()

    assert not result["ok"]
    assert "kein gültiger Plan" in result["reason"]
