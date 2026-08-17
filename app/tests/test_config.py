"""Tests für das Laden der Addon-Konfiguration + Provider-Auflösung (D-056)."""

import json

from energy_pilot.config import AddonConfig, resolve_active_provider


def test_defaults_when_no_options_file(tmp_path):
    cfg = AddonConfig.load(options_path=str(tmp_path / "missing.json"), env={})
    assert cfg.provider == "gemini"
    assert cfg.min_confidence_percent == 70
    # Modell/Key liegen jetzt im Provider-Untermenü (D-056).
    active = resolve_active_provider(cfg.values)
    assert active.name == "gemini"
    assert active.model == "gemini-2.5-flash"


def test_file_values_override_defaults(tmp_path):
    path = tmp_path / "options.json"
    path.write_text(json.dumps({"planning_interval_min": 30}))

    cfg = AddonConfig.load(options_path=str(path), env={})
    assert cfg.planning_interval_min == 30
    # Nicht überschriebene Werte behalten ihren Default
    assert cfg.provider == "gemini"


def test_resolve_active_provider_switches_provider(tmp_path):
    path = tmp_path / "options.json"
    path.write_text(json.dumps({
        "provider": "claude",
        "providers": {"claude": {"api_key": "sk-ant", "model": "claude-x"}},
    }))
    cfg = AddonConfig.load(options_path=str(path), env={})
    active = resolve_active_provider(cfg.values)
    assert active.name == "claude"
    assert active.api_key == "sk-ant"
    assert active.model == "claude-x"


def test_resolve_active_provider_openai_defaults(tmp_path):
    active = resolve_active_provider({"provider": "openai"})
    assert active.name == "openai"
    assert active.model == "gpt-5"
    assert active.rate_limit_per_min == 60


def test_resolve_active_provider_invalid_falls_back_to_gemini():
    active = resolve_active_provider({"provider": "bogus"})
    assert active.name == "gemini"


def test_resolve_active_provider_legacy_top_level_fallback():
    # Alt-Installation: Gemini-Felder flach auf oberster Ebene (D-056-Migration).
    values = {
        "provider": "gemini",
        "api_key": "LEGACY-KEY",
        "model": "gemini-legacy",
        "ai_request_timeout_s": 45,
        "ai_rate_limit_per_min": 7,
    }
    active = resolve_active_provider(values)
    assert active.api_key == "LEGACY-KEY"
    assert active.model == "gemini-legacy"
    assert active.timeout_s == 45.0
    assert active.rate_limit_per_min == 7


def test_resolve_active_provider_shared_temperature_seed():
    active = resolve_active_provider({"provider": "gemini", "ai_temperature": 0.0, "ai_seed": 42})
    assert active.temperature == 0.0
    assert active.seed == 42


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


def test_thinking_level_is_normalized_and_validated(tmp_path):
    """Nur die dokumentierten Denkstufen werden übernommen; alles andere fällt auf None."""
    from energy_pilot.config import resolve_active_provider

    base = {"provider": "gemini", "providers": {"gemini": {"api_key": "k"}}}
    assert resolve_active_provider({**base, "ai_thinking_level": " MINIMAL "}).thinking_level == (
        "minimal"
    )
    assert resolve_active_provider({**base, "ai_thinking_level": "quatsch"}).thinking_level is None
    assert resolve_active_provider({**base, "ai_thinking_level": ""}).thinking_level is None
