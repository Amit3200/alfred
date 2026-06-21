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
        "jira_list",
        "jira_detail",
        "jira_action",
        "athena_query",
        "cloudwatch_query",
        "cloudwatch_log_groups",
        "grade_events_query",
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
        self.router = LLMRouter.from_config(config, data_dir=data_dir)
        self.session_store = session_store
        self._context_fetcher = context_fetcher
        self._playbooks = playbook_store or PlaybookStore(
            data_dir,
            disabled_skills=config.skills.disabled,
        )
        self._data_dir = data_dir

    def process(self, task: Task) -> AssistantResponse:
        from backend.observability.context import interaction_scope, set_call_kind, set_skill_name

        logger.debug("Processing task %s source=%s", task.id, task.source)
        with interaction_scope(task) as _ctx:
            return self._process_task(task, set_call_kind=set_call_kind, set_skill_name=set_skill_name)

    def _process_task(
        self,
        task: Task,
        *,
        set_call_kind: Any,
        set_skill_name: Any,
    ) -> AssistantResponse:
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

        repo_hint = str(task.metadata.get("repo") or task.metadata.get("repository") or "")

        investigation = self._playbooks.pick_investigation(
            task.cleaned_intent,
            channel_id=task.channel_id,
            repo=repo_hint,
        )
        if investigation is None and self.config.git.enabled:
            from backend.ingress.git_direct import looks_like_code_investigation

            if looks_like_code_investigation(task.cleaned_intent):
                investigation = self._playbooks.get_by_name("investigate_bug")
        if investigation is None and self.config.jira.enabled:
            from backend.ingress.jira_direct import looks_like_jira_question

            if looks_like_jira_question(task.cleaned_intent):
                investigation = (
                    self._playbooks.get_by_name("jira_management")
                    or self._playbooks.get_by_name("jira_ticket")
                )
        if investigation is None and self.config.slack.enabled:
            from backend.ingress.user_identity import is_user_identity_lookup

            if is_user_identity_lookup(task.cleaned_intent):
                investigation = self._playbooks.get_by_name("jira_management")
        review_skill = self._resolve_pr_review_skill(investigation, task, session)
        omit_assistant = omit_assistant_session_history(
            task.cleaned_intent,
            include_context=include_context,
            pr_review_active=bool(review_skill),
        )
        active_skill = review_skill or investigation
        set_skill_name(active_skill.name if active_skill else None)

        git_context_prompt = ""
        if active_skill and session and self.config.git.enabled:
            from backend.ingress.git_context import format_session_git_context

            git_context_prompt = format_session_git_context(session, task.cleaned_intent)

        jira_context_prompt = ""
        if (
            active_skill
            and active_skill.name in ("jira_management", "jira_ticket")
            and self.config.jira.enabled
        ):
            from backend.ingress.jira_context import format_jira_context_for_prompt

            jira_context_prompt = format_jira_context_for_prompt(
                self.config,
                task,
                session,
                data_dir=self._data_dir_path(),
            )

        pr_context_prompt = ""
        pr_metadata: dict[str, Any] | None = None
        if review_skill and self.config.git.enabled:
            pr_context_prompt, pr_metadata = self._prefetch_pr_context(task, session=session)

        conversational = None if active_skill else self._playbooks.pick_conversational(
            task.cleaned_intent,
            channel_id=task.channel_id,
            repo=repo_hint,
        )
        routed_playbook = active_skill or conversational

        repo_context_prompt = ""
        if self.config.git.enabled:
            from backend.context.generator import load_repo_context_for_prompt

            repo_context_prompt = load_repo_context_for_prompt(
                self._data_dir_path(),
                self.config.git,
            )

        extra_system = "\n\n".join(
            part
            for part in (repo_context_prompt, git_context_prompt, jira_context_prompt, pr_context_prompt)
            if part
        )
        messages = self._build_messages(
            task,
            session=session,
            slack_context=slack_context if include_context else None,
            history_window_label=history_window_label if include_context else "",
            omit_assistant_turns=omit_assistant,
            playbook_prompt=self._playbooks.format_routed_prompt(
                routed_playbook,
                channel_id=task.channel_id,
                repo=repo_hint,
                data_dir=self._data_dir_path(),
            ),
            extra_system=extra_system,
        )

        response: AssistantResponse | None = None
        metadata_patch: dict[str, Any] | None = None
        if pr_metadata:
            metadata_patch = {"active_pr": pr_metadata}

        if review_skill and self.config.git.enabled:
            set_call_kind("investigation")
            provider_name, provider, model_name = self._select_provider(review_skill)
            logger.info(
                "Skill-guided PR review: %s provider=%s model=%s prefetched=%s",
                review_skill.name,
                provider_name,
                model_name,
                bool(pr_context_prompt),
            )
            response, inv_patch = self._run_investigation(
                review_skill,
                messages,
                provider=provider,
                model=model_name,
                task=task,
                session=session,
            )
            if inv_patch:
                metadata_patch = {**(metadata_patch or {}), **inv_patch}
        elif self.config.git.enabled or self.config.jira.enabled or self.config.slack.enabled:
            from backend.ingress.user_identity import is_user_identity_lookup

            if investigation and investigation.name in ("jira_ticket", "jira_management") and (
                self.config.jira.enabled or is_user_identity_lookup(task.cleaned_intent)
            ):
                set_call_kind("investigation")
                response, inv_patch = self._try_direct_jira(investigation, task, session)
                if inv_patch:
                    metadata_patch = {**(metadata_patch or {}), **inv_patch}

            if response is None and investigation:
                set_call_kind("investigation")
                response, inv_patch = self._try_direct_investigate(investigation, task, session)
                if inv_patch:
                    metadata_patch = {**(metadata_patch or {}), **inv_patch}

            if response is None and investigation and investigation.allowed_tools:
                set_call_kind("git_direct")
                response, git_patch = self._try_direct_git(investigation, task, session)
                if git_patch:
                    metadata_patch = {**(metadata_patch or {}), **git_patch}

        if response is None:
            provider_name, provider, model_name = self._select_provider(investigation)
            logger.debug(
                "Calling provider=%s model=%s session=%s turns=%d context=%s routed_playbook=%s investigation=%s",
                provider_name,
                model_name,
                session_key,
                len(session.turns) if session else 0,
                include_context,
                routed_playbook.name if routed_playbook else None,
                bool(investigation),
            )

            if investigation and investigation.allowed_tools and (
                self.config.git.enabled or self.config.jira.enabled
            ):
                set_call_kind("investigation")
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
                from backend.ingress.git_direct import looks_like_tool_json

                set_call_kind("chat")
                llm_response = provider.chat(messages, model=model_name or None)
                raw = (llm_response.content or "").strip()
                content = clean_response_scaffold(raw)
                if (not content or looks_like_tool_json(raw)) and self.config.git.enabled:
                    inv = self._playbooks.get_by_name("investigate_bug")
                    if inv and inv.allowed_tools:
                        set_call_kind("investigation")
                        inv_name, inv_provider, inv_model = self._select_provider(inv)
                        response, inv_patch = self._run_investigation(
                            inv,
                            messages,
                            provider=inv_provider,
                            model=inv_model,
                            task=task,
                            session=session,
                        )
                        if inv_patch:
                            metadata_patch = {**(metadata_patch or {}), **inv_patch}
                    elif not content:
                        response = AssistantResponse.from_text(
                            "I couldn't generate a reply — the model returned an empty response. "
                            "For Kimi K2.6, try again or check Admin → AI; large Slack summaries "
                            "may need a playbook for ticket formatting."
                        )
                    else:
                        response = AssistantResponse.from_text(content)
                elif content:
                    response = AssistantResponse.from_text(content)
                else:
                    response = AssistantResponse.from_text(
                        "I couldn't generate a reply — the model returned an empty response. "
                        "For Kimi K2.6, try again or check Admin → AI; large Slack summaries "
                        "may need a playbook for ticket formatting."
                    )

        if session_key and self.session_store:
            if response.payload.kind in STRUCTURED_TOOL_KINDS and response.text:
                rendered = response.text
            else:
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

    def _resolve_pr_review_skill(
        self,
        investigation: Playbook | None,
        task: Task,
        session: ConversationSession | None,
    ) -> Playbook | None:
        """Return the review_pr skill when intent is a PR review or thread follow-up."""
        from backend.ingress.git_direct import should_run_pr_analysis

        if investigation and investigation.name == "review_pr":
            return investigation
        if should_run_pr_analysis(task.cleaned_intent, session):
            return self._playbooks.get_by_name("review_pr")
        return None

    def _prefetch_pr_context(
        self,
        task: Task,
        *,
        session: ConversationSession | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Gather PR facts for injection; analysis is driven by the review_pr skill."""
        from backend.ingress.git_direct import resolve_pr_for_analysis
        from backend.ingress.pr_analysis import format_pr_context_for_prompt, gather_pr_context

        ref = resolve_pr_for_analysis(task.cleaned_intent, session)
        if not ref:
            return "", None

        repo, number = ref
        logger.info("Pre-fetching PR context: %s #%s", repo, number)
        try:
            ctx = gather_pr_context(
                self.config,
                data_dir=self._data_dir_path(),
                workspace_id=mirror_workspace_key(task),
                repo=repo,
                number=number,
            )
        except RuntimeError as exc:
            logger.warning("PR context fetch failed: %s", exc)
            return "", None
        except Exception:
            logger.exception("PR context fetch failed")
            return "", None

        return format_pr_context_for_prompt(ctx), ctx.metadata

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

    def _try_direct_jira(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None = None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        from backend.ingress.jira_direct import detect_jira_direct_action
        from backend.tools.git_api import build_git_tool_registry

        direct = detect_jira_direct_action(
            task.cleaned_intent,
            self.config,
            task,
            data_dir=self._data_dir_path(),
            session=session,
        )
        if not direct:
            return None, None
        tool_name, tool_args = direct
        if tool_name not in skill.allowed_tools:
            return None, None

        logger.info("Direct JIRA tool: %s", tool_name)
        if tool_name == "lookup_user_identity":
            from backend.ingress.user_identity import format_user_identity_result, lookup_user_identity

            data = lookup_user_identity(
                self.config,
                task=task,
                data_dir=self._data_dir_path(),
                slack_user_id=str(tool_args.get("slack_user_id") or ""),
                query=str(tool_args.get("query") or ""),
                targets=tool_args.get("targets"),
            )
            if data.get("error"):
                return AssistantResponse.error(str(data["error"])), None
            return AssistantResponse.from_text(format_user_identity_result(data)), None

        if tool_name == "build_workspace_identity_map":
            from backend.ingress.user_identity import (
                build_workspace_identity_map,
                format_user_identity_result,
            )

            data = build_workspace_identity_map(
                self.config,
                data_dir=self._data_dir_path(),
                include_github=bool(tool_args.get("include_github", True)),
            )
            if data.get("error"):
                return AssistantResponse.error(str(data["error"])), None
            return AssistantResponse.from_text(format_user_identity_result(data)), None

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
        )
        if result.kind == "error":
            return AssistantResponse.error(result.data.get("message", "JIRA tool failed.")), None

        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, None
        return None, None

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
        from backend.ingress.git_direct import looks_like_tool_json, strip_text_tool_markup
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

        raw_stripped = strip_text_tool_markup((raw or "").strip()).strip()
        prose = (
            clean_response_scaffold(raw_stripped)
            if raw_stripped and not looks_like_tool_json(raw_stripped)
            else ""
        )

        if registry.last_result and registry.last_result.kind in STRUCTURED_TOOL_KINDS:
            structured = _tool_result_to_response(registry.last_result)
            if structured is not None:
                if prose:
                    structured.text = prose
                return structured, patch

        if prose:
            return AssistantResponse.from_text(prose), patch

        if looks_like_tool_json(raw_stripped):
            return (
                AssistantResponse.from_text(
                    "I couldn't complete the Git lookup — the AI model failed to run tools. "
                    "Try a direct question like: *where is X handled in org/repo?*"
                ),
                patch,
            )
        return AssistantResponse.from_text(
            clean_response_scaffold(raw_stripped)
            or "I ran the available tools but couldn't form a final answer."
        ), patch

    def _summarize_pr(self, detail: dict[str, Any], task: Task) -> str | None:
        """One-shot LLM summary of a fetched PR (after get_pr)."""
        from backend.observability.context import set_call_kind

        set_call_kind("pr_summary")
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
    if result.kind == "user_identity":
        from backend.ingress.user_identity import format_user_identity_result

        return AssistantResponse.from_text(format_user_identity_result(result.data))
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
    if task.source == "git":
        return "github"
    return "cli"


def clean_message_text(text: str) -> str:
    from backend.ingress.sanitize import clean_slack_text

    return clean_slack_text(text)
