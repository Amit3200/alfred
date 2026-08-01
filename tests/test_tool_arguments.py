"""Tests for resilient tool argument parsing."""

from __future__ import annotations

from backend.ai.openai_compat import OpenAICompatProvider
from backend.ai.tool_arguments import parse_tool_call_arguments
from backend.models.config import AIProviderConfig


def test_parse_tool_call_arguments_valid_json():
    assert parse_tool_call_arguments('{"project":"TS","summary":"Test"}') == {
        "project": "TS",
        "summary": "Test",
    }


def test_parse_tool_call_arguments_salvages_truncated_description():
    raw = (
        '{"project":"TS","issue_type":"Task","summary":"QueensNdolls integration",'
        '"description":"Integration with delivery and pickup app breaking due to FlexyCart'
    )
    parsed = parse_tool_call_arguments(raw, tool_name="jira_create_issue")
    assert parsed["project"] == "TS"
    assert parsed["issue_type"] == "Task"
    assert "QueensNdolls" in parsed["summary"]


def test_parse_tool_call_arguments_returns_empty_on_garbage():
    assert parse_tool_call_arguments("not json at all", tool_name="jira_create_issue") == {}


def test_openai_compat_tolerates_malformed_tool_json(monkeypatch):
    class FakeFunction:
        name = "jira_create_issue"
        arguments = (
            '{"project":"TS","issue_type":"Task","summary":"Bug",'
            '"description":"Long text that got cut off mid-string'
        )

    class FakeToolCall:
        id = "call_1"
        function = FakeFunction()

    class FakeMessage:
        content = None
        tool_calls = [FakeToolCall()]
        reasoning_content = None

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

        @staticmethod
        def model_dump() -> dict:
            return {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    cfg = AIProviderConfig(
        enabled=True,
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="test-model",
    )
    provider = OpenAICompatProvider("openai", cfg)
    monkeypatch.setattr(provider, "_get_client", lambda: FakeClient())

    from backend.ai.base import Message, ToolSchema

    response = provider.chat(
        [Message(role="user", content="create ticket")],
        tools=[ToolSchema(name="jira_create_issue", description="create", parameters={})],
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].arguments["project"] == "TS"
