"""Skill resolution, scoped tools, LangGraph/worker run."""

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
from backend.orchestrator.processor.helpers import (
    STRUCTURED_TOOL_KINDS,
    _tool_result_to_response,
    _unified_metadata_patch,
)

logger = logging.getLogger(__name__)


class InvestigationMixin:
    def _scheduled_job_skill(self, task: Task) -> Playbook | None:
        """Bind `run {skill_name}` from cron or chat (spaces or underscores)."""
        from backend.routing.plan_templates import strip_run_date_suffix

        intent = strip_run_date_suffix(task.cleaned_intent or "")
        if not intent.lower().startswith("run "):
            return None
        name = intent[4:].strip()
        if not name:
            return None
        found = self._playbooks.get_by_name(name)
        if found is None and " " in name:
            found = self._playbooks.get_by_name(name.replace(" ", "_"))
        return found

    def _plan_template_skill(self, route_context: Any) -> Playbook | None:
        """Match `.alfred/playbooks/` plan templates by trigger (cheap, no LLM)."""
        from backend.orchestrator.graph.skill_policy import resolve_policy_skill
        from backend.routing.plan_templates import match_plan_template

        plan = match_plan_template(
            route_context.intent,
            self._playbooks,
            channel_id=getattr(route_context, "channel_id", "") or "",
            repo=getattr(route_context, "repo", "") or "",
            min_confidence=self.config.routing.plan_template_min_confidence,
        )
        if plan is None:
            return None
        return resolve_policy_skill(
            plan,
            self._playbooks,
            fallback=None,
            data_dir=self._data_dir_path(),
        )

    def _apply_turn_plan_skill(self, investigation: Playbook | None, turn_plan: Any) -> Playbook | None:
        """Prefer classifier skill when JIRA vs Slack List would otherwise collide."""
        from backend.routing.classifier.intent_classes import is_html_slides_intent

        if turn_plan is None or turn_plan.confidence < 0.85 or not turn_plan.skill_name:
            return investigation
        planned = self._playbooks.get_by_name(turn_plan.skill_name)
        if planned is None:
            return investigation
        if turn_plan.prefers_jira:
            if investigation is None or investigation.name != planned.name:
                logger.info("TurnPlan prefers JIRA → skill %s", planned.name)
                return planned
            return investigation
        if is_html_slides_intent(turn_plan.intent_class):
            if investigation is None or investigation.name != planned.name:
                logger.info("TurnPlan HTML slides → skill %s", planned.name)
                return planned
        return investigation

    def _resolve_investigation_skill(self, route_context: Any, task: Task, *, session=None):
        """Plan-first skill resolution; fall back to SkillRouter when needed."""
        from backend.observability.context import set_call_kind
        from backend.orchestrator.graph.skill_policy import resolve_policy_skill
        from backend.routing.chat_persona import normalize_persona, resolve_effective_persona
        from backend.routing.html_slides_delivery import (
            looks_like_html_slides_followup,
            looks_like_html_slides_publish_continuation,
            looks_like_html_slides_request,
        )
        from backend.routing.tool_planner import planner_llm_enabled, resolve_tool_plan

        slide_text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
        if (
            looks_like_html_slides_request(slide_text)
            or looks_like_html_slides_followup(task, session)
            or looks_like_html_slides_publish_continuation(task, session)
        ):
            slides_skill = self._playbooks.get_by_name("html_slides")
            if slides_skill is not None:
                logger.info("HTML slides intent → skill html_slides")
                return slides_skill

        named = self._scheduled_job_skill(task)
        if named is not None:
            logger.info("Named run skill → %s (source=%s)", named.name, task.source)
            return named

        templated = self._plan_template_skill(route_context)
        if templated is not None:
            logger.info("Plan template → skill %s", templated.name)
            return templated

        if session:
            forced_skill = str(session.metadata.get("force_investigation_skill") or "").strip()
            if forced_skill == "slack_board_management":
                turn = task.metadata.get("turn_plan") or {}
                if str(turn.get("target_system") or "") == "jira" or str(
                    turn.get("intent_class") or ""
                ).startswith("jira."):
                    forced_skill = ""
            if forced_skill:
                skill = self._playbooks.get_by_name(forced_skill)
                if skill is not None:
                    logger.info("Forced investigation skill from board agent seed: %s", forced_skill)
                    return skill

        persona = resolve_effective_persona(task, session) if task.source == "ui" else "all"
        turn_meta = task.metadata.get("turn_plan") or {}
        turn_intent = str(turn_meta.get("intent_class") or "")
        turn_confidence = float(turn_meta.get("confidence") or 0)
        if (
            normalize_persona(persona) == "support"
            and turn_intent not in ("unknown", "conversational")
        ):
            if not (
                looks_like_html_slides_request(slide_text)
                or looks_like_html_slides_followup(task, session)
            ):
                skill = self._playbooks.get_by_name("repo_knowledge")
                if skill is not None:
                    return skill

        routing = self.config.routing
        turn_meta = task.metadata.get("turn_plan") or {}
        turn_intent = str(turn_meta.get("intent_class") or "")
        turn_confidence = float(turn_meta.get("confidence") or 0)
        if turn_intent in ("unknown", "conversational") and turn_confidence < 0.5:
            if not routing.skill_router_fallback:
                return None
            return self._skill_router.route_investigation(route_context).playbook

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
                session_metadata=dict(session.metadata if session else {}),
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
        from backend.tools.builder import build_git_tool_registry

        effective_persona = persona or (
            resolve_effective_persona(task, session) if task.source == "ui" else "all"
        )
        skill_allowed = list(skill.allowed_tools or [])
        if effective_persona in ("support", "tech"):
            skill_allowed = filter_tools_for_persona(effective_persona, skill_allowed)

        set_call_kind("skill_matching")
        _, provider, model = self._resolve_llm("skill_matching")

        from backend.routing.slack_board.agent import clear_board_agent_plan_seed, seeded_board_agent_plan

        plan = seeded_board_agent_plan(session)
        used_seed = plan is not None
        turn = task.metadata.get("turn_plan") or {}
        prefers_jira = str(turn.get("target_system") or "") == "jira" or str(
            turn.get("intent_class") or ""
        ).startswith("jira.")
        if used_seed and prefers_jira:
            plan = None
            used_seed = False
            clear_board_agent_plan_seed(session)
        if used_seed:
            logger.info(
                "Using seeded board agent plan intent=%s confidence=%.2f",
                plan.intent_class,
                plan.confidence,
            )
        else:
            plan = resolve_tool_plan(
                self.config,
                task,
                route_context,
                provider=provider if planner_llm_enabled(self.config) else None,
                model=model or None,
                skill_allowed=skill_allowed or None,
                data_dir=self._data_dir_path(),
                playbook_store=self._playbooks,
                session_metadata=dict(session.metadata if session else {}),
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
        if used_seed and session:
            clear_board_agent_plan_seed(session)
            seed_key = task_session_key(task)
            if seed_key and self.session_store:
                self.session_store.save(session)
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
        from backend.routing.git.direct import looks_like_tool_json, strip_text_tool_markup
        from backend.routing.git.context import metadata_patch_for_tool_result
        from backend.tools.builder import build_git_tool_registry
        from backend.observability.checkpoint import log_checkpoint

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=scoped_tools or skill.allowed_tools or None,
        )
        registry.clear_trace()
        registry.current_task = task
        registry.session_metadata = dict(session.metadata if session else {})
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

        if goal_spec and goal_spec.intent_class.startswith("slack.board."):
            from backend.routing.classifier.intent_classes import is_slack_board_create_intent
            from backend.routing.slack_board.bootstrap import inject_slack_board_bootstrap_message
            from backend.routing.slack_board.prompt import slack_board_agentic_addendum
            from slack_sdk import WebClient

            if messages and messages[0].role == "system":
                messages[0] = Message(
                    role="system",
                    content=(
                        f"{messages[0].content.rstrip()}"
                        f"{slack_board_agentic_addendum(intent_class=goal_spec.intent_class)}"
                    ),
                )
            token = (self.config.slack.bot_token or "").strip()
            if token and is_slack_board_create_intent(goal_spec.intent_class):
                messages = inject_slack_board_bootstrap_message(
                    messages,
                    WebClient(token=token),
                    self.config,
                    task=task,
                    data_dir=self._data_dir_path(),
                    auto_create=False,
                )

        if skill.name == "html_slides":
            from backend.ai.base import Message
            from backend.routing.html_slides_delivery import (
                html_slides_system_addendum,
                inject_html_slides_bootstrap_message,
            )

            if messages and messages[0].role == "system":
                messages[0] = Message(
                    role="system",
                    content=f"{messages[0].content.rstrip()}{html_slides_system_addendum(task, session=session, config=self.config, data_dir=self._data_dir_path())}",
                )
            messages = inject_html_slides_bootstrap_message(messages, task, session=session)

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

        if skill.name == "html_slides":
            from backend.routing.html_slides_delivery import (
                format_artifact_tool_reply,
                html_deck_session_metadata_patch,
                resolve_html_slides_reply,
                salvage_html_deck_from_prose,
            )

            public_base = (self.config.artifacts.public_base_url or "").strip()
            artifact_reply, _, artifact_patch = resolve_html_slides_reply(
                registry,
                task=task,
                public_base_url=public_base,
            )
            if artifact_reply:
                merged_patch = {**(patch or {}), **(artifact_patch or {})}
                return AssistantResponse.from_text(artifact_reply), merged_patch or None

            if prose:
                salvaged = salvage_html_deck_from_prose(
                    prose,
                    registry,
                    allowed_tools=allowed_tools,
                )
                if salvaged and salvaged.kind in ("html_deck_saved", "html_artifact_published"):
                    salvaged_reply = format_artifact_tool_reply(
                        salvaged,
                        task=task,
                        public_base_url=public_base,
                    )
                    salvaged_patch = (
                        html_deck_session_metadata_patch(salvaged.data)
                        if salvaged.kind == "html_deck_saved"
                        else {
                            "pending_publish": False,
                            "last_published_slug": str(salvaged.data.get("slug") or ""),
                            "last_published_url": str(
                                salvaged.data.get("share_url") or salvaged.data.get("slug_url") or ""
                            ),
                        }
                    )
                    return (
                        AssistantResponse.from_text(salvaged_reply),
                        {**(patch or {}), **salvaged_patch},
                    )

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


