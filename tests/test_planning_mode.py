"""Tests for Checklist-Based Task Planning Mode."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.ai.base import LLMResponse
from backend.models.config import AlfredConfig, AIProviderConfig
from backend.models.task import Task
from backend.orchestrator.planning import generate_initial_plan, update_plan_progress, plans_dir


def test_generate_initial_plan(tmp_path, monkeypatch):
    config = AlfredConfig()
    config.ai.default_provider = "openai"
    config.ai.providers = {
        "openai": AIProviderConfig(enabled=True, model="gpt-4o"),
    }

    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=(
            "# Task Plan\n"
            "- [ ] Step 1: Run diagnostics\n"
            "- [ ] Step 2: Extract summaries\n"
        ),
        model="gpt-4o",
    )

    monkeypatch.setattr(
        "backend.orchestrator.planning.LLMRouter.from_config",
        lambda cfg, data_dir: MagicMock(get=lambda: mock_provider),
    )

    task = Task(
        id="t_plan_1",
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="diagnose prod server",
        cleaned_intent="diagnose prod server",
    )

    plan = generate_initial_plan(
        task,
        ["grep_repo", "list_prs"],
        config,
        data_dir=str(tmp_path),
    )

    assert plan is not None
    assert "Run diagnostics" in plan
    
    plan_file = plans_dir(tmp_path) / "plan_t_plan_1.md"
    assert plan_file.is_file()
    assert "- [ ] Step 1:" in plan_file.read_text()


def test_update_plan_progress(tmp_path, monkeypatch):
    config = AlfredConfig()
    config.ai.default_provider = "openai"
    config.ai.providers = {
        "openai": AIProviderConfig(enabled=True, model="gpt-4o"),
    }

    # Seed the plan file
    plan_dir = plans_dir(tmp_path)
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / "plan_t_plan_1.md"
    plan_file.write_text(
        "# Task Plan\n"
        "- [ ] Step 1: Run diagnostics\n"
        "- [ ] Step 2: Extract summaries\n",
        encoding="utf-8",
    )

    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=(
            "# Task Plan\n"
            "- [x] Step 1: Run diagnostics\n"
            "- [ ] Step 2: Extract summaries\n"
        ),
        model="gpt-4o",
    )

    monkeypatch.setattr(
        "backend.orchestrator.planning.LLMRouter.from_config",
        lambda cfg, data_dir: MagicMock(get=lambda: mock_provider),
    )

    updated = update_plan_progress(
        "t_plan_1",
        "Ran grep_repo",
        "Found error traceback",
        config,
        data_dir=str(tmp_path),
    )

    assert updated is not None
    assert "- [x] Step 1:" in updated
    assert "- [ ] Step 2:" in updated
    assert "- [x] Step 1:" in plan_file.read_text()
