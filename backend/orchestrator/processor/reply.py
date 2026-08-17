"""Finish, format, and failure replies."""

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


class ReplyMixin:
    def _finish_response(
        self,
        response: AssistantResponse,
        *,
        tool_plan: Any | None = None,
        skill: Any | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> AssistantResponse:
        from backend.routing.reply_meta import finalize_reply_meta

        explicit = None
        if metadata_patch:
            raw = metadata_patch.get("reply_meta")
            if isinstance(raw, dict):
                explicit = raw
        return finalize_reply_meta(
            response,
            tool_plan=tool_plan,
            skill_name=str(skill.name) if skill else "",
            explicit=explicit,
        )

    def _synthesize_doc_answer(
        self,
        question: str,
        *,
        doc_path: str,
        doc_content: str,
        repo: str = "",
    ) -> str:
        """Summarize a doc excerpt for the user question with citations."""
        excerpt = doc_content.strip()
        if not excerpt:
            return format_doc_search({"query": question, "results": [], "found": False})

        header = f"**Source:** `{doc_path}`"
        if repo:
            header = f"**Source:** `{doc_path}` ({repo})"

        provider_name, provider, model_name = self._resolve_llm("investigation")
        system = (
            "You answer FlexyPe support documentation questions using ONLY the excerpt provided. "
            "Start with **Yes** or **No** on whether the asked integration/feature is supported or documented. "
            "If Yes, give concise setup steps (numbered). If No, say clearly it is not documented/supported — "
            "do NOT describe a different product or integration. "
            "Never paste raw MDX/JSX tags or frontmatter. Cite the doc path at the end."
        )
        user = (
            f"{header}\n\nQuestion: {question.strip()}\n\nDocumentation excerpt:\n{excerpt[:12000]}"
        )
        try:
            response = provider.chat(
                [
                    Message(role="system", content=system),
                    Message(role="user", content=user),
                ],
                model=model_name or None,
            )
            text = (response.content or "").strip()
            if text:
                return text
        except Exception as exc:
            logger.warning("Doc answer synthesis failed: %s", exc)

        return (
            f"I found `{doc_path}` but couldn't summarize it. "
            "Open that doc in the knowledge base for full steps."
        )

    def _investigation_failure_response(
        self,
        skill: Playbook,
        allowed_tools: list[str],
        exc: Exception,
    ) -> AssistantResponse:
        from backend.routing.tool_availability import resolvable_playbook_tools
        from backend.tools.catalog import GIT_WRITE_TOOLS

        message = str(exc)
        if "No tools available for the matched skill" in message:
            available, unknown, disabled = resolvable_playbook_tools(
                allowed_tools,
                self.config,
            )
            parts = [
                f"I couldn't run skill **{skill.name}**: none of its allowed tools are registered.",
            ]
            if unknown:
                parts.append(
                    f"Unknown or removed tools: {', '.join(unknown)}. "
                    "Update the playbook allowlist under `.alfred/playbooks/`."
                )
            if disabled:
                parts.append(f"Disabled by current config: {', '.join(disabled)}.")
            if any(name in GIT_WRITE_TOOLS for name in allowed_tools) and not self.config.git.write_enabled:
                parts.append(
                    "Enable **git.write_enabled** in Admin → Integrations to use PR/write tools."
                )
            if not self.config.git.enabled:
                parts.append("Enable **git.enabled** and set a valid token in Admin → Secrets.")
            return AssistantResponse.from_text(" ".join(parts))

        return AssistantResponse.from_text(
            f"I couldn't complete skill **{skill.name}**: {exc}."
        )

    def _summarize_pr(self, detail: dict[str, Any], task: Task) -> str | None:
        """One-shot LLM summary of a fetched PR (after get_pr)."""
        from backend.observability.context import set_call_kind

        set_call_kind("pr_summary")
        body = (detail.get("body") or "").strip()
        title = detail.get("title") or "Untitled"
        repo = detail.get("repo") or ""
        number = detail.get("number")
        url = detail.get("url") or ""

        _, provider, model = self._resolve_llm("basic_chat")
        prompt = (
            f"Summarize this pull request in 2–4 sentences. "
            f"Include what changed and why if known.\n\n"
            f"PR: #{number} {title}\n"
            f"Repo: {repo}\n"
            f"URL: {url}\n"
            f"Branch: {detail.get('head')} → {detail.get('base')}\n\n"
            f"Description:\n{body or '(no description provided)'}"
        )
        try:
            response = provider.chat([Message(role="user", content=prompt)], model=model or None)
            text = (response.content or "").strip()
            return text if text else None
        except Exception:
            logger.exception("PR summary generation failed")
            return None


