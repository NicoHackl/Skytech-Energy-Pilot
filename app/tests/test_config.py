"""Tests für das Laden der Addon-Konfiguration."""

import json

from energy_pilot.config import AddonConfig


def test_defaults_when_no_options_file(tmp_path):
    cfg = AddonConfig.load(options_path=str(tmp_path / "missing.json"), env={})
    assert cfg.model == "gemini-3.5-flash"
    assert cfg.provider == "gemini"
    assert cfg.min_confidence_percent == 70


def test_file_values_override_defaults(tmp_path):
    path = tmp_path / "options.json"
    path.write_text(json.dumps({"model": "gemini-x", "planning_interval_min": 30}))

    cfg = AddonConfig.load(options_path=str(path), env={})
    assert cfg.model == "gemini-x"
    assert cfg.planning_interval_min == 30
    # Nicht überschriebene Werte behalten ihren Default
    assert cfg.provider == "gemini"


def test_env_overrides_log_level(tmp_path):
    cfg = AddonConfig.load(options_path=str(tmp_path / "missing.json"), env={"LOG_LEVEL": "debug"})
    assert cfg.log_level == "debug"


def test_unknown_attribute_raises():
    cfg = AddonConfig.load(options_path="missing.json", env={})
    try:
        _ = cfg.does_not_exist
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("AttributeError erwartet")
