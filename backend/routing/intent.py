"""Unified intent routing — bypass LLM for unambiguous direct actions."""

from __future__ import annotations

import logging
from typing import Any

from backend.routing.git_context import detect_investigate_direct_action
from backend.routing.git_direct import detect_git_direct_action
from backend.routing.jira_direct import detect_jira_direct_action
from backend.routing.playbooks import Playbook
from backend.models.config import AlfredConfig
from backend.models.task import Task

logger = logging.getLogger(__name__)


def detect_direct_action(
    intent: str,
    config: AlfredConfig,
    task: Task,
    session: Any | None = None,
    playbook: Playbook | None = None,
    data_dir: Any | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Unified entry point to resolve direct (no-LLM) tool actions across all domains."""
    # 1. Check JIRA direct actions (internally delegates to user identity mapping as well)
    if config.jira.enabled or config.slack.enabled:
        jira_action = detect_jira_direct_action(
            intent,
            config,
            task,
            data_dir=data_dir,
            session=session,
        )
        if jira_action:
            logger.info("Unified Router: detected direct JIRA/identity action %s", jira_action[0])
            return jira_action

    # 2. Check Git/investigate direct actions
    if config.git.enabled and playbook:
        # Check git_status direct actions (e.g. list_my_prs, get_pr, list_repos)
        git_action = detect_git_direct_action(intent, playbook, config.git)
        if git_action:
            logger.info("Unified Router: detected direct Git action %s", git_action[0])
            return git_action

        # Check investigate_bug / review_pr direct actions (e.g. grep_repo, read_file)
        inv_action = detect_investigate_direct_action(
            intent,
            playbook.name,
            config.git,
            session,
        )
        if inv_action:
            logger.info("Unified Router: detected direct investigation action %s", inv_action[0])
            return inv_action

    return None
