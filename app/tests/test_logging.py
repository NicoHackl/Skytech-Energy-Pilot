"""Tests für strukturiertes Logging, Secret-Redaction und Export."""

import io
import json

from energy_pilot.logging_setup import log, setup_logging


def test_secrets_are_redacted_in_context():
    logger, ring = setup_logging("DEBUG", capacity=10, stream=io.StringIO())
    log(logger, "info", "starte", context={"api_key": "geheim123", "host": "homeassistant"})

    records = ring.records()
    assert len(records) == 1
    assert records[0]["context"]["api_key"] == "***redacted***"
    assert records[0]["context"]["host"] == "homeassistant"
    assert records[0]["message"] == "starte"


def test_ring_buffer_respects_capacity_and_level_filter():
    logger, ring = setup_logging("DEBUG", capacity=2, stream=io.StringIO())
    log(logger, "info", "eins")
    log(logger, "warning", "zwei")
    log(logger, "error", "drei")

    # Kapazität 2 -> ältester Eintrag fällt heraus
    assert [r["message"] for r in ring.records()] == ["zwei", "drei"]
    assert [r["message"] for r in ring.records(level="error")] == ["drei"]


def test_export_jsonl_is_machine_readable():
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    log(logger, "error", "boom", context={"detail": "x"})

    export = ring.export_jsonl()
    parsed = json.loads(export.splitlines()[0])
    assert parsed["level"] == "ERROR"
    assert parsed["message"] == "boom"


def test_extra_fields_are_included():
    logger, ring = setup_logging("DEBUG", stream=io.StringIO())
    log(logger, "info", "plan", plan_id="2026-06-16T14:00", provider="gemini")

    record = ring.records()[0]
    assert record["plan_id"] == "2026-06-16T14:00"
    assert record["provider"] == "gemini"
