"""Check file settings and environment overrides."""

from pathlib import Path

import pytest

from agent_desk.settings import load_settings


def test_example_defaults():
    """The example gives the agreed defaults."""
    settings = load_settings("agent-desk.example.toml")
    assert (settings.bootstrap, settings.refund_limit, settings.max_attempts, settings.backoff_base_s) == ("localhost:9092", 50, 3, 1)
    assert settings.db_path == Path("data/shop.sqlite")
    assert settings.checkpoint_path == Path(".agent-desk/checkpoints.sqlite")


def test_environment_override(monkeypatch):
    """Environment values replace file values without exposing bad input."""
    monkeypatch.setenv("AGENT_DESK_REFUND_LIMIT", "10")
    assert load_settings("agent-desk.example.toml").refund_limit == 10
    for value in ("bad-number", "nan", "-1"):
        monkeypatch.setenv("AGENT_DESK_REFUND_LIMIT", value)
        with pytest.raises(ValueError, match="AGENT_DESK_REFUND_LIMIT") as error:
            load_settings()
        assert value not in str(error.value)


def test_other_overrides(monkeypatch, tmp_path):
    """Paths and retry settings also accept environment overrides."""
    monkeypatch.setenv("AGENT_DESK_DB_PATH", str(tmp_path / "shop.sqlite"))
    monkeypatch.setenv("AGENT_DESK_MAX_ATTEMPTS", "5")
    assert load_settings().db_path == tmp_path / "shop.sqlite"
    assert load_settings().max_attempts == 5
