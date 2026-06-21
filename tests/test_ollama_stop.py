"""Tests for Ollama stop helper."""

from unittest.mock import patch

from backend.ollama import service as ollama_service


def test_stop_ollama_when_not_installed():
    with patch.object(ollama_service.shutil, "which", return_value=None):
        result = ollama_service.stop_ollama()
    assert result["ok"] is True
    assert result["stopped"] is False


def test_stop_ollama_when_not_running():
    with patch.object(ollama_service.shutil, "which", return_value="/usr/bin/ollama"):
        with patch.object(ollama_service, "get_status", return_value={"running": False}):
            result = ollama_service.stop_ollama()
    assert result["ok"] is True
    assert result["stopped"] is False
