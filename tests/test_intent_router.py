"""Tests for the Unified Intent Router."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.routing.playbooks import PlaybookStore, Playbook
from backend.models.config import AlfredConfig, default_config
from backend.models.task import Task
from backend.routing.intent import detect_direct_action


def test_detect_direct_action_user_identity():
    config = default_config()
    config.jira.enabled = True
    config.slack.enabled = True

    task = Task(
        id="task-1",
        source="slack",
        raw_text="map all users",
        cleaned_intent="map all users",
        user_id="U123",
        channel_id="C123",
    )

    action = detect_direct_action(
        intent="map all users",
        config=config,
        task=task,
    )
    assert action is not None
    assert action[0] == "build_workspace_identity_map"


def test_detect_direct_action_jira_issue():
    config = default_config()
    config.jira.enabled = True

    task = Task(
        id="task-2",
        source="slack",
        raw_text="status of TECH-123",
        cleaned_intent="status of TECH-123",
        user_id="U123",
        channel_id="C123",
    )

    action = detect_direct_action(
        intent="status of TECH-123",
        config=config,
        task=task,
    )
    assert action is not None
    assert action[0] == "get_jira_issue"
    assert action[1]["issue_key"] == "TECH-123"


def test_detect_direct_action_git_status():
    config = default_config()
    config.git.enabled = True

    task = Task(
        id="task-3",
        source="slack",
        raw_text="what are my open PRs?",
        cleaned_intent="what are my open PRs?",
        user_id="U123",
        channel_id="C123",
    )

    skill = Playbook(
        name="git_status",
        path=Path("git_status.md"),
        description="status",
        mode="investigation",
        allowed_tools=["list_my_prs"],
        _body="",
    )

    action = detect_direct_action(
        intent="what are my open PRs?",
        config=config,
        task=task,
        playbook=skill,
    )
    assert action is not None
    assert action[0] == "list_my_prs"
