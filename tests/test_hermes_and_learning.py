"""Tests for Hermes Runner Loop and Self-Improving Learning Loop."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.ai.base import LLMResponse, Message, ToolCall
from backend.models.config import AlfredConfig, AIConfig, AIProviderConfig
from backend.models.task import Task
from backend.orchestrator.hermes_runner import run_hermes_loop
from backend.orchestrator.learning import analyze_and_generate_playbook
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def test_run_hermes_loop_tool_call():
    provider = MagicMock()
    # Mock first chat call returning tool calls, second returning final answer
    provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc1", name="grep_repo", arguments={"query": "hello"})],
            model="m1",
        ),
        LLMResponse(content="I found the match.", tool_calls=[], model="m1"),
    ]

    registry = ToolRegistry()
    from backend.ai.base import ToolSchema
    schema = ToolSchema(
        name="grep_repo",
        description="grep files",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    mock_handler = MagicMock()
    mock_handler.return_value = ToolResult(kind="text", data={"text": "found line 1"})
    registry.register(schema, mock_handler)

    messages = [Message(role="system", content="System base")]
    result = run_hermes_loop(
        provider,
        messages,
        registry,
        allowed_tools=["grep_repo"],
        model="m1",
    )

    assert result == "I found the match."
    assert provider.chat.call_count == 2
    mock_handler.assert_called_once_with({"query": "hello"})


def test_analyze_and_generate_playbook(tmp_path, monkeypatch):
    config = AlfredConfig()
    config.orchestrator.self_improvement = True
    config.ai.default_provider = "openai"
    config.ai.providers = {
        "openai": AIProviderConfig(enabled=True, model="gpt-4o"),
    }

    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(
        content=(
            "---\n"
            "name: test_playbook\n"
            "description: Generated test playbook\n"
            "mode: investigation\n"
            "trigger_keywords: [test, debug]\n"
            "---\n"
            "# Objective\n"
            "Run a test debug.\n"
        ),
        model="gpt-4o",
    )

    monkeypatch.setattr(
        "backend.orchestrator.learning.LLMRouter.from_config",
        lambda cfg, data_dir: MagicMock(get=lambda: mock_provider),
    )

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="@alfred why is deployment failing?",
        cleaned_intent="why is deployment failing?",
    )

    playbook_file = analyze_and_generate_playbook(
        task,
        "It failed due to timeout.",
        config,
        data_dir=str(tmp_path),
    )

    assert playbook_file is not None
    assert Path(playbook_file).exists()
    assert "test_playbook" in Path(playbook_file).name
    assert "Generated test playbook" in Path(playbook_file).read_text()


def test_analyze_and_generate_playbook_disabled(tmp_path):
    config = AlfredConfig()
    config.orchestrator.self_improvement = False

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="...",
        cleaned_intent="...",
    )

    playbook_file = analyze_and_generate_playbook(
        task,
        "Response",
        config,
        data_dir=str(tmp_path),
    )
    assert playbook_file is None
