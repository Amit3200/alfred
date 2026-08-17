"""LangGraph node implementations for Alfred task orchestration."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import RunnableConfig

from backend.ai.base import Message
from backend.agent.loop import run_agent_loop
from backend.agent.subagents import build_subagent_manifest, group_steps_by_domain, should_use_subagents
from backend.formatting.sanitize import clean_response_scaffold
from backend.orchestrator.graph.runtime import GraphRuntime, get_runtime
from backend.orchestrator.graph.serialize import (
    goal_spec_from_dict,
    goal_spec_to_dict,
    tool_plan_from_dict,
    tool_plan_to_dict,
)
from backend.orchestrator.graph.skill_policy import resolve_policy_skill
from backend.orchestrator.graph.state import AlfredGraphState
from backend.orchestrator.processor import STRUCTURED_TOOL_KINDS, _tool_result_to_response, _unified_metadata_patch
from backend.routing.entity_extractor import EntityBag, extract_entities
from backend.routing.git.direct import looks_like_tool_json, strip_text_tool_markup
from backend.routing.goal_spec import goal_spec_from_plan
from backend.routing.grounding_gate import ToolTraceEntry, validate_agent_result
from backend.routing.tool_plan_validator import validate_tool_plan
from backend.routing.tool_planner import planner_llm_enabled, resolve_tool_plan
from backend.models.response import AssistantResponse
from backend.observability.checkpoint import log_checkpoint

logger = logging.getLogger(__name__)


def _entities_to_dict(entities: EntityBag) -> dict[str, Any]:
    return {
        "issue_keys": list(entities.issue_keys),
        "spreadsheet_ids": list(entities.spreadsheet_ids),
        "document_ids": list(entities.document_ids),
        "slack_user_ids": list(entities.slack_user_ids),
        "github_prs": [list(pr) for pr in entities.github_prs],
    }


def extract_entities_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = get_runtime(config)
    ctx = runtime.route_context
    entities = extract_entities(
        runtime.task.cleaned_intent,
        runtime.task.raw_text,
        ctx.thread_context or "",
    )
    return {
        "task_id": runtime.task.id,
        "intent": runtime.task.cleaned_intent,
        "skill_name": runtime.skill.name,
        "entities": _entities_to_dict(entities),
    }


def plan_tools_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = get_runtime(config)
    processor = runtime.processor
    skill = runtime.active_skill

    from backend.routing.slack_board.agent import seeded_board_agent_plan

    plan = seeded_board_agent_plan(runtime.session)
    if plan is None:
        _, planner_provider, planner_model = processor._resolve_llm("skill_matching")
        plan = resolve_tool_plan(
            processor.config,
            runtime.task,
            runtime.route_context,
            provider=planner_provider if planner_llm_enabled(processor.config) else None,
            model=planner_model or None,
            skill_allowed=list(skill.allowed_tools or []),
            data_dir=processor._data_dir_path(),
            playbook_store=processor._playbooks,
            session_metadata=dict(getattr(runtime.session, "metadata", None) or {}),
        )
    else:
        logger.info(
            "LangGraph using seeded board agent plan intent=%s confidence=%.2f",
            plan.intent_class,
            plan.confidence,
        )

    policy_skill = resolve_policy_skill(
        plan,
        processor._playbooks,
        fallback=skill,
        data_dir=processor._data_dir_path(),
    )
    if policy_skill.name != skill.name:
        logger.info("LangGraph skill policy: %s → %s", skill.name, policy_skill.name)
        runtime.set_skill(policy_skill)

    if plan and plan.intent_class == "repo.docs.qa":
        log_checkpoint("route_plan", "repo_knowledge", "completed")

    from backend.routing.classifier.intent_classes import is_slack_board_create_intent

    if plan and is_slack_board_create_intent(plan.intent_class):
        log_checkpoint("route_plan", "slack_board_management", "completed")

    if plan:
        log_checkpoint("tool_plan", plan.intent_class or "unknown", "completed")
        goal_text = (plan.goal or "").strip()
        if goal_text:
            log_checkpoint("tool_plan_goal", goal_text[:160], "completed")
        step_names = [step.tool for step in (plan.steps or [])] or list(plan.tools_needed or [])
        if step_names:
            log_checkpoint("tool_plan_steps", " → ".join(step_names[:8]), "completed")

    return {"tool_plan": tool_plan_to_dict(plan)}


def validate_plan_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = get_runtime(config)
    processor = runtime.processor
    skill = runtime.active_skill
    plan = tool_plan_from_dict(state.get("tool_plan"))

    from backend.tools.builder import build_git_tool_registry
    from backend.models.session import mirror_workspace_key

    registry = build_git_tool_registry(
        processor.config,
        workspace_id=mirror_workspace_key(runtime.task),
        data_dir=processor._data_dir_path(),
        allowed_tools=skill.allowed_tools or None,
    )
    binding = validate_tool_plan(
        plan,
        registry,
        skill_allowed=list(skill.allowed_tools or []),
        skill_name=skill.name,
    )

    goal = goal_spec_from_plan(plan)
    runtime.scoped_tools = binding.allowed_tools
    runtime.manifest_text = binding.manifest_text

    from backend.orchestrator.graph.plan_routing import resolve_graph_route

    route = resolve_graph_route(plan, allowed_tools=binding.allowed_tools or [])

    log_checkpoint("graph_route", route, "completed")

    return {
        "scoped_tools": binding.allowed_tools,
        "manifest_text": binding.manifest_text,
        "goal_spec": goal_spec_to_dict(goal),
        "route": route,
        "skill_name": skill.name,
    }


def try_direct_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = get_runtime(config)
    plan = tool_plan_from_dict(state.get("tool_plan"))

    if plan and state.get("route") == "direct":
        response, patch = runtime.processor._execute_planned_direct(
            runtime.active_skill,
            runtime.task,
            runtime.session,
            plan,
        )
        if response is not None:
            kind = response.payload.kind
            data = dict(response.payload.data or {})
            return {
                "direct_handled": True,
                "route": "done",
                "response_kind": kind,
                "response_data": data,
                "raw_reply": str(data.get("text") or ""),
                "metadata_patch": patch,
                "tool_trace": [],
                "grounding_passed": True,
                "grounding_issues": [],
            }

    response, patch = runtime.processor._try_unified_direct(
        runtime.active_skill,
        runtime.task,
        runtime.session,
    )
    if response is None:
        return {"direct_handled": False, "route": "worker"}

    kind = response.payload.kind
    data = dict(response.payload.data or {})
    return {
        "direct_handled": True,
        "route": "done",
        "response_kind": kind,
        "response_data": data,
        "raw_reply": str(data.get("text") or ""),
        "metadata_patch": patch,
        "tool_trace": [],
        "grounding_passed": True,
        "grounding_issues": [],
    }


def run_worker_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = get_runtime(config)
    processor = runtime.processor
    skill = runtime.active_skill
    plan = tool_plan_from_dict(state.get("tool_plan"))
    goal_spec = goal_spec_from_dict(state.get("goal_spec")) or runtime.goal_spec
    allowed = list(state.get("scoped_tools") or runtime.scoped_tools or skill.allowed_tools or [])

    from backend.tools.builder import build_git_tool_registry
    from backend.models.session import mirror_workspace_key
    from backend.observability.checkpoint import log_checkpoint

    registry = build_git_tool_registry(
        processor.config,
        workspace_id=mirror_workspace_key(runtime.task),
        data_dir=processor._data_dir_path(),
        allowed_tools=allowed or None,
    )
    registry.clear_trace()
    registry.current_task = runtime.task
    registry.session_metadata = dict(getattr(runtime.session, "metadata", None) or {})
    processor._attach_governance(registry, runtime.task, session=runtime.session, skill_name=skill.name)

    messages = list(runtime.messages)
    manifest = state.get("manifest_text") or runtime.manifest_text
    if manifest and messages and messages[0].role == "system":
        messages[0] = Message(
            role="system",
            content=f"{messages[0].content.rstrip()}\n\n{manifest}",
        )

    if plan and should_use_subagents(plan):
        extra = "\n\n".join(
            build_subagent_manifest(domain, steps)
            for domain, steps in group_steps_by_domain(plan.steps or [])
        )
        if extra and messages and messages[0].role == "system":
            messages[0] = Message(
                role="system",
                content=f"{messages[0].content.rstrip()}\n\n{extra}",
            )

    if not allowed:
        allowed = list(registry._tools.keys())

    if skill.name == "html_slides" and messages and messages[0].role == "system":
        from backend.routing.html_slides_delivery import (
            html_slides_system_addendum,
            inject_html_slides_bootstrap_message,
        )

        messages[0] = Message(
            role="system",
            content=f"{messages[0].content.rstrip()}{html_slides_system_addendum(runtime.task, session=runtime.session, config=processor.config, data_dir=processor._data_dir_path())}",
        )
        messages = inject_html_slides_bootstrap_message(messages, runtime.task, session=runtime.session)

    runner = processor.config.orchestrator.agent_runner

    if plan and plan.intent_class == "repo.docs.qa" and messages and messages[0].role == "system":
        from backend.routing.doc_qa_prompt import doc_qa_system_addendum

        messages[0] = Message(
            role="system",
            content=f"{messages[0].content.rstrip()}{doc_qa_system_addendum()}",
        )

    if plan and plan.intent_class == "repo.docs.qa":
        from backend.routing.doc_qa_bootstrap import inject_doc_qa_bootstrap_message
        from backend.models.session import task_session_key

        log_checkpoint("doc_bootstrap", "search_and_read", "started")
        messages = inject_doc_qa_bootstrap_message(
            messages,
            registry,
            query=runtime.task.cleaned_intent,
            allowed=allowed,
            session=runtime.session,
            git=processor.config.git,
            task_id=runtime.task.id,
            session_key=task_session_key(runtime.task),
        )
        log_checkpoint("doc_bootstrap", "search_and_read", "completed")

    if plan:
        from backend.routing.slack_board.agent import is_slack_board_write_intent

        if is_slack_board_write_intent(plan.intent_class):
            from backend.routing.classifier.intent_classes import is_slack_board_create_intent
            from backend.routing.slack_board.bootstrap import inject_slack_board_bootstrap_message
            from backend.routing.slack_board.prompt import slack_board_agentic_addendum
            from slack_sdk import WebClient

            if messages and messages[0].role == "system":
                messages[0] = Message(
                    role="system",
                    content=(
                        f"{messages[0].content.rstrip()}"
                        f"{slack_board_agentic_addendum(intent_class=plan.intent_class)}"
                    ),
                )
            token = (processor.config.slack.bot_token or "").strip()
            slack_client = WebClient(token=token) if token else None
            if slack_client and is_slack_board_create_intent(plan.intent_class):
                log_checkpoint("board_bootstrap", "thread_context", "started")
                messages = inject_slack_board_bootstrap_message(
                    messages,
                    slack_client,
                    processor.config,
                    task=runtime.task,
                    data_dir=processor._data_dir_path(),
                    auto_create=False,
                )
                log_checkpoint("board_bootstrap", "thread_context", "completed")

    log_checkpoint("agent_loop_start", runner, "started")

    try:
        if runner == "hermes":
            from backend.orchestrator.hermes_runner import run_hermes_loop

            raw = run_hermes_loop(
                runtime.provider,
                messages,
                registry,
                allowed,
                model=runtime.model or None,
                session=runtime.session,
                git=processor.config.git,
            )
        else:
            raw = run_agent_loop(
                runtime.provider,
                messages,
                registry,
                allowed,
                model=runtime.model or None,
                session=runtime.session,
                git=processor.config.git,
            )
    except RuntimeError as exc:
        if "No tools available" in str(exc) and registry.last_result:
            raw = ""
        else:
            logger.exception("LangGraph worker node failed")
            failure = processor._investigation_failure_response(skill, allowed, exc)
            data = dict(failure.payload.data or {})
            return {
                "response_kind": failure.payload.kind,
                "response_data": data,
                "raw_reply": str(data.get("text") or ""),
                "tool_trace": list(registry.tool_trace),
                "metadata_patch": None,
                "route": "done",
            }
    except Exception as exc:
        logger.exception("LangGraph worker node failed")
        failure = processor._investigation_failure_response(skill, allowed, exc)
        data = dict(failure.payload.data or {})
        return {
            "response_kind": failure.payload.kind,
            "response_data": data,
            "raw_reply": str(data.get("text") or ""),
            "tool_trace": list(registry.tool_trace),
            "metadata_patch": None,
            "route": "done",
        }

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
        if structured is not None and not prose:
            data = dict(structured.payload.data or {})
            return {
                "response_kind": structured.payload.kind,
                "response_data": data,
                "raw_reply": str(data.get("text") or ""),
                "tool_trace": list(registry.tool_trace),
                "metadata_patch": patch,
                "route": "done",
            }

    if skill.name == "html_slides":
        from backend.routing.html_slides_delivery import (
            format_artifact_tool_reply,
            html_deck_session_metadata_patch,
            resolve_html_slides_reply,
            salvage_html_deck_from_prose,
        )

        public_base = (processor.config.artifacts.public_base_url or "").strip()
        artifact_reply, _, artifact_patch = resolve_html_slides_reply(
            registry,
            task=runtime.task,
            public_base_url=public_base,
        )
        if artifact_reply:
            merged_patch = {**(patch or {}), **(artifact_patch or {})}
            return {
                "raw_reply": artifact_reply,
                "response_kind": "text",
                "response_data": {"text": artifact_reply},
                "tool_trace": list(registry.tool_trace),
                "metadata_patch": merged_patch or None,
                "route": "done",
            }

        if prose:
            salvaged = salvage_html_deck_from_prose(
                prose,
                registry,
                allowed_tools=allowed,
            )
            if salvaged and salvaged.kind in ("html_deck_saved", "html_artifact_published"):
                salvaged_reply = format_artifact_tool_reply(
                    salvaged,
                    task=runtime.task,
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
                return {
                    "raw_reply": salvaged_reply,
                    "response_kind": "text",
                    "response_data": {"text": salvaged_reply},
                    "tool_trace": list(registry.tool_trace),
                    "metadata_patch": {**(patch or {}), **salvaged_patch},
                    "route": "done",
                }

    return {
        "raw_reply": prose or raw_stripped,
        "response_kind": "text",
        "response_data": {"text": prose or raw_stripped},
        "tool_trace": list(registry.tool_trace),
        "metadata_patch": patch,
        "route": "done",
    }


def missing_tools_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    plan = tool_plan_from_dict(state.get("tool_plan"))
    missing = plan.missing_capabilities if plan else []
    text = (
        "I can't complete this request yet — these capabilities are not available: "
        f"{', '.join(missing) if missing else 'unknown tools'}."
    )
    return {
        "raw_reply": text,
        "response_kind": "text",
        "response_data": {"text": text},
        "route": "done",
        "grounding_passed": True,
        "grounding_issues": [],
    }


def validate_goal_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    goal_spec = goal_spec_from_dict(state.get("goal_spec"))
    raw = str(state.get("raw_reply") or "")
    if state.get("response_kind") != "text" or not raw.strip():
        return {"grounding_passed": True, "grounding_issues": []}

    trace = [
        ToolTraceEntry(
            tool=str(item.get("tool") or ""),
            success=bool(item.get("success")),
            result_kind=str(item.get("result_kind") or ""),
            observation=str(item.get("observation") or ""),
        )
        for item in state.get("tool_trace") or []
    ]
    if not trace and not goal_spec:
        return {"grounding_passed": True, "grounding_issues": []}

    validation = validate_agent_result(raw, trace, goal_spec)
    log_checkpoint("grounding", "validate", "started")
    if validation.passed:
        log_checkpoint("grounding", "validate", "completed")
        return {"grounding_passed": True, "grounding_issues": []}

    log_checkpoint("grounding", "validate", "error")
    return {
        "grounding_passed": False,
        "grounding_issues": validation.issues,
        "raw_reply": validation.fallback,
        "response_data": {"text": validation.fallback},
    }


def format_reply_node(state: AlfredGraphState, config: RunnableConfig) -> dict[str, Any]:
    """Apply intent-class formatters to structured and text replies."""
    from backend.formatting.intent_formatters import format_reply_for_intent
    from backend.formatting.strategies import KIND_FORMATTERS

    kind = str(state.get("response_kind") or "text")
    data = dict(state.get("response_data") or {})
    plan = tool_plan_from_dict(state.get("tool_plan"))
    intent_class = plan.intent_class if plan else ""

    if kind in KIND_FORMATTERS and not data.get("text"):
        data["text"] = KIND_FORMATTERS[kind].render(data, slack=False)

    formatted = format_reply_for_intent(
        intent_class=intent_class,
        kind=kind,
        data=data,
        raw_text=str(state.get("raw_reply") or data.get("text") or ""),
    )
    if formatted:
        data["text"] = formatted

    text = str(data.get("text") or state.get("raw_reply") or "")
    return {
        "route": "done",
        "response_kind": kind,
        "response_data": data,
        "raw_reply": text,
    }
