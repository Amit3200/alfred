"""Process Tasks with the configured AI provider and per-thread session memory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Literal

from backend.ai.base import Message
from backend.ai.registry import LLMRouter
from backend.ingress.context_policy import (
    needs_context_refresh,
    omit_assistant_session_history,
)
from backend.ingress.playbooks import Playbook, PlaybookStore
from backend.ingress.prompts import ALFRED_SYSTEM_PROMPT, build_slack_user_message
from backend.ingress.render import Channel, render_for_channel
from backend.ingress.response_clean import clean_response_scaffold
from backend.ingress.slack_context import SlackContextBundle
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse, ResponsePayload
from backend.models.session import ConversationSession, mirror_workspace_key, task_session_key
from backend.models.task import Task
from backend.paths import get_data_dir
from backend.storage.session_store import SessionStore
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)

STRUCTURED_TOOL_KINDS = frozenset(
    {
        "pr_list",
        "pr_detail",
        "repo_list",
        "code_grep",
        "file_content",
        "git_log",
        "git_blame",
        "git_show",
    }
)


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
        self._playbooks = playbook_store or PlaybookStore(
            data_dir,
            disabled_skills=config.skills.disabled,
        )
        self._data_dir = data_dir

    def process(self, task: Task) -> AssistantResponse:
        logger.debug("Processing task %s source=%s", task.id, task.source)
        session_key = task_session_key(task)
        session = self._load_session(session_key)
        channel = _task_channel(task)

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
        investigation = self._playbooks.pick_investigation(
            task.cleaned_intent,
            channel_id=task.channel_id,
        )
        prompt_playbooks = [investigation] if investigation else matched_playbooks
        git_context_prompt = ""
        if investigation and session and self.config.git.enabled:
            from backend.ingress.git_context import format_session_git_context

            git_context_prompt = format_session_git_context(session, task.cleaned_intent)

        messages = self._build_messages(
            task,
            session=session,
            slack_context=slack_context if include_context else None,
            history_window_label=history_window_label if include_context else "",
            omit_assistant_turns=omit_assistant,
            playbook_prompt=self._playbooks.format_for_prompt(prompt_playbooks),
            extra_system=git_context_prompt,
        )

        response: AssistantResponse | None = None
        metadata_patch: dict[str, Any] | None = None
        if self.config.git.enabled:
            response, pr_patch = self._try_direct_pr_analysis(task, session=session)
            if pr_patch:
                metadata_patch = {"active_pr": pr_patch}

            if response is None and investigation:
                response, inv_patch = self._try_direct_investigate(investigation, task, session)
                if inv_patch:
                    metadata_patch = {**(metadata_patch or {}), **inv_patch}

            if response is None and investigation and investigation.allowed_tools:
                response, git_patch = self._try_direct_git(investigation, task, session)
                if git_patch:
                    metadata_patch = {**(metadata_patch or {}), **git_patch}

        if response is None:
            provider_name, provider, model_name = self._select_provider(investigation)
            logger.debug(
                "Calling provider=%s model=%s session=%s turns=%d context=%s playbooks=%d investigation=%s",
                provider_name,
                model_name,
                session_key,
                len(session.turns) if session else 0,
                include_context,
                len(prompt_playbooks),
                bool(investigation),
            )

            if investigation and investigation.allowed_tools and self.config.git.enabled:
                response, inv_patch = self._run_investigation(
                    investigation,
                    messages,
                    provider=provider,
                    model=model_name,
                    task=task,
                    session=session,
                )
                if inv_patch:
                    metadata_patch = {**(metadata_patch or {}), **inv_patch}
            else:
                llm_response = provider.chat(messages, model=model_name or None)
                content = clean_response_scaffold((llm_response.content or "").strip())
                response = (
                    AssistantResponse.from_text(content)
                    if content
                    else AssistantResponse.from_text(
                        "I couldn't generate a reply from the model. "
                        "Check AI settings and that Ollama (or your provider) is running."
                    )
                )

        if session_key and self.session_store:
            rendered = render_for_channel(response, channel)
            self.session_store.append_exchange(
                session_key,
                source=task.source,
                scope_id=task.channel_id,
                thread_id=task.thread_ts or "",
                user_content=task.cleaned_intent,
                assistant_content=rendered,
                assistant_payload=response.payload,
                context_snapshot=slack_context if include_context else None,
                metadata_patch=metadata_patch,
            )
            logger.info("Session updated: %s", session_key)

        return response

    def _select_provider(self, investigation: Playbook | None) -> tuple[str, Any, str]:
        if investigation:
            name = self.config.ai.routing.investigation
            cfg = self.config.ai.providers.get(name)
            if cfg and cfg.enabled:
                provider = self.router.get(name)
                if provider.is_available():
                    return name, provider, cfg.model or ""
        name = self.config.ai.default_provider
        provider = self.router.get(name)
        cfg = self.config.ai.providers[name]
        return name, provider, cfg.model or ""

    def _try_direct_pr_analysis(
        self,
        task: Task,
        *,
        session: ConversationSession | None = None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Fetch PR diffs, checkout head branch, and produce a code-level review."""
        from backend.ingress.git_direct import (
            pr_analysis_focus,
            resolve_pr_for_analysis,
            should_run_pr_analysis,
        )
        from backend.ingress.pr_analysis import analyze_pull_request

        if not should_run_pr_analysis(task.cleaned_intent, session):
            return None, None
        ref = resolve_pr_for_analysis(task.cleaned_intent, session)
        if not ref:
            return None, None

        repo, number = ref
        focus = pr_analysis_focus(task.cleaned_intent)
        logger.info("Direct PR code analysis: %s #%s (focus=%s)", repo, number, focus)
        inv_skill = Playbook(
            name="review_pr",
            path=Path("review_pr.md"),
            body="",
            mode="investigation",
            allowed_tools=["get_pr"],
        )
        _, provider, model = self._select_provider(inv_skill)
        try:
            analysis, context = analyze_pull_request(
                self.config,
                data_dir=self._data_dir_path(),
                workspace_id=mirror_workspace_key(task),
                repo=repo,
                number=number,
                provider=provider,
                model=model or None,
                focus=focus,
            )
        except RuntimeError as exc:
            return AssistantResponse.error(str(exc)), None
        except Exception as exc:
            logger.exception("PR analysis failed")
            return AssistantResponse.error(f"PR analysis failed: {exc}"), None

        if analysis:
            return (
                AssistantResponse.from_text(clean_response_scaffold(analysis.strip())),
                context or None,
            )
        return (
            AssistantResponse.from_text(
                "I fetched the PR but couldn't generate a review. "
                "Check that your Git token has access and the AI provider is running."
            ),
            context or None,
        )

    def _try_direct_investigate(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Run local git tools directly for code investigation intents."""
        from backend.ingress.git_context import (
            detect_investigate_direct_action,
            metadata_patch_for_tool_result,
        )
        from backend.tools.git_api import build_git_tool_registry

        direct = detect_investigate_direct_action(
            task.cleaned_intent,
            skill.name,
            self.config.git,
            session,
        )
        if not direct:
            return None, None
        tool_name, tool_args = direct
        if tool_name not in skill.allowed_tools:
            return None, None

        logger.info("Direct investigate tool: %s", tool_name)
        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
        )
        result = registry.run_normalized(
            tool_name,
            tool_args,
            allowed=skill.allowed_tools,
            git=self.config.git,
            session=session,
        )
        if result.kind == "error":
            return AssistantResponse.error(result.data.get("message", "Git tool failed.")), None

        patch = metadata_patch_for_tool_result(tool_name, tool_args, result)
        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, patch
        return None, patch

    def _try_direct_git(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Run a Git API tool directly when the question is unambiguous (no LLM)."""
        from backend.ingress.git_direct import detect_git_direct_action, wants_pr_summary
        from backend.tools.git_api import build_git_tool_registry

        direct = detect_git_direct_action(task.cleaned_intent, skill, self.config.git)
        if not direct:
            return None, None
        tool_name, tool_args = direct
        if tool_name not in skill.allowed_tools:
            return None, None

        logger.info("Direct git tool: %s", tool_name)
        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
        )
        result = registry.run_normalized(
            tool_name,
            tool_args,
            allowed=skill.allowed_tools,
            git=self.config.git,
            session=session,
        )
        if result.kind == "error":
            return AssistantResponse.error(result.data.get("message", "Git tool failed.")), None

        from backend.ingress.git_context import metadata_patch_for_tool_result

        patch = metadata_patch_for_tool_result(tool_name, tool_args, result)

        if tool_name == "get_pr" and wants_pr_summary(task.cleaned_intent):
            from backend.ingress.git_direct import wants_pr_code_analysis

            detail = result.data.get("pr")
            if detail and not wants_pr_code_analysis(task.cleaned_intent):
                summary = self._summarize_pr(detail, task)
                if summary:
                    return AssistantResponse.from_text(clean_response_scaffold(summary.strip())), patch

        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, patch

        return (
            AssistantResponse.from_text(
                "I couldn't fetch PR data from Git. "
                "Check Admin → Secrets (Git token) and Integrations (Git enabled)."
            ),
            patch,
        )

    def _run_investigation(
        self,
        skill: Playbook,
        messages: list[Message],
        *,
        provider: Any,
        model: str,
        task: Task,
        session: ConversationSession | None,
    ) -> tuple[AssistantResponse, dict[str, Any] | None]:
        from backend.agent.loop import run_agent_loop
        from backend.ingress.git_direct import looks_like_tool_json
        from backend.ingress.git_context import metadata_patch_for_tool_result
        from backend.tools.git_api import build_git_tool_registry

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
        )

        try:
            raw = run_agent_loop(
                provider,
                messages,
                registry,
                skill.allowed_tools,
                model=model or None,
                session=session,
                git=self.config.git,
            )
        except Exception as exc:
            logger.exception("Investigation loop failed")
            return (
                AssistantResponse.from_text(
                    f"I couldn't complete the Git investigation: {exc}. "
                    "Check that Git is enabled and your token is valid in Admin → Secrets."
                ),
                None,
            )

        patch: dict[str, Any] | None = None
        if registry.last_result and registry.last_tool_name:
            patch = metadata_patch_for_tool_result(
                registry.last_tool_name,
                registry.last_tool_args or {},
                registry.last_result,
            )

        if registry.last_result and registry.last_result.kind in STRUCTURED_TOOL_KINDS:
            structured = _tool_result_to_response(registry.last_result)
            if structured is not None:
                return structured, patch

        if looks_like_tool_json(raw):
            return (
                AssistantResponse.from_text(
                    "I couldn't complete the Git lookup — the AI model failed to run tools. "
                    "Try a direct question like: *where is X handled in org/repo?*"
                ),
                patch,
            )
        return AssistantResponse.from_text(clean_response_scaffold(raw.strip())), patch

    def _summarize_pr(self, detail: dict[str, Any], task: Task) -> str | None:
        """One-shot LLM summary of a fetched PR (after get_pr)."""
        body = (detail.get("body") or "").strip()
        title = detail.get("title") or "Untitled"
        repo = detail.get("repo") or ""
        number = detail.get("number")
        url = detail.get("url") or ""

        _, provider, model = self._select_provider(None)
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
        omit_assistant_turns: bool = False,
        playbook_prompt: str = "",
        extra_system: str = "",
    ) -> list[Message]:
        system_parts = [ALFRED_SYSTEM_PROMPT]
        if playbook_prompt:
            system_parts.append(playbook_prompt)
        if extra_system:
            system_parts.append(extra_system)
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


def _tool_result_to_response(result: ToolResult) -> AssistantResponse | None:
    if result.kind in STRUCTURED_TOOL_KINDS:
        return AssistantResponse.structured(result.kind, result.data)
    if result.kind == "error":
        return AssistantResponse.error(str(result.data.get("message") or "Tool failed."))
    return None


def _task_channel(task: Task) -> Channel:
    if task.source == "slack":
        return "slack"
    if task.source == "ui":
        return "ui"
    return "cli"


def clean_message_text(text: str) -> str:
    from backend.ingress.sanitize import clean_slack_text

    return clean_slack_text(text)
