"""Tests for Ollama local service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.ollama import service as ollama


def test_get_status_not_installed() -> None:
    with patch("backend.ollama.service.shutil.which", return_value=None):
        result = ollama.get_status()
    assert result["installed"] is False
    assert result["running"] is False
    assert result["local_only"] is True
    assert "not installed" in result["message"].lower()


def test_get_status_running_with_model() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}]}

    with (
        patch("backend.ollama.service.shutil.which", return_value="/usr/local/bin/ollama"),
        patch("backend.ollama.service.requests.get", return_value=mock_resp),
    ):
        result = ollama.get_status(model="llama3")

    assert result["installed"] is True
    assert result["running"] is True
    assert result["model_ready"] is True


def test_install_already_present() -> None:
    with patch("backend.ollama.service.shutil.which", return_value="/usr/bin/ollama"):
        result = ollama.install_ollama()
    assert result["ok"] is True
    assert result.get("already_installed") is True


def test_api_root_strips_v1_suffix() -> None:
    assert ollama._api_root("http://localhost:11434/v1") == "http://localhost:11434"
