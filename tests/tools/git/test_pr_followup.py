"""Tests for PR follow-up routing in the same chat session."""

from __future__ import annotations
from backend.orchestrator.processor import TaskProcessor, _tool_result_to_response
from backend.tools.result import ToolResult


from unittest.mock import MagicMock, patch

from backend.routing.git.direct import (
    extract_pr_from_session,
    should_run_pr_analysis,
    wants_pr_retry,
)
from backend.orchestrator.processor import TaskProcessor
from backend.models.config import GitConfig, default_config
from backend.models.session import ConversationSession, ConversationTurn
from backend.models.task import Task


def test_wants_pr_retry():
    assert wants_pr_retry("can you retry again?")
    assert wants_pr_retry("please try again")
    assert not wants_pr_retry("what are my open prs?")


def test_should_run_pr_analysis_for_followup_in_session():
    session = ConversationSession(
        key="ui:abc:abc",
        source="ui",
        scope_id="abc",
        thread_id="abc",
        turns=[
            ConversationTurn(
                role="user",
                content="review https://github.com/AcmeCorp/adhocs/pull/91",
            ),
        ],
        metadata={"active_pr": {"repo": "AcmeCorp/adhocs", "number": 91}},
    )
    followup = "but what it does? the business impact and all what is it all about?"
    assert should_run_pr_analysis(followup, session)
    assert extract_pr_from_session(session) == ("AcmeCorp/adhocs", 91)


def test_should_run_pr_analysis_for_retry_in_session():
    session = ConversationSession(
        key="slack:C1:100",
        source="slack",
        scope_id="C1",
        thread_id="100",
        turns=[
            ConversationTurn(
                role="user",
                content="review https://github.com/AcmeCorp/platform/pull/2040",
            ),
        ],
        metadata={"active_pr": {"repo": "AcmeCorp/platform", "number": 2040}},
    )
    assert should_run_pr_analysis("can you retry again?", session)


def test_processor_followup_reuses_session_pr_via_skill():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()
    mock_provider = MagicMock()
    processor.router.get.return_value = mock_provider
    cfg = config.ai.providers[config.ai.routing.investigation.provider]
    cfg.enabled = True

    session_key = "ui:abc:abc"
    processor.session_store = MagicMock()
    processor.session_store.load.return_value = ConversationSession(
        key=session_key,
        source="ui",
        scope_id="abc",
        thread_id="abc",
        turns=[
            ConversationTurn(
                role="user",
                content="review https://github.com/AcmeCorp/adhocs/pull/91",
            ),
        ],
        metadata={"active_pr": {"repo": "AcmeCorp/adhocs", "number": 91, "head": "feature/sqs"}},
    )

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="abc",
        metadata={"chat_id": "abc"},
        raw_text="what is the business impact?",
        cleaned_intent="what is the business impact?",
    )

    with patch.object(
        processor,
        "_prefetch_pr_context",
        return_value=("## Pre-fetched PR data\nRabbitMQ migration", {"repo": "AcmeCorp/adhocs", "number": 91}),
    ):
        with patch(
            "backend.orchestrator.graph.nodes.run_agent_loop",
            return_value="## 1. Executive Summary\n* **Business Impact:** High - RabbitMQ to SQS.",
        ) as mock_loop:
            with patch(
                "backend.agent.loop.run_agent_loop",
                return_value="## 1. Executive Summary\n* **Business Impact:** High - RabbitMQ to SQS.",
            ):
                response = processor.process(task)

    mock_loop.assert_called_once()
    assert "RabbitMQ" in response.payload.data["text"]


def test_processor_retry_routes_to_review_skill():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()
    mock_provider = MagicMock()
    processor.router.get.return_value = mock_provider
    cfg = config.ai.providers[config.ai.routing.investigation.provider]
    cfg.enabled = True

    session_key = "slack:C0BBJUVLQFR:1782050346.000539"
    processor.session_store = MagicMock()
    processor.session_store.load.return_value = ConversationSession(
        key=session_key,
        source="slack",
        scope_id="C0BBJUVLQFR",
        thread_id="1782050346.000539",
        turns=[
            ConversationTurn(
                role="user",
                content="can you review the PR - https://github.com/AcmeCorp/platform/pull/2040?",
            ),
            ConversationTurn(
                role="assistant",
                content="Prior review output",
            ),
        ],
        metadata={"active_pr": {"repo": "AcmeCorp/platform", "number": 2040, "head": "webhook-email-update"}},
    )

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C0BBJUVLQFR",
        thread_ts="1782050346.000539",
        raw_text="@alfred can you retry again?",
        cleaned_intent="can you retry again?",
        metadata={"in_existing_thread": True},
    )

    with patch.object(
        processor,
        "_prefetch_pr_context",
        return_value=("## Pre-fetched PR data\nPR #2040", {"repo": "AcmeCorp/platform", "number": 2040}),
    ):
        with patch(
            "backend.orchestrator.graph.nodes.run_agent_loop",
            return_value="## 1. Executive Summary\n* **PR Objective:** Email in webhook",
        ) as mock_loop:
            with patch(
                "backend.agent.loop.run_agent_loop",
                return_value="## 1. Executive Summary\n* **PR Objective:** Email in webhook",
            ):
                response = processor.process(task)

    mock_loop.assert_called_once()
    assert "Executive Summary" in response.payload.data["text"]
    messages = mock_loop.call_args.args[1]
    roles = [m.role for m in messages]
    assert "assistant" in roles


def test_investigation_prefers_llm_text_over_last_tool_result():
    """PR review must return the model's analysis, not raw read_file output."""
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")
    processor = TaskProcessor(config)
    processor.router = MagicMock()
    mock_provider = MagicMock()
    processor.router.get.return_value = mock_provider
    cfg = config.ai.providers[config.ai.routing.investigation.provider]
    cfg.enabled = True

    review_text = "## 1. Executive Summary\n* **PR Objective:** Fix webhook email"
    with patch("backend.agent.loop.run_agent_loop", return_value=review_text):
        with patch("backend.tools.builder.build_git_tool_registry") as mock_registry_cls:
            registry = mock_registry_cls.return_value
            registry.last_result = ToolResult(
                kind="file_content",
                data={"repo": "AcmeCorp/platform", "path": "utils.ts", "content": "code"},
            )
            registry.last_tool_name = "read_file"
            registry.last_tool_args = {"repo": "AcmeCorp/platform", "path": "utils.ts"}

            response, _ = processor._run_investigation(
                processor._playbooks.get_by_name("review_pr"),
                [],
                provider=mock_provider,
                model="test",
                task=Task(
                    source="ui",
                    user_id="u1",
                    channel_id="ui:x:x",
                    raw_text="retry",
                    cleaned_intent="retry",
                ),
                session=None,
            )

    assert response.payload.kind == "text"
    assert "Executive Summary" in response.payload.data["text"]

    structured = _tool_result_to_response(
        ToolResult(kind="file_content", data={"repo": "r", "path": "p.ts", "content": "x"}),
    )
    assert structured is not None
    assert structured.payload.kind == "file_content"
