"""Process Tasks with the configured AI provider and per-thread session memory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from backend.ai.base import Message
from backend.ai.registry import LLMRouter
from backend.ingress.context_policy import (
    needs_context_refresh,
    omit_assistant_session_history,
)
from backend.ingress.playbooks import PlaybookStore
from backend.ingress.prompts import ALFRED_SYSTEM_PROMPT, build_slack_user_message
from backend.ingress.response_clean import clean_response_scaffold
from backend.ingress.slack_context import SlackContextBundle
from backend.ingress.slack_format import format_for_slack
from backend.models.config import AlfredConfig
from backend.models.session import ConversationSession, task_session_key
from backend.models.task import Task
from backend.storage.session_store import SessionStore

logger = logging.getLogger(__name__)


class TaskProcessor:
    def __init__(
        self,
        config: AlfredConfig,
        *,
        session_store: SessionStore | None = None,
        context_fetcher: Callable[[Task], SlackContextBundle | str | None] | None = None,
        playbook_store: PlaybookStore | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.router = LLMRouter.from_config(config)
        self.session_store = session_store
        self._context_fetcher = context_fetcher
        self._playbooks = playbook_store or PlaybookStore(data_dir)

    def process(self, task: Task) -> str:
        logger.debug("Processing task %s source=%s", task.id, task.source)
        session_key = task_session_key(task)
        session = self._load_session(session_key)

        slack_context: str | None = None
        history_window_label = ""
        if self._context_fetcher:
            try:
                raw_context = self._context_fetcher(task)
                if isinstance(raw_context, SlackContextBundle):
                    slack_context = raw_context.text or None
                    history_window_label = raw_context.history_window_label
                elif raw_context:
                    slack_context = raw_context
            except Exception:
                logger.exception("Failed to fetch Slack context for task %s", task.id)

        include_context = bool(
            slack_context
            and (
                task.source != "slack"
                or needs_context_refresh(task.cleaned_intent, has_session=bool(session and session.turns))
            )
        )

        omit_assistant = omit_assistant_session_history(
            task.cleaned_intent,
            include_context=include_context,
        )
        matched_playbooks = self._playbooks.match(
            task.cleaned_intent,
            channel_id=task.channel_id,
        )
        messages = self._build_messages(
            task,
            session=session,
            slack_context=slack_context if include_context else None,
            history_window_label=history_window_label if include_context else "",
            omit_assistant_turns=omit_assistant,
            playbook_prompt=self._playbooks.format_for_prompt(matched_playbooks),
        )

        provider_name = self.config.ai.default_provider
        provider = self.router.get(provider_name)
        provider_cfg = self.config.ai.providers[provider_name]
        logger.debug(
            "Calling provider=%s model=%s session=%s turns=%d context=%s playbooks=%d",
            provider_name,
            provider_cfg.model,
            session_key,
            len(session.turns) if session else 0,
            include_context,
            len(matched_playbooks),
        )

        response = provider.chat(messages, model=provider_cfg.model or None)
        content = clean_response_scaffold((response.content or "").strip())
        if not content:
            return (
                "I couldn't generate a reply from the model. "
                "Check AI settings and that Ollama (or your provider) is running."
            )
        if task.source == "slack":
            content = format_for_slack(content)

        if session_key and self.session_store:
            self.session_store.append_exchange(
                session_key,
                source=task.source,
                scope_id=task.channel_id,
                thread_id=task.thread_ts or "",
                user_content=task.cleaned_intent,
                assistant_content=content,
                context_snapshot=slack_context if include_context else None,
            )
            logger.info("Session updated: %s", session_key)

        return content

    def _load_session(self, session_key: str | None) -> ConversationSession | None:
        if not session_key or not self.session_store:
            return None
        return self.session_store.load(session_key)

    def _build_messages(
        self,
        task: Task,
        *,
        session: ConversationSession | None,
        slack_context: str | None,
        history_window_label: str = "",
        omit_assistant_turns: bool = False,
        playbook_prompt: str = "",
    ) -> list[Message]:
        system_parts = [ALFRED_SYSTEM_PROMPT]
        if playbook_prompt:
            system_parts.append(playbook_prompt)
        messages: list[Message] = [Message(role="system", content="\n\n".join(system_parts))]

        if session:
            for turn in session.turns:
                if omit_assistant_turns and turn.role == "assistant":
                    continue
                messages.append(Message(role=turn.role, content=turn.content))

        if task.source == "slack":
            user_content = build_slack_user_message(
                task.cleaned_intent,
                slack_context,
                history_window_label=history_window_label,
            )
        elif slack_context:
            user_content = f"{task.cleaned_intent}\n\n[Context]\n{slack_context}"
        else:
            user_content = task.cleaned_intent

        messages.append(Message(role="user", content=user_content))
        return messages


def clean_message_text(text: str) -> str:
    from backend.ingress.sanitize import clean_slack_text

    return clean_slack_text(text)
