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


def _planner(tmp_path, provider):
    config = AddonConfig.load(options_path=str(tmp_path / "options.json"), env={})
    logger, _ = setup_logging("DEBUG", stream=io.StringIO())
    db = init_db(str(tmp_path / "ep.db"))
    return Planner(provider, config, db, device_collector=_Devices(), logger=logger), db


async def test_run_produces_valid_plan(tmp_path):
    data = {
        "devices": [
            {
                "name": "heizstab",
                "prio_vorschlag": 2,
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
