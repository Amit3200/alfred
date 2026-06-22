"""Tests for Google Workspace prompt context."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.ingress.google_context import (
    format_google_context_for_prompt,
    looks_like_google_access_question,
)
from backend.models.config import AlfredConfig, GoogleConfig
from backend.models.task import Task


def _task(intent: str, *, raw: str = "") -> Task:
    return Task(
        source="slack",
        channel_id="C1",
        user_id="U1",
        raw_text=raw or intent,
        cleaned_intent=intent,
    )


def test_google_context_connected(monkeypatch):
    config = AlfredConfig(google=GoogleConfig(enabled=True))
    monkeypatch.setattr(
        "backend.ingress.google_context.check_google",
        lambda _config: {"ok": True, "message": "OAuth connected for Sheets and Docs"},
    )

    prompt = format_google_context_for_prompt(config, _task("read my sheet"))

    assert "connected" in prompt.lower()
    assert "never" in prompt.lower()
    assert "google_read_sheet" in prompt


def test_google_context_not_connected(monkeypatch):
    config = AlfredConfig(google=GoogleConfig(enabled=True))
    monkeypatch.setattr(
        "backend.ingress.google_context.check_google",
        lambda _config: {"ok": False, "message": "OAuth client saved — click Connect Google"},
    )

    prompt = format_google_context_for_prompt(
        config,
        _task("do you have google access?"),
    )

    assert "not ready" in prompt.lower()
    assert "Connect Google" in prompt
    assert looks_like_google_access_question("do you have google access?") is True


def test_google_context_extracts_sheet_url(monkeypatch):
    config = AlfredConfig(google=GoogleConfig(enabled=True))
    monkeypatch.setattr(
        "backend.ingress.google_context.check_google",
        lambda _config: {"ok": True, "message": "OAuth connected"},
    )
    url = "https://docs.google.com/spreadsheets/d/abc123XYZ/edit#gid=0"
    session = MagicMock()
    session.turns = []

    prompt = format_google_context_for_prompt(
        config,
        _task("summarize sheet2", raw=f"check {url}"),
        session,
    )

    assert "`abc123XYZ`" in prompt
