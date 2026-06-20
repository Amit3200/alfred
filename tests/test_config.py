"""Tests for Alfred configuration layer."""

from pathlib import Path

import pytest

from backend.config_manager import ConfigManager
from backend.models.config import AlfredConfig, AlfredSecrets, default_config


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "alfred-test"


def test_init_creates_config_and_secrets(data_dir: Path) -> None:
    manager = ConfigManager(data_dir)
    assert not manager.is_initialized()
    config = manager.init()
    assert config.initialized
    assert manager.is_initialized()
    assert (data_dir / "config.yaml").exists()
    assert (data_dir / "secrets.enc").exists()
    assert (data_dir / ".key").exists()


def test_secrets_not_in_config_yaml(data_dir: Path) -> None:
    manager = ConfigManager(data_dir)
    manager.init()
    config = manager.load_config()
    config.slack.enabled = True
    secrets = manager.load_secrets()
    secrets.slack_bot_token = "xoxb-test-token"
    manager.save_merged(config, secrets)

    raw = (data_dir / "config.yaml").read_text()
    assert "xoxb-test-token" not in raw

    loaded_config, loaded_secrets = manager.load_merged()
    assert loaded_secrets.slack_bot_token == "xoxb-test-token"
    assert loaded_config.slack.bot_token == "xoxb-test-token"


def test_public_config_strips_secrets(data_dir: Path) -> None:
    manager = ConfigManager(data_dir)
    manager.init()
    config, secrets = manager.load_merged()
    secrets.ai_api_keys["anthropic"] = "sk-secret"
    manager.save_merged(config, secrets)

    public = manager.public_config()
    assert public["slack"]["bot_token"] == ""
    assert public["_secrets_configured"]["ai_api_keys"].get("anthropic") is True


def test_default_ai_providers() -> None:
    config = default_config()
    assert "ollama" in config.ai.providers
    assert "anthropic" in config.ai.providers
    assert config.ai.default_provider == "ollama"


def test_secrets_update_replaces_existing_token(data_dir: Path) -> None:
    """Simulates PUT /api/config/secrets — new values must not be overwritten by stale config."""
    manager = ConfigManager(data_dir)
    manager.init()
    config, secrets = manager.load_merged()
    secrets.slack_bot_token = "test"
    manager._apply_secrets_to_config(config, secrets)
    manager.save_merged(config, secrets)

    _, secrets = manager.load_merged()
    secrets.slack_bot_token = "xoxb-123456789012345678901234"
    manager._apply_secrets_to_config(config, secrets)
    manager.save_merged(config, secrets)

    _, loaded = manager.load_merged()
    assert loaded.slack_bot_token == "xoxb-123456789012345678901234"
