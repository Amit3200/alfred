"""Turn owner — load session, route, execute, persist."""

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

from backend.orchestrator.processor.direct import DirectMixin
from backend.orchestrator.processor.helpers import (
    STRUCTURED_TOOL_KINDS,
    _looks_like_missing_tools_reply,
    _task_channel,
)
from backend.orchestrator.processor.investigation import InvestigationMixin
from backend.orchestrator.processor.reply import ReplyMixin
from backend.orchestrator.processor.session import SessionMixin


class TaskProcessor(SessionMixin, DirectMixin, InvestigationMixin, ReplyMixin):
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
            from backend.routing.slack_board.admin import try_slack_board_admin_command

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

        from backend.routing.resolver import resolve_turn

        turn_plan = resolve_turn(task, config=self.config, session=session)
        task.metadata["turn_plan"] = turn_plan.to_metadata()

        if task.source == "slack":
            from backend.routing.slack_board.direct import (
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

            followup_response = None
            if not turn_plan.prefers_jira:
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

            followup_response = None
            if not turn_plan.prefers_jira:
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
                session=session,
                session_turns=session_turns,
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

            update_response, update_meta = (None, {})
            if not turn_plan.prefers_jira:
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

            if self.config.routing.tool_planner_enabled and not turn_plan.prefers_jira:
                from backend.routing.slack_board.agent import seed_slack_board_agent_plan
                from backend.routing.tool_planner import planner_llm_enabled

                if planner_llm_enabled(self.config):
                    set_call_kind("skill_matching")
                    _, planner_provider, planner_model = self._resolve_llm("skill_matching")
                    llm_meta = seed_slack_board_agent_plan(
                        task,
                        self.config,
                        self._data_dir_path(),
                        session=session,
                        session_turns=session_turns,
                        provider=planner_provider,
                        model=planner_model,
                    )
                    if llm_meta and session:
                        session.metadata.update(llm_meta)
                        if session_key and self.session_store:
                            self.session_store.save(session)

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

        if slack_user_names:
            task.metadata["slack_user_names"] = slack_user_names

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
            from backend.routing.html_slides_delivery import (
                looks_like_html_slides_followup,
                looks_like_html_slides_publish_continuation,
                looks_like_html_slides_request,
            )

            slide_text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
            if (
                looks_like_html_slides_request(slide_text)
                or looks_like_html_slides_followup(task, session)
                or looks_like_html_slides_publish_continuation(task, session)
            ):
                investigation = self._playbooks.get_by_name("html_slides")
                if investigation:
                    logger.info("Persona override → html_slides for slide request")
            if investigation is None and not turn_plan.intent_class in ("unknown", "conversational"):
                forced = persona_skill_name(chat_persona)
                if forced:
                    investigation = self._playbooks.get_by_name(forced)
                    if investigation:
                        logger.info("Persona %s → skill %s", chat_persona, forced)

        legacy_routing = self.config.routing.planner_strategy == "rules_first"
        if investigation is None and ticket_target != "jira" and not turn_plan.prefers_jira:
            from backend.domains.slack_board.operations import board_enabled, resolve_board_for_task
            from backend.routing.slack_board.intent import (
                looks_like_slack_board_config_question,
                looks_like_slack_board_followup,
                looks_like_slack_board_request,
                looks_like_slack_board_update,
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
            board_update = looks_like_slack_board_update(task.cleaned_intent or "")
            if followup or board_update or (
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

        if (
            investigation is not None
            and investigation.name == "jira_management"
            and task.source == "slack"
            and not turn_plan.prefers_jira
        ):
            from backend.domains.slack_board.operations import resolve_board_for_task
            from backend.routing.slack_board.intent import looks_like_slack_board_update

            if (
                resolve_board_for_task(self.config, task, data_dir=self._data_dir_path())
                and looks_like_slack_board_update(task.cleaned_intent or "")
            ):
                slack_skill = self._playbooks.get_by_name("slack_board_management")
                if slack_skill:
                    investigation = slack_skill
                    logger.info(
                        "Preferring slack_board_management over jira for board update in linked channel"
                    )

        if investigation is None and legacy_routing and self.config.repo_knowledge.enabled:
            from backend.routing.tool_planner import looks_like_repo_doc_question

            if looks_like_repo_doc_question(task.cleaned_intent, source=task.source):
                investigation = self._playbooks.get_by_name("repo_knowledge")
                if investigation:
                    logger.info(
                        "Forced repo_knowledge for documentation-style question (routing miss)"
                    )
        if investigation is None and ticket_target == "slack_list" and not turn_plan.prefers_jira:
            investigation = self._playbooks.get_by_name("slack_board_management")
            if investigation:
                logger.info("Using slack_board_management from ticket_create_target")
        if investigation is None and ticket_target == "jira":
            from backend.domains.slack_board.operations import resolve_board_for_task
            from backend.routing.slack_board.intent import looks_like_slack_board_update

            if (
                not turn_plan.prefers_jira
                and resolve_board_for_task(self.config, task, data_dir=self._data_dir_path())
                and looks_like_slack_board_update(task.cleaned_intent or "")
            ):
                investigation = self._playbooks.get_by_name("slack_board_management")
                if investigation:
                    logger.info(
                        "Using slack_board_management instead of jira for board update in linked channel"
                    )
            else:
                investigation = self._playbooks.get_by_name("jira_management")
                if investigation:
                    logger.info("Using jira_management from ticket_create_target")

        investigation = self._apply_turn_plan_skill(investigation, turn_plan)

        if task.source == "scheduler" and investigation is not None:
            from backend.orchestrator.scheduled_job import run_scheduled_playbook

            scheduled = run_scheduled_playbook(self, investigation, task, session)
            if scheduled is not None:
                if session_key and self.session_store:
                    rendered = render_for_channel(scheduled, channel)
                    self.session_store.append_exchange(
                        session_key,
                        source=task.source,
                        scope_id=task.channel_id,
                        thread_id=task.thread_ts or "",
                        user_content=task.cleaned_intent,
                        assistant_content=rendered,
                        assistant_payload=scheduled.payload,
                    )
                return self._finish_response(scheduled)

        if (
            investigation is None
            and legacy_routing
            and ticket_target != "slack_list"
            and self.config.jira.enabled
        ):
            from backend.routing.jira.intent import (
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
        session_meta_patch: dict[str, Any] | None = None
        if active_skill and active_skill.name == "html_slides":
            from backend.routing.html_slides_delivery import publish_session_metadata_patch

            session_meta_patch = publish_session_metadata_patch(task)
            session_meta_patch.setdefault("last_skill_name", "html_slides")
            session_meta_patch.setdefault("last_intent_class", "html_slides")
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
            from backend.routing.git.context import format_session_git_context

            git_context_prompt = format_session_git_context(session, task.cleaned_intent)

        jira_context_prompt = ""
        if (
            active_skill
            and active_skill.name in ("jira_management", "jira_ticket")
            and self.config.jira.enabled
        ):
            from backend.routing.jira.context import format_jira_context_for_prompt

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
                from backend.routing.git.direct import looks_like_tool_json

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
                    from backend.routing.jira.intent import (
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

        from backend.routing.slack_board.pending import pending_board_creates_patch

        pending_patch = pending_board_creates_patch(session)
        finish_patch = {
            **(metadata_patch or {}),
            **(session_meta_patch or {}),
            **pending_patch,
        }
        response = self._finish_response(
            response,
            tool_plan=tool_plan,
            skill=active_skill,
            metadata_patch=finish_patch or None,
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
                metadata_patch=finish_patch or None,
            )
            logger.info("Session updated: %s", session_key)

        return response
    def _resolve_llm(self, task_kind: str) -> tuple[str, Any, str]:
        from backend.ai.routing import resolve_llm_route

        return resolve_llm_route(self.config.ai, task_kind, router=self.router)

    def _is_confirmation_only(self, text: str) -> bool:
        from backend.governance.confirmation import is_confirmation_only

        return is_confirmation_only(text, self.config.governance)


