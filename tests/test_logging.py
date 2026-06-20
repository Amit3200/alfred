"""Tests for file logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import backend.logging_config as logging_config_module
from backend.logging_config import setup_logging
from backend.paths import log_path


@pytest.fixture(autouse=True)
def reset_logging_state():
    logging_config_module._configured = False
    root = logging.getLogger()
    root.handlers.clear()
    yield
    root.handlers.clear()
    logging_config_module._configured = False


def test_setup_logging_creates_file(tmp_path: Path):
    path = setup_logging(tmp_path)
    assert path == log_path(tmp_path)
    logging.getLogger("test.alfred").info("hello from test")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert path.exists()
    assert "hello from test" in path.read_text()
