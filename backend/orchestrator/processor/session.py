"""Session load, messages, governance attach."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Literal

from backend.ai.base import Message
from backend.ai.registry import LLMRouter
from backend.orchestrator.policy import (
    needs_context_refresh,
    omit_assistant_session_history,
)
from backend.orchestrator.task_cancel import TaskCancelledError, raise_if_cancelled
from backend.routing.playbook_store_registry import get_playbook_store
from backend.routing.playbooks import Playbook, PlaybookStore
from backend.orchestrator.prompts import GITHUB_COMMENT_RULES, build_alfred_system_prompt, build_slack_user_message
from backend.formatting.render import Channel, render_for_channel
from backend.formatting.sanitize import clean_response_scaffold
from backend.integrations.slack.context import SlackContextBundle
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse, ResponsePayload
from backend.models.session import ConversationSession, mirror_workspace_key, task_session_key
from backend.models.task import Task
from backend.paths import get_data_dir
from backend.db.session_store import SessionStore
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)


class SessionMixin:
    def _maybe_grant_write_approval(
        self,
        task: Task,
        session: ConversationSession | None,
    ) -> dict[str, Any] | None:
        from backend.governance.confirmation import approval_metadata_patch, is_confirmation_phrase

        if not self.config.governance.enabled or not self.config.governance.require_confirmation:
            return None
        if not is_confirmation_phrase(task.cleaned_intent, self.config.governance):
            return None
        return approval_metadata_patch(
            user_id=task.user_id,
            ttl_minutes=self.config.governance.approval_ttl_minutes,
        )

    def _attach_governance(
        self,
        registry: Any,
        task: Task,
        *,
        session: ConversationSession | None,
        skill_name: str | None,
    ) -> None:
        from backend.governance.context import GovernanceContext

        registry.governance = GovernanceContext(
            self.config,
            task,
            session=session,
            skill_name=skill_name,
            data_dir=self._data_dir_path(),
        )

    def _load_session(self, session_key: str | None) -> ConversationSession | None:
        if not session_key or not self.session_store:
            return None
        return self.session_store.load(session_key)

    def _data_dir_path(self) -> Path:
        return get_data_dir(self._data_dir)

    def _build_messages(
        self,
        task: Task,
        *,
        session: ConversationSession | None,
        slack_context: str | None,
        history_window_label: str = "",
        slack_user_names: dict[str, str] | None = None,
        omit_assistant_turns: bool = False,
        playbook_prompt: str = "",
        extra_system: str = "",
        model_name: str | None = None,
    ) -> list[Message]:
        system_parts = [
            build_alfred_system_prompt(
                self.config,
                model_name=model_name,
                include_slack_rules=task.source == "slack",
            )
        ]
        if task.source == "git":
            system_parts.append(GITHUB_COMMENT_RULES)
        if playbook_prompt:
            system_parts.append(playbook_prompt)
        if extra_system:
            system_parts.append(extra_system)
        messages: list[Message] = [Message(role="system", content="\n\n".join(system_parts))]

        if session:
            from backend.orchestrator.policy import prune_context
            for turn in session.turns:
                if omit_assistant_turns and turn.role == "assistant":
                    continue
                pruned_content = prune_context(turn.content or "")
                messages.append(Message(role=turn.role, content=pruned_content))

        if task.source == "slack":
            user_content = build_slack_user_message(
                task.cleaned_intent,
                slack_context,
                history_window_label=history_window_label,
                user_names=slack_user_names,
            )
        elif slack_context:
            user_content = f"{task.cleaned_intent}\n\n[Context]\n{slack_context}"
        else:
            user_content = task.cleaned_intent

        already_has_current_user = (
            session
            and session.turns
            and session.turns[-1].role == "user"
            and (session.turns[-1].content or "").strip() == user_content.strip()
        )
        if not already_has_current_user:
            messages.append(Message(role="user", content=user_content))
        return messages

