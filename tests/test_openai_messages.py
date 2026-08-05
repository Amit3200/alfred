"""Tests for OpenAI message serialization."""

from backend.ai.base import Message, ToolCall
from backend.ai.openai_messages import message_to_openai_api


def test_tool_message_serialization():
    payload = message_to_openai_api(
        Message(role="tool", content="result", tool_call_id="call_1", name="demo")
    )
    assert payload["role"] == "tool"
    assert payload["tool_call_id"] == "call_1"


def test_assistant_tool_calls_serialization():
    payload = message_to_openai_api(
        Message(
            role="assistant",
            content="Calling tool",
            tool_calls=[ToolCall(id="c1", name="demo", arguments={"x": 1})],
        )
    )
    assert payload["role"] == "assistant"
    assert payload["content"] == "Calling tool"
    assert payload["tool_calls"][0]["function"]["name"] == "demo"


def test_assistant_tool_calls_empty_content_gets_placeholder():
    payload = message_to_openai_api(
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="c1", name="search_repo_docs", arguments={"query": "mobile"})],
        )
    )
    assert payload["content"] == "Calling tools: search_repo_docs"
    assert payload["tool_calls"][0]["function"]["name"] == "search_repo_docs"
