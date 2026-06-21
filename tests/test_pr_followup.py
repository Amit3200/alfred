"""Tests for PR follow-up routing in the same chat session."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.ingress.git_direct import extract_pr_from_session, should_run_pr_analysis
from backend.ingress.processor import TaskProcessor
from backend.models.config import GitConfig, default_config
from backend.models.session import ConversationSession, ConversationTurn
from backend.models.task import Task


def test_should_run_pr_analysis_for_followup_in_session():
    session = ConversationSession(
        key="ui:abc:abc",
        source="ui",
        scope_id="abc",
        thread_id="abc",
        turns=[
            ConversationTurn(
                role="user",
                content="review https://github.com/FlexyPe/flexype-adhocs/pull/91",
            ),
        ],
        metadata={"active_pr": {"repo": "FlexyPe/flexype-adhocs", "number": 91}},
    )
    followup = "but what it does? the business impact and all what is it all about?"
    assert should_run_pr_analysis(followup, session)
    assert extract_pr_from_session(session) == ("FlexyPe/flexype-adhocs", 91)


def test_processor_followup_reuses_session_pr():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()
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
                content="review https://github.com/FlexyPe/flexype-adhocs/pull/91",
            ),
        ],
        metadata={"active_pr": {"repo": "FlexyPe/flexype-adhocs", "number": 91, "head": "feature/sqs"}},
    )

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="abc",
        metadata={"chat_id": "abc"},
        raw_text="what is the business impact?",
        cleaned_intent="what is the business impact?",
    )

    with patch("backend.ingress.pr_analysis.analyze_pull_request") as mock_analyze:
        mock_analyze.return_value = (
            "**Business impact**\nMigrates consumers from RabbitMQ to SQS.",
            {"repo": "FlexyPe/flexype-adhocs", "number": 91},
        )
        with patch("backend.agent.loop.run_agent_loop") as mock_loop:
            response = processor.process(task)

    mock_analyze.assert_called_once()
    assert mock_analyze.call_args.kwargs["focus"] == "business"
    assert "RabbitMQ" in response.payload.data["text"]
    mock_loop.assert_not_called()
