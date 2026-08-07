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
        "doc_search",
        "doc_content",
        "doc_answer",
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

        if task.source == "slack":
            from backend.routing.slack_board_admin import try_slack_board_admin_command

            admin_response = try_slack_board_admin_command(
                task,
                self.config,
                self._data_dir_path(),
            )
            if admin_response is not None:
                if session_key and self.session_store:
                    rendered = render_for_channel(admin_response, channel)
                    self.session_store.append_exchange(
                        session_key,
                        source=task.source,
                        scope_id=task.channel_id,
                        thread_id=task.thread_ts or "",
                        user_content=task.cleaned_intent,
                        assistant_content=rendered,
                        assistant_payload=admin_response.payload,
                    )
                return self._finish_response(admin_response)

        if task.source == "slack":
            from backend.routing.slack_board_direct import (
                try_slack_board_create_direct,
                try_slack_board_status_followup,
                try_slack_board_update_direct,
                try_slack_board_where_direct,
            )

            session_turns: tuple[str, ...] = ()
            if session and session.turns:
                session_turns = tuple(
                    turn.content for turn in session.turns[-4:] if (turn.content or "").strip()
                )

            followup_response = try_slack_board_where_direct(
                task,
                self.config,
                self._data_dir_path(),
                session=session,
            )
            if followup_response is not None:
                if session_key and self.session_store:
                    rendered = render_for_channel(followup_response, channel)
                    self.session_store.append_exchange(
                        session_key,
                        source=task.source,
                        scope_id=task.channel_id,
                        thread_id=task.thread_ts or "",
                        user_content=task.cleaned_intent,
                        assistant_content=rendered,
                        assistant_payload=followup_response.payload,
                    )
                return self._finish_response(followup_response)

            followup_response = try_slack_board_status_followup(
                task,
                self.config,
                self._data_dir_path(),
                session=session,
                session_turns=session_turns,
            )
            if followup_response is not None:
                if session_key and self.session_store:
                    rendered = render_for_channel(followup_response, channel)
                    self.session_store.append_exchange(
                        session_key,
                        source=task.source,
                        scope_id=task.channel_id,
                        thread_id=task.thread_ts or "",
                        user_content=task.cleaned_intent,
                        assistant_content=rendered,
                        assistant_payload=followup_response.payload,
                    )
                return self._finish_response(followup_response)

            create_response, board_meta = try_slack_board_create_direct(
                task,
                self.config,
                self._data_dir_path(),
            )
            if create_response is not None:
                if board_meta and session:
                    session.metadata.update(board_meta)
                    if session_key and self.session_store:
                        self.session_store.save(session)
                if session_key and self.session_store:
                    rendered = render_for_channel(create_response, channel)
                    self.session_store.append_exchange(
                        session_key,
                        source=task.source,
                        scope_id=task.channel_id,
                        thread_id=task.thread_ts or "",
                        user_content=task.cleaned_intent,
                        assistant_content=rendered,
                        assistant_payload=create_response.payload,
                        metadata_patch=board_meta or None,
                    )
                return self._finish_response(create_response, metadata_patch=board_meta or None)

            update_response, update_meta = try_slack_board_update_direct(
                task,
                self.config,
                self._data_dir_path(),
                session=session,
            )
            if update_response is not None:
                if update_meta and session:
                    session.metadata.update(update_meta)
                    if session_key and self.session_store:
                        self.session_store.save(session)
                if session_key and self.session_store:
                    rendered = render_for_channel(update_response, channel)
                    self.session_store.append_exchange(
                        session_key,
                        source=task.source,
                        scope_id=task.channel_id,
                        thread_id=task.thread_ts or "",
                        user_content=task.cleaned_intent,
                        assistant_content=rendered,
                        assistant_payload=update_response.payload,
                        metadata_patch=update_meta or None,
                    )
                return self._finish_response(update_response, metadata_patch=update_meta or None)

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
            return self._finish_response(response, metadata_patch=gov_patch)

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

        from backend.routing.ticket_create_disambiguation import (
            apply_ticket_create_target,
            build_disambiguation_response,
            needs_ticket_create_disambiguation,
            resolve_target_from_pending_reply,
            store_pending_ticket_create,
            ticket_create_target_from_task,
        )

        ticket_target = ticket_create_target_from_task(task)
        if ticket_target is None and session:
            reply_target = resolve_target_from_pending_reply(task, session)
            if reply_target:
                apply_ticket_create_target(session, reply_target)
                task.metadata["ticket_create_target"] = reply_target
                ticket_target = reply_target
                if session_key and self.session_store:
                    self.session_store.save(session)

        if ticket_target is None:
            from backend.routing.ticket_create_disambiguation import default_ticket_create_target

            policy_target = default_ticket_create_target(
                task,
                self.config,
                data_dir=self._data_dir_path(),
            )
            if policy_target:
                task.metadata["ticket_create_target"] = policy_target
                ticket_target = policy_target

        if (
            ticket_target is None
            and needs_ticket_create_disambiguation(
                task,
                self.config,
                session=session,
                data_dir=self._data_dir_path(),
            )
        ):
            if session and session_key and self.session_store:
                store_pending_ticket_create(session, task)
                self.session_store.save(session)
            response = build_disambiguation_response(session_key=session_key or "")
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
                )
            return self._finish_response(response)

        chat_persona = None
        if task.source == "ui":
            from backend.routing.chat_persona import persona_skill_name, resolve_effective_persona

            chat_persona = resolve_effective_persona(task, session)
            task.metadata["chat_persona_effective"] = chat_persona

        investigation = self._resolve_investigation_skill(route_context, task, session=session)
        if investigation is None and chat_persona:
            forced = persona_skill_name(chat_persona)
            if forced:
                investigation = self._playbooks.get_by_name(forced)
                if investigation:
                    logger.info("Persona %s → skill %s", chat_persona, forced)

        legacy_routing = self.config.routing.planner_strategy == "rules_first"
        if investigation is None and ticket_target != "jira":
            from backend.integrations.slack.board_service import board_enabled, resolve_board_for_task
            from backend.routing.slack_board_intent import (
                looks_like_slack_board_config_question,
                looks_like_slack_board_followup,
                looks_like_slack_board_request,
            )

            board_ready = resolve_board_for_task(
                self.config, task, data_dir=self._data_dir_path()
            )
            config_question = looks_like_slack_board_config_question(task.cleaned_intent)
            followup = looks_like_slack_board_followup(
                task.cleaned_intent,
                session_turns=route_context.session_turns,
                thread_context=route_context.thread_context,
            )
            if followup or (
                looks_like_slack_board_request(task.cleaned_intent)
                and (
                    config_question
                    or board_ready
                    or (
                        legacy_routing
                        and board_enabled(self.config, self._data_dir_path())
                        and board_ready
                    )
                )
            ):
                investigation = self._playbooks.get_by_name("slack_board_management")
                if investigation:
                    logger.info("Using slack_board_management for board intent or follow-up")

        if investigation is None and legacy_routing and self.config.repo_knowledge.enabled:
            from backend.routing.tool_planner import looks_like_repo_doc_question

            if looks_like_repo_doc_question(task.cleaned_intent, source=task.source):
                investigation = self._playbooks.get_by_name("repo_knowledge")
                if investigation:
                    logger.info(
                        "Forced repo_knowledge for documentation-style question (routing miss)"
                    )
        if investigation is None and ticket_target == "slack_list":
            investigation = self._playbooks.get_by_name("slack_board_management")
            if investigation:
                logger.info("Using slack_board_management from ticket_create_target")
        if investigation is None and ticket_target == "jira":
            investigation = self._playbooks.get_by_name("jira_management")
            if investigation:
                logger.info("Using jira_management from ticket_create_target")

        if (
            investigation is None
            and legacy_routing
            and ticket_target != "slack_list"
            and self.config.jira.enabled
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
            return self._finish_response(workflow_response, metadata_patch=workflow_meta)

        review_skill = self._resolve_pr_review_skill(investigation, task, session)
        omit_assistant = omit_assistant_session_history(
            task.cleaned_intent,
            include_context=include_context,
            pr_review_active=bool(review_skill),
        )
        active_skill = review_skill or investigation
        set_skill_name(active_skill.name if active_skill else None)

        tool_plan = None
        scoped_binding = None
        if active_skill and active_skill.mode in ("investigation", "workflow"):
            scoped_binding = self._resolve_scoped_tools(
                task,
                route_context,
                active_skill,
                session=session,
                persona=chat_persona,
            )
            if scoped_binding and scoped_binding.plan:
                tool_plan = scoped_binding.plan
                logger.info(
                    "Tool plan: strategy=%s confidence=%.2f tools=%s goal=%s",
                    tool_plan.strategy,
                    tool_plan.confidence,
                    scoped_binding.allowed_tools,
                    tool_plan.goal[:80],
                )

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
            rk = self.config.repo_knowledge
            if rk.enabled and not rk.inject_overview:
                repo_context_prompt = (
                    "## Repository documentation\n"
                    "Use `search_repo_docs` and `read_repo_doc` for runbook and documentation questions."
                )
            else:
                from backend.context.generator import load_repo_context_for_prompt

                repo_context_prompt = load_repo_context_for_prompt(
                    self._data_dir_path(),
                    self.config.git,
                )

        from backend.routing.context_scope import build_context_envelope, format_context_envelope

        context_envelope = build_context_envelope(
            self.config,
            task,
            tool_plan=tool_plan,
            slack_context=slack_context if include_context else None,
            jira_context=jira_context_prompt,
            google_context=google_context_prompt,
            git_context=git_context_prompt,
            repo_context=repo_context_prompt,
            pr_context=pr_context_prompt,
        )
        scoped_context = format_context_envelope(context_envelope)

        tool_manifest = scoped_binding.manifest_text if scoped_binding else ""

        goal_spec_block = ""
        subagent_block = ""
        goal_spec = None
        if tool_plan:
            from backend.routing.goal_spec import goal_spec_from_plan
            from backend.agent.subagents import (
                build_subagent_manifest,
                group_steps_by_domain,
                should_use_subagents,
            )

            goal_spec = goal_spec_from_plan(tool_plan)
            if goal_spec:
                criteria = "\n".join(f"- {c}" for c in goal_spec.success_criteria)
                goal_spec_block = (
                    f"## GoalSpec\n"
                    f"Intent: `{goal_spec.intent_class}`\n"
                    f"Goal: {goal_spec.goal}\n"
                    f"Success criteria:\n{criteria}"
                )
            if should_use_subagents(tool_plan):
                subagent_block = "\n\n".join(
                    build_subagent_manifest(domain, steps)
                    for domain, steps in group_steps_by_domain(tool_plan.steps or [])
                )

        extra_system = "\n\n".join(
            part
            for part in (
                scoped_context,
                tool_manifest,
                goal_spec_block,
                subagent_block,
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
                scoped_tools=scoped_binding.allowed_tools if scoped_binding else None,
                goal_spec=goal_spec,
                route_context=route_context,
                manifest_text=scoped_binding.manifest_text if scoped_binding else "",
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
                    scoped_tools=scoped_binding.allowed_tools if scoped_binding else None,
                    goal_spec=goal_spec,
                    route_context=route_context,
                    manifest_text=scoped_binding.manifest_text if scoped_binding else "",
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
                            scoped_tools=scoped_binding.allowed_tools if scoped_binding else None,
                            goal_spec=goal_spec,
                            route_context=route_context,
                            manifest_text=scoped_binding.manifest_text if scoped_binding else "",
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
                                scoped_tools=scoped_binding.allowed_tools if scoped_binding else None,
                                goal_spec=goal_spec,
                                route_context=route_context,
                                manifest_text=scoped_binding.manifest_text if scoped_binding else "",
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

        response = self._finish_response(
            response,
            tool_plan=tool_plan,
            skill=active_skill,
            metadata_patch=metadata_patch,
        )

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

    def _resolve_investigation_skill(self, route_context: Any, task: Task, *, session=None):
        """Plan-first skill resolution; fall back to SkillRouter when needed."""
        from backend.observability.context import set_call_kind
        from backend.orchestrator.graph.skill_policy import resolve_policy_skill
        from backend.routing.chat_persona import normalize_persona, resolve_effective_persona
        from backend.routing.tool_planner import planner_llm_enabled, resolve_tool_plan

        persona = resolve_effective_persona(task, session) if task.source == "ui" else "all"
        if normalize_persona(persona) == "support":
            skill = self._playbooks.get_by_name("repo_knowledge")
            if skill is not None:
                return skill

        routing = self.config.routing
        if routing.plan_first_routing and routing.tool_planner_enabled:
            data_dir = self._data_dir_path()
            planner_provider = None
            planner_model = None
            if planner_llm_enabled(self.config):
                set_call_kind("skill_matching")
                _, planner_provider, planner_model = self._resolve_llm("skill_matching")
            plan = resolve_tool_plan(
                self.config,
                task,
                route_context,
                provider=planner_provider,
                model=planner_model or None,
                skill_allowed=None,
                data_dir=data_dir,
                playbook_store=self._playbooks,
            )
            if plan and plan.confidence >= routing.tool_planner_min_confidence:
                skill = resolve_policy_skill(
                    plan,
                    self._playbooks,
                    fallback=None,
                    data_dir=data_dir,
                )
                if skill is not None:
                    logger.info(
                        "Plan-first skill: %s intent=%s confidence=%.2f",
                        skill.name,
                        plan.intent_class,
                        plan.confidence,
                    )
                    return skill

        if not routing.skill_router_fallback:
            return None

        return self._skill_router.route_investigation(route_context).playbook

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
        if not skill.allowed_tools or tool_name not in skill.allowed_tools:
            from backend.routing.git_direct import wants_pr_code_analysis, wants_pr_summary

            if (
                tool_name == "get_pr"
                and wants_pr_summary(task.cleaned_intent)
                and not wants_pr_code_analysis(task.cleaned_intent)
            ):
                git_skill = self._playbooks.get_by_name("git_status")
                if git_skill and git_skill.name != skill.name:
                    return self._try_unified_direct(git_skill, task, session)
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
                summary = self._summarize_pr(detail, task)
                if not summary:
                    from backend.formatting.strategies import format_pr_detail

                    summary = format_pr_detail({"pr": detail}, slack=task.source == "slack")
                return AssistantResponse.from_text(summary), patch

        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, patch
        return None, patch

    def _execute_planned_direct(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None,
        plan: Any,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Run a single-step tool plan without the ReAct loop (fast path)."""
        from backend.routing.tool_plan_types import ToolPlan

        if not isinstance(plan, ToolPlan) or len(plan.steps) != 1:
            return None, None

        step = plan.steps[0]
        tool_name = step.tool
        tool_args = dict(step.args_hint or {})

        if plan.intent_class == "repo.docs.qa" and tool_name == "search_repo_docs":
            # Doc Q&A uses LangGraph worker (search → read → grounded answer), not the BM25 fast path.
            return None, None

        if not skill.allowed_tools or tool_name not in skill.allowed_tools:
            return None, None

        from backend.tools.git_api import build_git_tool_registry

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
        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, patch
        text = str(result.data.get("text") or "").strip()
        if text:
            return AssistantResponse.from_text(text), patch
        return None, patch

    def _execute_repo_doc_qa_direct(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None,
        query: str,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Search indexed docs, read the top hit, and synthesize a grounded answer."""
        from backend.formatting.intent_formatters import format_doc_search
        from backend.observability.checkpoint import log_checkpoint
        from backend.routing.reply_meta import attach_reply_meta, doc_reply_meta
        from backend.tools.git_api import build_git_tool_registry

        allowed = list(skill.allowed_tools or [])
        if "search_repo_docs" not in allowed:
            repo_skill = self._playbooks.get_by_name("repo_knowledge")
            if repo_skill and repo_skill.allowed_tools:
                allowed = list(repo_skill.allowed_tools)
                skill = repo_skill

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=allowed or None,
        )
        self._attach_governance(registry, task, session=session, skill_name=skill.name)

        log_checkpoint("doc_tool_call", "search_repo_docs", "started")
        search_result = registry.run_normalized(
            "search_repo_docs",
            {"query": query},
            allowed=allowed,
            git=self.config.git,
            session=session,
        )
        if search_result.kind == "error":
            log_checkpoint("doc_tool_call", "search_repo_docs", "error", error=RuntimeError(str(search_result.data.get("message") or "Doc search failed.")))
            return AssistantResponse.error(str(search_result.data.get("message") or "Doc search failed.")), None

        if not search_result.data.get("found"):
            log_checkpoint("doc_tool_call", "search_repo_docs", "completed")
            from backend.context.doc_index import describe_missing_doc_topic, significant_query_tokens
            from backend.routing.chat_persona import normalize_persona

            if significant_query_tokens(query):
                topic = describe_missing_doc_topic(query)
                body = (
                    f"**No** — **{topic}** is not documented in indexed FlexyPe support docs. "
                    "It does not appear to be a supported integration in our handbook."
                )
                meta = doc_reply_meta(query, None, not_found=True)
                return (
                    attach_reply_meta(AssistantResponse.from_text(body), meta),
                    {"last_intent_class": "repo.docs.qa", "reply_meta": meta},
                )

            persona = str(task.metadata.get("chat_persona_effective") or task.metadata.get("chat_persona") or "")
            if normalize_persona(persona) == "support" and self.config.web_search.enabled and "web_search" in allowed:
                log_checkpoint("doc_tool_call", "web_search", "started")
                web_result = registry.run_normalized(
                    "web_search",
                    {"query": query},
                    allowed=allowed,
                    git=self.config.git,
                    session=session,
                )
                if web_result.kind != "error" and web_result.data.get("results"):
                    log_checkpoint("doc_tool_call", "web_search", "completed")
                    from backend.formatting.strategies import WebSearchFormatter

                    body = WebSearchFormatter().render(web_result.data, slack=False)
                    prefix = (
                        "I couldn't find this in indexed FlexyPe documentation. "
                        "Here's what I found on the web instead:\n\n"
                    )
                    meta = doc_reply_meta(query, None, web_fallback=True)
                    return (
                        attach_reply_meta(AssistantResponse.from_text(prefix + body), meta),
                        {"reply_meta": meta},
                    )
                log_checkpoint("doc_tool_call", "web_search", "completed")
            return (
                AssistantResponse.structured(
                    "doc_search",
                    {"query": query, "results": [], "found": False},
                ),
                None,
            )

        log_checkpoint("doc_tool_call", "search_repo_docs", "completed")
        hits = list(search_result.data.get("results") or [])
        from backend.context.doc_index import describe_missing_doc_topic, pick_best_doc_hit, significant_query_tokens

        top = pick_best_doc_hit(hits, query)
        if top is None:
            if hits and significant_query_tokens(query):
                topic = describe_missing_doc_topic(query)
                body = (
                    f"**No** — **{topic}** is not documented in indexed FlexyPe support docs. "
                    "It does not appear to be a supported integration in our handbook."
                )
                meta = doc_reply_meta(query, None, not_found=True)
                return (
                    attach_reply_meta(AssistantResponse.from_text(body), meta),
                    {"last_intent_class": "repo.docs.qa", "reply_meta": meta},
                )
            return (
                AssistantResponse.structured(
                    "doc_search",
                    {"query": query, "results": [], "found": False},
                ),
                None,
            )
        doc_path = str(top.get("path") or "")
        doc_repo = str(top.get("repo") or "").strip()
        if doc_path:
            log_checkpoint("doc_found", doc_path, "completed")
        if doc_repo:
            log_checkpoint("repo_context", doc_repo, "completed")
        read_args: dict[str, Any] = {"path": doc_path}
        if doc_repo:
            read_args["repo"] = doc_repo

        doc_content = str(top.get("excerpt") or "")
        if "read_repo_doc" in allowed and doc_path:
            log_checkpoint("doc_tool_call", "read_repo_doc", "started")
            read_result = registry.run_normalized(
                "read_repo_doc",
                read_args,
                allowed=allowed,
                git=self.config.git,
                session=session,
            )
            if read_result.kind != "error":
                doc_content = str(read_result.data.get("content") or doc_content)
                log_checkpoint("doc_tool_call", "read_repo_doc", "completed")
            else:
                log_checkpoint(
                    "doc_tool_call",
                    "read_repo_doc",
                    "error",
                    error=RuntimeError(str(read_result.data.get("message") or "Read failed.")),
                )

        log_checkpoint("doc_synthesis", "summarize", "started")
        answer = self._synthesize_doc_answer(
            task.cleaned_intent,
            doc_path=doc_path,
            doc_content=doc_content,
            repo=doc_repo,
        )
        log_checkpoint("doc_synthesis", "summarize", "completed")
        from backend.context.doc_assets import build_doc_answer_payload

        meta = doc_reply_meta(query, top)
        payload = build_doc_answer_payload(
            text=answer,
            doc_path=doc_path,
            repo=doc_repo,
            doc_content=doc_content,
        )
        response = AssistantResponse.structured("doc_answer", payload, text=str(payload.get("text") or answer))
        return (
            attach_reply_meta(response, meta),
            {
                "last_intent_class": "repo.docs.qa",
                "doc_path": doc_path,
                "doc_repo": doc_repo,
                "reply_meta": meta,
            },
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

    def _resolve_scoped_tools(
        self,
        task: Task,
        route_context: Any,
        skill: Playbook,
        *,
        session: ConversationSession | None = None,
        persona: str | None = None,
    ):
        from backend.observability.context import set_call_kind
        from backend.routing.chat_persona import filter_tools_for_persona, resolve_effective_persona
        from backend.routing.tool_plan_validator import validate_tool_plan
        from backend.routing.tool_planner import planner_llm_enabled, resolve_tool_plan
        from backend.tools.git_api import build_git_tool_registry

        effective_persona = persona or (
            resolve_effective_persona(task, session) if task.source == "ui" else "all"
        )
        skill_allowed = list(skill.allowed_tools or [])
        if effective_persona in ("support", "tech"):
            skill_allowed = filter_tools_for_persona(effective_persona, skill_allowed)

        set_call_kind("skill_matching")
        _, provider, model = self._resolve_llm("skill_matching")

        plan = resolve_tool_plan(
            self.config,
            task,
            route_context,
            provider=provider if planner_llm_enabled(self.config) else None,
            model=model or None,
            skill_allowed=skill_allowed or None,
            data_dir=self._data_dir_path(),
            playbook_store=self._playbooks,
        )

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=skill_allowed or None,
        )
        binding = validate_tool_plan(
            plan,
            registry,
            skill_allowed=skill_allowed or None,
            skill_name=skill.name,
        )
        if effective_persona in ("support", "tech") and binding.allowed_tools:
            binding.allowed_tools = filter_tools_for_persona(
                effective_persona,
                binding.allowed_tools,
                registered=set(registry._tools.keys()),
            )
        return binding

    def _record_routing_trace(
        self,
        task: Task,
        *,
        skill: Any,
        tool_plan: Any | None = None,
        scoped_tools: list[str] | None = None,
        graph_final: dict[str, Any] | None = None,
        routing_strategy: str = "",
    ) -> None:
        from backend.orchestrator.graph.serialize import tool_plan_to_dict
        from backend.routing.trace_store import build_trace_record, record_trace

        plan_dict = tool_plan_to_dict(tool_plan) if tool_plan is not None else None
        if graph_final and graph_final.get("tool_plan"):
            plan_dict = graph_final.get("tool_plan")

        steps: list[dict[str, Any]] = []
        if graph_final:
            steps = [
                {"node": "extract_entities", "entities": graph_final.get("entities")},
                {"node": "plan_tools", "plan": graph_final.get("tool_plan")},
                {
                    "node": "execute",
                    "route": graph_final.get("route"),
                    "scoped_tools": graph_final.get("scoped_tools"),
                },
                {
                    "node": "ground",
                    "passed": graph_final.get("grounding_passed"),
                    "issues": graph_final.get("grounding_issues"),
                },
            ]

        strategy = routing_strategy
        if not strategy and plan_dict:
            strategy = str(plan_dict.get("strategy") or "")

        record_trace(
            self._data_dir_path(),
            build_trace_record(
                task_id=task.id,
                intent=task.cleaned_intent,
                skill_name=skill.name if skill else "",
                routing_strategy=strategy or "unknown",
                tool_plan=plan_dict,
                scoped_tools=scoped_tools or list(graph_final.get("scoped_tools") or []) if graph_final else [],
                graph_route=str(graph_final.get("route") or "") if graph_final else "",
                tool_trace=list(graph_final.get("tool_trace") or []) if graph_final else [],
                grounding_passed=bool(graph_final.get("grounding_passed", True)) if graph_final else True,
                grounding_issues=list(graph_final.get("grounding_issues") or []) if graph_final else [],
                steps=steps,
                source=task.source,
                channel_id=task.channel_id,
            ),
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
        scoped_tools: list[str] | None = None,
        goal_spec: Any | None = None,
        route_context: Any | None = None,
        manifest_text: str = "",
    ) -> tuple[AssistantResponse, dict[str, Any] | None]:
        if self.config.routing.langgraph_enabled and route_context is not None:
            from backend.orchestrator.graph.runner import run_investigation_graph

            return run_investigation_graph(
                self,
                skill,
                messages,
                provider=provider,
                model=model,
                task=task,
                session=session,
                route_context=route_context,
                scoped_tools=scoped_tools,
                goal_spec=goal_spec,
                manifest_text=manifest_text,
            )

        from backend.agent.loop import run_agent_loop
        from backend.routing.git_direct import looks_like_tool_json, strip_text_tool_markup
        from backend.routing.git_context import metadata_patch_for_tool_result
        from backend.tools.git_api import build_git_tool_registry
        from backend.observability.checkpoint import log_checkpoint

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=scoped_tools or skill.allowed_tools or None,
        )
        registry.clear_trace()
        registry.current_task = task
        self._attach_governance(registry, task, session=session, skill_name=skill.name)

        runner = self.config.orchestrator.agent_runner
        log_checkpoint("agent_loop_start", runner, "started")

        allowed_tools = scoped_tools or skill.allowed_tools
        if not allowed_tools:
            allowed_tools = list(registry._tools.keys())

        if goal_spec and goal_spec.intent_class == "repo.docs.qa" and messages and messages[0].role == "system":
            from backend.ai.base import Message
            from backend.routing.doc_qa_prompt import doc_qa_system_addendum

            messages[0] = Message(
                role="system",
                content=f"{messages[0].content.rstrip()}{doc_qa_system_addendum()}",
            )

        if goal_spec and goal_spec.intent_class == "repo.docs.qa":
            from backend.models.session import task_session_key
            from backend.routing.doc_qa_bootstrap import inject_doc_qa_bootstrap_message

            messages = inject_doc_qa_bootstrap_message(
                messages,
                registry,
                query=task.cleaned_intent,
                allowed=allowed_tools,
                session=session,
                git=self.config.git,
                task_id=task.id,
                session_key=task_session_key(task),
            )

        if goal_spec and goal_spec.intent_class == "slack.board.create":
            from backend.routing.slack_board_bootstrap import inject_slack_board_bootstrap_message
            from backend.routing.slack_board_prompt import slack_board_create_addendum
            from slack_sdk import WebClient

            if messages and messages[0].role == "system":
                messages[0] = Message(
                    role="system",
                    content=f"{messages[0].content.rstrip()}{slack_board_create_addendum()}",
                )
            token = (self.config.slack.bot_token or "").strip()
            if token:
                messages = inject_slack_board_bootstrap_message(
                    messages,
                    WebClient(token=token),
                    self.config,
                    task=task,
                    data_dir=self._data_dir_path(),
                )

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
            from backend.routing.grounding_gate import ToolTraceEntry, validate_agent_result

            trace = [
                ToolTraceEntry(
                    tool=str(item.get("tool") or ""),
                    success=bool(item.get("success")),
                    result_kind=str(item.get("result_kind") or ""),
                    observation=str(item.get("observation") or ""),
                )
                for item in registry.tool_trace
            ]
            if trace or goal_spec:
                validation = validate_agent_result(prose, trace, goal_spec)
                if not validation.passed:
                    logger.warning("Grounding gate rejected reply: %s", validation.issues)
                    return AssistantResponse.from_text(validation.fallback), patch
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
    if result.kind == "slack_messages":
        text = str(result.data.get("text") or "").strip()
        if text:
            return AssistantResponse.from_text(text)
        count = int(result.data.get("message_count") or 0)
        return AssistantResponse.from_text(f"Fetched {count} Slack message(s).")
    if result.kind == "slack_board_task":
        from backend.routing.slack_board_direct import (
            format_board_task_created,
            format_board_task_updated,
        )

        data = result.data or {}
        if data.get("updated"):
            return AssistantResponse.from_text(format_board_task_updated(data))
        return AssistantResponse.from_text(
            format_board_task_created(
                data,
                severity=str(data.get("severity") or ""),
                assignee_user_id=str(data.get("assignee_user_id") or ""),
            )
        )
    if result.kind == "slack_board_search":
        rows = list((result.data or {}).get("results") or [])
        if not rows:
            return AssistantResponse.from_text("No matching board tasks found.")
        lines = [f"Found **{len(rows)}** board task(s):"]
        for row in rows[:10]:
            if not isinstance(row, dict):
                continue
            display = row.get("display_id") or row.get("record_id") or "Task"
            title = row.get("title") or row.get("formatted") or ""
            status = row.get("status") or ""
            line = f"- **{display}**"
            if title:
                line += f" — {title}"
            if status:
                line += f" (`{status}`)"
            lines.append(line)
        return AssistantResponse.from_text("\n".join(lines))
    if result.kind == "slack_board_comment":
        return AssistantResponse.from_text("Posted comment on the board task thread.")
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
