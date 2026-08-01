"""Process Tasks with the configured AI provider and per-thread session memory."""

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

STRUCTURED_TOOL_KINDS = frozenset(
    {
        "pr_list",
        "pr_detail",
        "pr_created",
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
        "google_sheet",
        "google_doc",
        "web_search",
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
        skill_router: Any | None = None,
    ) -> None:
        self.config = config
        self.router = LLMRouter.from_config(config, data_dir=data_dir)
        self.session_store = session_store
        self._context_fetcher = context_fetcher
        self._playbooks = playbook_store or get_playbook_store(
            data_dir,
            disabled_skills=config.skills.disabled,
        )
        self._data_dir = data_dir
        from backend.routing import SkillRouter

        self._skill_router = skill_router or SkillRouter(
            config, self._playbooks, llm_router=self.router
        )

    def process(self, task: Task) -> AssistantResponse:
        from backend.observability.context import interaction_scope, set_call_kind, set_skill_name
        from backend.observability.checkpoint import log_checkpoint

        logger.debug("Processing task %s source=%s", task.id, task.source)
        log_checkpoint("process_task", task.id, "started")
        try:
            with interaction_scope(task) as _ctx:
                response = self._process_task(task, set_call_kind=set_call_kind, set_skill_name=set_skill_name)
                log_checkpoint("process_task", task.id, "completed")
                return response
        except TaskCancelledError:
            log_checkpoint("process_task", task.id, "cancelled")
            response = AssistantResponse.from_text("Request stopped.")
            session_key = task_session_key(task)
            if session_key and self.session_store:
                rendered = render_for_channel(response, _task_channel(task))
                self.session_store.append_assistant_turn(
                    session_key,
                    source=task.source,
                    scope_id=task.channel_id,
                    thread_id=task.thread_ts or "",
                    assistant_content=rendered,
                    assistant_payload=response.payload,
                )
            return response
        except Exception as exc:
            log_checkpoint("process_task", task.id, "error", error=exc)
            raise

    def _process_task(
        self,
        task: Task,
        *,
        set_call_kind: Any,
        set_skill_name: Any,
    ) -> AssistantResponse:
        raise_if_cancelled(self._data_dir_path(), task.id)

        session_key = task_session_key(task)
        session = self._load_session(session_key)
        channel = _task_channel(task)

        gov_patch = self._maybe_grant_write_approval(task, session)
        if gov_patch and session and session_key and self.session_store:
            session.metadata.update(gov_patch)
            self.session_store.save(session)
        elif gov_patch and session:
            session.metadata.update(gov_patch)

        if (
            self.config.governance.enabled
            and gov_patch
            and self._is_confirmation_only(task.cleaned_intent)
        ):
            from backend.governance.confirmation import confirmation_granted_message

            response = AssistantResponse.from_text(
                confirmation_granted_message(self.config.governance.approval_ttl_minutes)
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
                    metadata_patch=gov_patch,
                )
            return response

        slack_context: str | None = None
        history_window_label = ""
        slack_user_names: dict[str, str] = {}
        if self._context_fetcher:
            try:
                raw_context = self._context_fetcher(task)
                if isinstance(raw_context, SlackContextBundle):
                    slack_context = raw_context.text or None
                    history_window_label = raw_context.history_window_label
                    slack_user_names = raw_context.user_names or {}
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

        route_context = self._build_route_context(
            task,
            session=session,
            slack_context=slack_context if include_context else None,
            repo=repo_hint,
        )
        investigation = self._skill_router.route_investigation(route_context).playbook
        if investigation is None and self.config.jira.enabled:
            from backend.routing.jira_intent import (
                looks_like_jira_create_followup,
                looks_like_jira_create_request,
            )

            if looks_like_jira_create_request(task.cleaned_intent) or looks_like_jira_create_followup(
                task.cleaned_intent,
                session_turns=route_context.session_turns,
                thread_context=route_context.thread_context,
            ):
                investigation = self._playbooks.get_by_name("jira_management")
                if investigation:
                    logger.info("Forced jira_management for JIRA create intent (routing miss)")

        workflow_response, workflow_meta = self._try_workflow_entry(
            investigation,
            task,
            session=session,
            slack_context=slack_context if include_context else None,
        )
        if workflow_response is not None:
            if session_key and self.session_store:
                rendered = render_for_channel(workflow_response, channel)
                self.session_store.append_exchange(
                    session_key,
                    source=task.source,
                    scope_id=task.channel_id,
                    thread_id=task.thread_ts or "",
                    user_content=task.cleaned_intent,
                    assistant_content=rendered,
                    assistant_payload=workflow_response.payload,
                    context_snapshot=slack_context if include_context else None,
                    metadata_patch=workflow_meta,
                )
            return workflow_response

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
            from backend.routing.git_context import format_session_git_context

            git_context_prompt = format_session_git_context(session, task.cleaned_intent)

        jira_context_prompt = ""
        if (
            active_skill
            and active_skill.name in ("jira_management", "jira_ticket")
            and self.config.jira.enabled
        ):
            from backend.routing.jira_context import format_jira_context_for_prompt

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

        google_context_prompt = ""
        if self.config.google.enabled:
            from backend.integrations.google.context import format_google_context_for_prompt

            google_context_prompt = format_google_context_for_prompt(
                self.config,
                task,
                session,
            )

        conversational = None
        if not active_skill:
            conversational = self._skill_router.route_conversational(route_context).playbook
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
            for part in (
                repo_context_prompt,
                git_context_prompt,
                jira_context_prompt,
                google_context_prompt,
                pr_context_prompt,
            )
            if part
        )
        # Resolve target model early to allow model-specific system prompts
        if review_skill and self.config.git.enabled:
            provider_name, provider, model_name = self._resolve_llm("pr_review")
        elif investigation and investigation.mode == "workflow":
            provider_name, provider, model_name = self._resolve_llm("workflow_execution")
        elif investigation:
            provider_name, provider, model_name = self._resolve_llm("investigation")
        else:
            provider_name, provider, model_name = self._resolve_llm("basic_chat")

        messages = self._build_messages(
            task,
            session=session,
            slack_context=slack_context if include_context else None,
            history_window_label=history_window_label if include_context else "",
            slack_user_names=slack_user_names if include_context else None,
            omit_assistant_turns=omit_assistant,
            playbook_prompt=self._playbooks.format_routed_prompt(
                routed_playbook,
                channel_id=task.channel_id,
                repo=repo_hint,
                data_dir=self._data_dir_path(),
            ),
            extra_system=extra_system,
            model_name=model_name,
        )

        response: AssistantResponse | None = None
        metadata_patch: dict[str, Any] | None = None
        if pr_metadata:
            metadata_patch = {"active_pr": pr_metadata}

        if review_skill and self.config.git.enabled:
            set_call_kind("investigation")
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
            if investigation:
                set_call_kind("investigation")
                response, direct_patch = self._try_unified_direct(investigation, task, session)
                if direct_patch:
                    metadata_patch = {**(metadata_patch or {}), **direct_patch}

        if response is None:
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

            if investigation and (
                self.config.git.enabled or self.config.jira.enabled or self.config.google.enabled
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
                from backend.routing.git_direct import looks_like_tool_json

                set_call_kind("chat")
                try:
                    llm_response = provider.chat(messages, model=model_name or None)
                    raw = (llm_response.content or "").strip()
                except Exception as exc:
                    logger.warning("Primary LLM provider chat failed: %s. Trying fallback provider.", exc)
                    try:
                        fallback_provider_name = self.config.ai.default_provider
                        if fallback_provider_name != provider_name:
                            fallback_prov = self.router.get(fallback_provider_name)
                            fallback_model = self.config.ai.providers[fallback_provider_name].model or ""
                            logger.info("Using fallback provider=%s model=%s", fallback_provider_name, fallback_model)
                            llm_response = fallback_prov.chat(messages, model=fallback_model or None)
                            raw = (llm_response.content or "").strip()
                        else:
                            raise
                    except Exception as fallback_exc:
                        logger.error("Fallback LLM provider chat failed: %s", fallback_exc)
                        raw = ""

                content = clean_response_scaffold(raw)
                if (not content or looks_like_tool_json(raw)) and self.config.git.enabled:
                    inv = self._playbooks.get_by_name("investigate_bug")
                    if inv and inv.allowed_tools:
                        set_call_kind("investigation")
                        inv_name, inv_provider, inv_model = self._resolve_llm("investigation")
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
                if response is None and self.config.jira.enabled and (
                    not content or _looks_like_missing_tools_reply(raw)
                ):
                    from backend.routing.jira_intent import (
                        looks_like_jira_create_followup,
                        looks_like_jira_create_request,
                    )

                    if looks_like_jira_create_request(task.cleaned_intent) or looks_like_jira_create_followup(
                        task.cleaned_intent,
                        session_turns=route_context.session_turns,
                        thread_context=route_context.thread_context,
                    ):
                        inv = self._playbooks.get_by_name("jira_management")
                        if inv and inv.allowed_tools:
                            set_call_kind("investigation")
                            inv_name, inv_provider, inv_model = self._resolve_llm("investigation")
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

                if response is None:
                    if not content:
                        response = AssistantResponse.from_text(
                            "I couldn't generate a reply — the model returned an empty response. "
                            "For Kimi K2.6, try again or check Admin → AI; large Slack summaries "
                            "may need a playbook for ticket formatting."
                        )
                    else:
                        response = AssistantResponse.from_text(content)

        if session_key and self.session_store:
            raise_if_cancelled(self._data_dir_path(), task.id)
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

    def _resolve_llm(self, task_kind: str) -> tuple[str, Any, str]:
        from backend.ai.routing import resolve_llm_route

        return resolve_llm_route(self.config.ai, task_kind, router=self.router)

    def _is_confirmation_only(self, text: str) -> bool:
        from backend.governance.confirmation import is_confirmation_only

        return is_confirmation_only(text, self.config.governance)

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

    def _try_workflow_entry(
        self,
        skill: Playbook | None,
        task: Task,
        *,
        session: ConversationSession | None,
        slack_context: str | None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Gate create-PR / plan commands; ask clarifying questions or run plan-only flow."""
        if skill is None:
            return None, None

        from backend.orchestrator.workflow_gates import gate_create_pr, gate_plan_task
        from backend.orchestrator.planning import generate_standalone_plan

        if skill.name == "create_pr":
            gate = gate_create_pr(
                task,
                self.config,
                session=session,
                slack_context=slack_context,
            )
            if not gate.ready:
                return AssistantResponse.from_text(gate.message), gate.metadata_patch or None
            if gate.enriched_intent:
                task.cleaned_intent = gate.enriched_intent
            from backend.orchestrator.planning import adopt_session_plan_for_task

            patch = dict(gate.metadata_patch or {})
            adopted = adopt_session_plan_for_task(task, session, self._data_dir_path())
            if adopted:
                patch["plan_file"] = adopted
            return None, patch or None

        if skill.name == "plan_task":
            gate = gate_plan_task(
                task,
                self.config,
                session=session,
                slack_context=slack_context,
            )
            if not gate.ready:
                return AssistantResponse.from_text(gate.message), gate.metadata_patch or None
            if gate.enriched_intent:
                task.cleaned_intent = gate.enriched_intent
            context_parts = [slack_context or ""]
            if session and session.context_snapshot and session.context_snapshot not in context_parts:
                context_parts.append(session.context_snapshot)
            plan_text, plan_path = generate_standalone_plan(
                task,
                self.config,
                context="\n\n".join(p for p in context_parts if p).strip(),
                data_dir=self._data_dir,
                task_kind="workflow_execution",
            )
            if not plan_text:
                return (
                    AssistantResponse.from_text(
                        "I couldn't generate a plan — check Admin → AI (Workflow execution provider) and try again."
                    ),
                    gate.metadata_patch,
                )
            path_note = f"\n\n_Saved to `{plan_path}`_" if plan_path else ""
            body = f"*Task plan*\n\n{plan_text}{path_note}"
            patch = dict(gate.metadata_patch or {})
            if plan_path:
                patch["plan_file"] = plan_path
            return AssistantResponse.from_text(body), patch

        return None, None

    def _build_route_context(
        self,
        task: Task,
        *,
        session: ConversationSession | None,
        slack_context: str | None,
        repo: str,
    ):
        from backend.routing import RouteContext

        session_turns: tuple[str, ...] = ()
        if session and session.turns:
            session_turns = tuple(
                turn.content for turn in session.turns[-4:] if (turn.content or "").strip()
            )
        return RouteContext(
            intent=task.cleaned_intent,
            channel_id=task.channel_id,
            repo=repo,
            thread_context=slack_context,
            session_turns=session_turns,
        )

    def _resolve_pr_review_skill(
        self,
        investigation: Playbook | None,
        task: Task,
        session: ConversationSession | None,
    ) -> Playbook | None:
        """Return the review_pr skill when intent is a PR review or thread follow-up."""
        from backend.routing.git_direct import should_run_pr_analysis

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
        from backend.routing.git_direct import resolve_pr_for_analysis
        from backend.integrations.git.pr_analysis import format_pr_context_for_prompt, gather_pr_context

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

    def _try_unified_direct(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None = None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Try running direct actions unified under a single router entry point."""
        from backend.routing.intent import detect_direct_action
        from backend.tools.git_api import build_git_tool_registry

        direct = detect_direct_action(
            task.cleaned_intent,
            self.config,
            task,
            session=session,
            playbook=skill,
            data_dir=self._data_dir_path(),
        )
        if not direct:
            return None, None

        tool_name, tool_args = direct
        if skill.allowed_tools and tool_name not in skill.allowed_tools:
            logger.info("Direct tool %s detected but not in allowed_tools for %s", tool_name, skill.name)
            return None, None

        logger.info("Unified direct execution: running tool %s", tool_name)

        # 1. Custom built-in direct handlers
        if tool_name == "lookup_user_identity":
            from backend.integrations.identity.user_identity import format_user_identity_result, lookup_user_identity

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
            from backend.integrations.identity.user_identity import (
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

        # 2. Standard registry-driven tools (JIRA/Git/AWS)
        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=skill.allowed_tools or None,
        )
        self._attach_governance(registry, task, session=session, skill_name=skill.name)

        result = registry.run_normalized(
            tool_name,
            tool_args,
            allowed=skill.allowed_tools,
            git=self.config.git,
            session=session,
        )
        if result.kind == "error":
            return AssistantResponse.error(result.data.get("message", f"Tool {tool_name} failed.")), None

        patch = _unified_metadata_patch(tool_name, tool_args, result)

        from backend.routing.git_direct import wants_pr_summary, wants_pr_code_analysis

        if tool_name == "get_pr" and wants_pr_summary(task.cleaned_intent):
            detail = result.data.get("pr")
            if detail and not wants_pr_code_analysis(task.cleaned_intent):
                from backend.integrations.git.pr_analysis import format_pr_context_for_prompt
                summary = format_pr_context_for_prompt(detail)
                return AssistantResponse.from_text(summary), patch

        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, patch
        return None, patch

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
        from backend.routing.git_direct import looks_like_tool_json, strip_text_tool_markup
        from backend.routing.git_context import metadata_patch_for_tool_result
        from backend.tools.git_api import build_git_tool_registry
        from backend.observability.checkpoint import log_checkpoint

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=skill.allowed_tools or None,
        )
        self._attach_governance(registry, task, session=session, skill_name=skill.name)

        runner = self.config.orchestrator.agent_runner
        log_checkpoint("agent_loop_start", runner, "started")

        allowed_tools = skill.allowed_tools
        if not allowed_tools:
            allowed_tools = list(registry._tools.keys())

        if skill.mode in ("investigation", "workflow") and skill.name != "plan_task":
            from backend.orchestrator.planning import generate_initial_plan, plan_exists_for_task

            if not plan_exists_for_task(task.id, self._data_dir_path()):
                generate_initial_plan(task, allowed_tools, self.config, data_dir=self._data_dir)

        try:
            if runner == "hermes":
                from backend.orchestrator.hermes_runner import run_hermes_loop
                raw = run_hermes_loop(
                    provider,
                    messages,
                    registry,
                    allowed_tools,
                    model=model or None,
                    session=session,
                    git=self.config.git,
                )
            else:
                raw = run_agent_loop(
                    provider,
                    messages,
                    registry,
                    allowed_tools,
                    model=model or None,
                    session=session,
                    git=self.config.git,
                )
        except TaskCancelledError:
            raise
        except Exception as exc:
            logger.exception("Investigation loop failed")
            return self._investigation_failure_response(skill, allowed_tools, exc), None

        patch = None
        if registry.last_result and registry.last_tool_name:
            patch = _unified_metadata_patch(
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
                    return AssistantResponse.from_text(prose), patch
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
        system_parts = [build_alfred_system_prompt(self.config, model_name=model_name)]
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

        messages.append(Message(role="user", content=user_content))
        return messages


_MISSING_TOOLS_REPLY_MARKERS = (
    "don't currently have jira",
    "do not currently have jira",
    "don't have jira",
    "no jira ticket creation",
    "jira tools are not available",
    "jira tools aren't available",
    "only have athena",
)


def _looks_like_missing_tools_reply(raw: str) -> bool:
    lower = (raw or "").lower()
    return any(marker in lower for marker in _MISSING_TOOLS_REPLY_MARKERS)


def _tool_result_to_response(result: ToolResult) -> AssistantResponse | None:
    if result.kind == "user_identity":
        from backend.integrations.identity.user_identity import format_user_identity_result

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
    from backend.integrations.slack.sanitize import clean_slack_text

    return clean_slack_text(text)


def _unified_metadata_patch(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
) -> dict[str, Any] | None:
    if result.kind == "error":
        return None

    # JIRA tools patch
    jira_patch = {}
    issue = result.data.get("issue") or result.data
    key = args.get("issue_key") or args.get("key") or (isinstance(issue, dict) and issue.get("key"))
    if key and (tool_name.startswith("jira") or tool_name in ("get_jira_issue", "create_jira_issue", "transition_jira_issue", "comment_jira_issue", "add_jira_comment")):
        jira_patch["active_jira_ticket"] = str(key)

    # Git tools patch
    from backend.routing.git_context import metadata_patch_for_tool_result
    git_patch = metadata_patch_for_tool_result(tool_name, args, result) or {}

    return {**jira_patch, **git_patch}
