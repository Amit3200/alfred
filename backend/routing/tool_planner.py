"""Rule-based and LLM tool planning."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.ai.base import LLMProvider, Message
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.entity_extractor import EntityBag, extract_entities
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.routing.types import RouteContext
from backend.tools.catalog_formatter import all_plannable_tool_names, format_tool_catalog_for_planner

logger = logging.getLogger(__name__)

_MIN_LLM_CONFIDENCE = 0.55
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)

_CREATE_SHEET_RE = re.compile(
    r"\b(create|make|build)\b.{0,40}\b(google\s*)?(sheet|spreadsheet)\b",
    re.I,
)
_CREATE_DOC_RE = re.compile(
    r"\b(create|make)\b.{0,40}\b(google\s*)?(doc|document)\b",
    re.I,
)
_ASSIGN_RE = re.compile(
    r"\bassign\b.{0,60}\b(ticket|issue|jira|PROJ|\w+-\d+)",
    re.I,
)
_TRANSITION_RE = re.compile(
    r"\b(move|transition|change\s+status|mark)\b.{0,40}\b(done|closed|resolved|in\s+progress|review)\b",
    re.I,
)
_SUMMARIZE_THREAD_RE = re.compile(r"\bsummarize\b.{0,30}\b(thread|conversation)\b", re.I)
_SUMMARIZE_ALERTS_RE = re.compile(
    r"\bsummarize\b.{0,30}\b(alert|bug|incident|error)\b",
    re.I,
)
_READ_SHEET_RE = re.compile(r"\b(read|show|get|open)\b.{0,30}\b(sheet|spreadsheet)\b", re.I)
_REPO_DOC_QA_RE = re.compile(
    r"(?:"
    r"\b("
    r"runbook|runbooks|documentation|docs?\s+say|what does (our|the)|how do we|playbook says?|"
    r"as per (?:our |the )?docs|per (?:our |the )?docs|refer to (?:the )?doc|our docs|"
    r"from (?:our |the )?docs|in (?:our |the )?documentation|"
    r"how (?:can|do|to)|configured?|configure|integrat(?:e|d|ion)|setup|set up|"
    r"onboarding|support doc|knowledge base|merchant|feature(?:s)?"
    r")\b|"
    r"\bhow\b.{0,80}\b(configur(?:e|ed|ing)|integrat(?:e|ed|ing)|setup|set up|connect|enable)\b|"
    r"\bwhat (?:is|are) (?:the )?.{2,80} (?:all )?about\b|"
    r"\bwhat's (?:the )?.{2,80} (?:all )?about\b|"
    r"\btell me about\b|"
    r"\bexplain (?:the )?.{3,80}\b|"
    r"\bdescribe (?:the )?.{3,80}\b"
    r")",
    re.I,
)
_SCRIPT_RUN_RE = re.compile(r"\b(run|execute|trigger)\b.{0,30}\b(script|report|metrics|job)\b", re.I)


def looks_like_repo_doc_question(text: str, *, source: str = "") -> bool:
    """True when the user likely wants indexed repo documentation."""
    stripped = f"{text or ''}".strip()
    if source == "slack":
        from backend.routing.slack_board_intent import (
            looks_like_slack_board_config_question,
            looks_like_slack_board_request,
        )

        if looks_like_slack_board_config_question(stripped):
            return False
        if looks_like_slack_board_request(stripped):
            return False
    return bool(_REPO_DOC_QA_RE.search(stripped))


def planner_llm_enabled(config: AlfredConfig) -> bool:
    """True when resolve_tool_plan should invoke the LLM tool planner."""
    routing = config.routing
    if routing.planner_strategy == "llm_first":
        return True
    return bool(routing.tool_planner_llm_fallback)


def plan_tools_rules(
    task: Task,
    entities: EntityBag,
    *,
    skill_allowed: list[str] | None = None,
    config: AlfredConfig | None = None,
    data_dir: Any = None,
    entity_direct_only: bool = False,
) -> ToolPlan | None:
    """Deterministic tool plan from intent + entities."""
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    lower = text.lower()
    allowed = set(skill_allowed or [])

    def _ok(name: str) -> bool:
        return not allowed or name in allowed

    # Single issue key → get
    if entities.issue_keys and len(entities.issue_keys) == 1 and len(text.split()) <= 8:
        key = entities.issue_keys[0]
        if _ok("get_jira_issue"):
            return ToolPlan(
                goal=f"Fetch JIRA issue {key}",
                confidence=0.95,
                tools_needed=["get_jira_issue"],
                steps=[ToolPlanStep("get_jira_issue", "fetch issue", {"issue_key": key})],
                intent_class="jira.read.single",
                strategy="rules",
            )

    if _CREATE_SHEET_RE.search(text):
        tools = [t for t in ("google_create_sheet", "google_write_sheet") if _ok(t)]
        if tools:
            return ToolPlan(
                goal="Create Google Sheet from user data",
                confidence=0.88,
                tools_needed=tools,
                steps=[
                    ToolPlanStep("google_create_sheet", "create spreadsheet"),
                    ToolPlanStep("google_write_sheet", "write rows"),
                ],
                intent_class="google.create.sheet",
                strategy="rules",
            )

    if entities.spreadsheet_ids and _READ_SHEET_RE.search(text) and _ok("google_read_sheet"):
        sid = entities.spreadsheet_ids[0]
        return ToolPlan(
            goal="Read Google Sheet",
            confidence=0.9,
            tools_needed=["google_read_sheet"],
            steps=[ToolPlanStep("google_read_sheet", "read sheet", {"spreadsheet_id": sid})],
            intent_class="google.read.sheet",
            strategy="rules",
        )

    if _CREATE_DOC_RE.search(text):
        tools = [t for t in ("google_create_doc",) if _ok(t)]
        if tools:
            return ToolPlan(
                goal="Create Google Doc",
                confidence=0.85,
                tools_needed=tools,
                steps=[ToolPlanStep("google_create_doc", "create doc")],
                intent_class="google.create.doc",
                strategy="rules",
            )

    if entities.document_ids and _ok("google_read_doc"):
        return ToolPlan(
            goal="Read Google Doc",
            confidence=0.88,
            tools_needed=["google_read_doc"],
            steps=[
                ToolPlanStep(
                    "google_read_doc",
                    "read doc",
                    {"document_id": entities.document_ids[0]},
                )
            ],
            intent_class="google.read.doc",
            strategy="rules",
        )

    if _ASSIGN_RE.search(text) and entities.issue_keys and _ok("jira_assign_issue"):
        return ToolPlan(
            goal="Assign JIRA issue",
            confidence=0.85,
            tools_needed=["jira_assign_issue"],
            steps=[
                ToolPlanStep(
                    "jira_assign_issue",
                    "assign issue",
                    {"issue_key": entities.issue_keys[0]},
                )
            ],
            intent_class="jira.write.assign",
            strategy="rules",
        )

    if _TRANSITION_RE.search(text) and entities.issue_keys and _ok("transition_jira_issue"):
        return ToolPlan(
            goal="Transition JIRA issue status",
            confidence=0.82,
            tools_needed=["transition_jira_issue"],
            steps=[
                ToolPlanStep(
                    "transition_jira_issue",
                    "change status",
                    {"issue_key": entities.issue_keys[0]},
                )
            ],
            intent_class="jira.write.transition",
            strategy="rules",
        )

    if config is not None and _ok("run_company_script"):
        from backend.integrations.company_scripts.triggers import match_script_by_trigger

        script_name = match_script_by_trigger(text, data_dir=data_dir, config=config)
        if script_name:
            return ToolPlan(
                goal=f"Run company script {script_name}".strip(),
                confidence=0.9,
                tools_needed=["run_company_script"],
                steps=[
                    ToolPlanStep(
                        "run_company_script",
                        "run script",
                        {"script": script_name},
                    )
                ],
                intent_class="script.run",
                strategy="rules",
            )

    if entity_direct_only:
        return None

    if _SUMMARIZE_THREAD_RE.search(text) and _ok("slack_fetch_thread"):
        return ToolPlan(
            goal="Summarize Slack thread",
            confidence=0.8,
            tools_needed=["slack_fetch_thread"],
            steps=[ToolPlanStep("slack_fetch_thread", "fetch thread for summary")],
            intent_class="slack.summarize.thread",
            strategy="rules",
        )

    if _SUMMARIZE_ALERTS_RE.search(text) and _ok("slack_fetch_channel_history"):
        return ToolPlan(
            goal="Summarize alerts from channel history",
            confidence=0.78,
            tools_needed=["slack_fetch_channel_history"],
            steps=[ToolPlanStep("slack_fetch_channel_history", "fetch channel history")],
            intent_class="slack.summarize.alerts",
            strategy="rules",
        )

    if config is not None and task.source == "slack":
        from backend.integrations.slack.board_service import board_enabled, resolve_board_for_task
        from backend.routing.slack_board_intent import (
            looks_like_slack_board_config_question,
            looks_like_slack_board_create,
            looks_like_slack_board_request,
            looks_like_slack_board_update,
            references_thread_context,
        )

        if looks_like_slack_board_config_question(text):
            return None

        if board_enabled(config, data_dir) and resolve_board_for_task(config, task, data_dir=data_dir):
            if looks_like_slack_board_create(text) and _ok("slack_board_create_task"):
                tools = ["slack_board_create_task"]
                steps = [ToolPlanStep("slack_board_create_task", "create list task")]
                if references_thread_context(text) and _ok("slack_fetch_thread"):
                    tools = ["slack_fetch_thread", "slack_board_create_task"]
                    steps = [
                        ToolPlanStep("slack_fetch_thread", "fetch thread for task details"),
                        ToolPlanStep("slack_board_create_task", "create list task"),
                    ]
                return ToolPlan(
                    goal="Create Slack List board task",
                    confidence=0.9,
                    tools_needed=tools,
                    steps=steps,
                    intent_class="slack.board.create",
                    strategy="rules",
                )

            if looks_like_slack_board_update(text) and _ok("slack_board_update_task"):
                return ToolPlan(
                    goal="Update Slack List board task",
                    confidence=0.85,
                    tools_needed=["slack_board_update_task"],
                    steps=[ToolPlanStep("slack_board_update_task", "update list task")],
                    intent_class="slack.board.update",
                    strategy="rules",
                )

            if looks_like_slack_board_request(text) and _ok("slack_board_search_tasks"):
                if not looks_like_slack_board_create(text) and not looks_like_slack_board_update(text):
                    return ToolPlan(
                        goal="Search Slack List board tasks",
                        confidence=0.8,
                        tools_needed=["slack_board_search_tasks"],
                        steps=[ToolPlanStep("slack_board_search_tasks", "search board")],
                        intent_class="slack.board.search",
                        strategy="rules",
                    )

    if looks_like_repo_doc_question(task.cleaned_intent or text, source=task.source) and _ok(
        "search_repo_docs"
    ):
        return ToolPlan(
            goal="Answer from indexed repo documentation",
            confidence=0.9,
            tools_needed=["search_repo_docs", "read_repo_doc"],
            steps=[
                ToolPlanStep("search_repo_docs", "search docs", {"query": task.cleaned_intent}),
            ],
            intent_class="repo.docs.qa",
            strategy="rules",
        )

    if config is not None and _ok("run_company_script"):
        from backend.integrations.company_scripts.triggers import match_script_by_trigger

        script_name = match_script_by_trigger(text, data_dir=data_dir, config=config)
        if not script_name and _SCRIPT_RUN_RE.search(text):
            return ToolPlan(
                goal="Run company script",
                confidence=0.7,
                tools_needed=["run_company_script"],
                steps=[ToolPlanStep("run_company_script", "run script")],
                intent_class="script.run",
                strategy="rules",
            )

    if "jira" in lower or "ticket" in lower:
        if any(h in lower for h in ("list", "show", "search", "open", "assigned")) and _ok("jira_search"):
            return ToolPlan(
                goal="Search/list JIRA issues",
                confidence=0.75,
                tools_needed=["jira_search"],
                steps=[ToolPlanStep("jira_search", "search issues")],
                intent_class="jira.read.list",
                strategy="rules",
            )

    return None


def _format_planner_session_context(session_metadata: dict[str, Any] | None) -> str:
    meta = dict(session_metadata or {})
    lines: list[str] = []
    if meta.get("pending_board_create"):
        lines.append("Session: awaiting task title for Slack List create.")
    last = dict(meta.get("last_board_task") or {})
    if last:
        display_id = last.get("display_id") or ""
        title = last.get("title") or ""
        record_id = last.get("record_id") or ""
        if display_id or record_id:
            lines.append(
                "Last board task in this thread: "
                f"{display_id or record_id}"
                + (f" — {title}" if title else "")
                + (f" (record {record_id})" if record_id and display_id else "")
            )
    return "\n".join(lines)


def _build_planner_channel_context(
    config: AlfredConfig | None,
    task: Task,
    data_dir: Any,
    *,
    session_metadata: dict[str, Any] | None = None,
) -> str:
    if config is None or task.source != "slack" or not task.channel_id:
        return ""
    from backend.db.slack_workflows_db import db_get_board_binding_for_channel, db_get_channel_workflow

    lines = [f"Slack channel id: {task.channel_id}"]
    workflow = db_get_channel_workflow(data_dir, task.channel_id)
    if workflow:
        lines.append(f"Channel ticket system: {workflow.get('ticket_system', 'ask')}")
        if workflow.get("jira_project_key"):
            lines.append(f"Channel JIRA project: {workflow['jira_project_key']}")
    binding = db_get_board_binding_for_channel(data_dir, task.channel_id)
    if binding:
        lines.extend(
            [
                f"Slack List board linked: {binding.get('board_key')} ({binding.get('list_id')})",
                f"Display id prefix: {binding.get('display_id_prefix')}",
            ]
        )
    else:
        lines.append("Slack List board: not linked for this channel")
    session_context = _format_planner_session_context(session_metadata)
    if session_context:
        lines.append(session_context)
    return "\n".join(lines)


def plan_tools_llm(
    provider: LLMProvider,
    context: RouteContext,
    entities: EntityBag,
    *,
    model: str | None = None,
    skill_allowed: list[str] | None = None,
    min_confidence: float = _MIN_LLM_CONFIDENCE,
    config: AlfredConfig | None = None,
    task: Task | None = None,
    data_dir: Any = None,
    session_metadata: dict[str, Any] | None = None,
) -> ToolPlan | None:
    """LLM tool planner — structured JSON only."""
    catalog_tools = list(skill_allowed) if skill_allowed else all_plannable_tool_names()
    catalog = format_tool_catalog_for_planner(catalog_tools)

    user_parts = [
        catalog,
        "",
        f"User message:\n{context.intent.strip()}",
        "",
        f"Extracted entities: {json.dumps(entities.raw, default=str)}",
    ]
    if context.thread_context:
        snippet = context.thread_context.strip()
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n… (truncated)"
        user_parts.extend(["", "Thread context:", snippet])
    if context.session_turns:
        user_parts.extend(["", "Recent session turns:"])
        user_parts.extend(f"- {t}" for t in context.session_turns[-2:])
    channel_context = (
        _build_planner_channel_context(
            config,
            task,
            data_dir,
            session_metadata=session_metadata,
        )
        if task
        else ""
    )
    if channel_context:
        user_parts.extend(["", "Channel configuration:", channel_context])

    system = """You are Alfred's Tool Planner. Given the user message, entities, and tool catalog,
produce a JSON plan. Do NOT execute tools. Do NOT invent tool names.

{
  "goal": "<one sentence>",
  "confidence": 0.0-1.0,
  "tools_needed": ["exact_tool_name", ...],
  "steps": [{"tool": "<name>", "purpose": "<why>", "args_hint": {}}],
  "missing_capabilities": ["<if any tool needed but not in catalog>"],
  "intent_class": "<short label>"
}

Rules:
1. Only use tools from the catalog.
2. For "create sheet from CSV/data", use google_create_sheet then google_write_sheet.
3. For assign requests on existing tickets, use jira_assign_issue not jira_create_issue.
4. For summarize thread/alerts, include slack_fetch_thread or slack_fetch_channel_history.
5. Questions about whether THIS Slack channel is configured for task tracking/boards are NOT repo documentation — prefer slack_board_* tools or set tools_needed=[] with intent_class slack.board.config.
6. Product/runbook/documentation questions use search_repo_docs + read_repo_doc with intent_class repo.docs.qa.
7. Slack List task create/update/search uses slack_board_* tools with intent_class slack.board.*.
   Include args_hint on steps: title for create; ticket_ref/display_id, status, assignee_user_id, severity for update.
   For follow-ups like "assign it to @user", use last board task from session context as ticket_ref when no id in message.
8. If impossible with catalog, set tools_needed=[] and list missing_capabilities.
9. Max 6 tools in tools_needed."""

    try:
        response = provider.chat(
            [
                Message(role="system", content=system),
                Message(role="user", content="\n".join(user_parts)),
            ],
            model=model,
        )
    except Exception as exc:
        logger.warning("LLM tool planner failed: %s", exc)
        return None

    parsed = _parse_plan_json(response.content or "")
    if not parsed:
        return None

    confidence = _clamp_float(parsed.get("confidence"), default=0.0)
    if confidence < min_confidence:
        return None

    tools_needed = _normalize_tool_list(parsed.get("tools_needed"), catalog_tools)
    steps = _normalize_steps(parsed.get("steps"), tools_needed)
    missing = _normalize_str_list(parsed.get("missing_capabilities"))

    return ToolPlan(
        goal=str(parsed.get("goal") or context.intent[:120]),
        confidence=confidence,
        tools_needed=tools_needed,
        steps=steps,
        missing_capabilities=missing,
        intent_class=str(parsed.get("intent_class") or ""),
        strategy="llm",
    )


def resolve_tool_plan(
    config: AlfredConfig,
    task: Task,
    context: RouteContext,
    *,
    provider: LLMProvider | None = None,
    model: str | None = None,
    skill_allowed: list[str] | None = None,
    data_dir: Any = None,
    playbook_store: Any = None,
    session_metadata: dict[str, Any] | None = None,
) -> ToolPlan | None:
    """Resolve tool plan: LLM-first (default) or rules-first (legacy)."""
    if not config.routing.tool_planner_enabled:
        return None

    min_conf = config.routing.tool_planner_min_confidence
    llm_first = config.routing.planner_strategy == "llm_first"
    entity_direct_only = llm_first

    if task.source == "ui":
        from backend.routing.chat_persona import (
            build_support_doc_plan,
            normalize_persona,
            resolve_effective_persona,
        )

        persona = str(task.metadata.get("chat_persona_effective") or "")
        if not persona:
            persona = resolve_effective_persona(task, None)
        if normalize_persona(persona) == "support":
            qa_plan = build_support_doc_plan(task)
            if skill_allowed:
                allowed = set(skill_allowed)
                filtered = [t for t in qa_plan.tools_needed if t in allowed]
                if filtered:
                    qa_plan.tools_needed = filtered
                    qa_plan.steps = [s for s in qa_plan.steps if s.tool in filtered]
                else:
                    qa_plan = None
            if qa_plan:
                return qa_plan

    entities = extract_entities(task.cleaned_intent, task.raw_text, context.thread_context or "")

    if llm_first and provider is not None:
        llm_plan = plan_tools_llm(
            provider,
            context,
            entities,
            model=model,
            skill_allowed=skill_allowed,
            min_confidence=min_conf,
            config=config,
            task=task,
            session_metadata=session_metadata,
        )
        if llm_plan and llm_plan.confidence >= min_conf:
            logger.info(
                "LLM-first plan: intent=%s confidence=%.2f tools=%s",
                llm_plan.intent_class,
                llm_plan.confidence,
                llm_plan.tools_needed,
            )
            return llm_plan

    plan = plan_tools_rules(
        task,
        entities,
        skill_allowed=skill_allowed,
        config=config,
        data_dir=data_dir,
        entity_direct_only=entity_direct_only,
    )
    if plan and plan.confidence >= min_conf:
        return plan

    if playbook_store is not None:
        from backend.routing.plan_templates import match_plan_template

        template_plan = match_plan_template(
            context.intent,
            playbook_store,
            channel_id=context.channel_id,
            repo=context.repo,
            min_confidence=config.routing.plan_template_min_confidence,
        )
        if template_plan:
            if skill_allowed:
                allowed = set(skill_allowed)
                filtered = [t for t in template_plan.tools_needed if t in allowed]
                if filtered:
                    template_plan.tools_needed = filtered
                    template_plan.steps = [s for s in template_plan.steps if s.tool in allowed]
                else:
                    template_plan = None
            if template_plan and template_plan.confidence >= min_conf:
                return template_plan

    if not llm_first and planner_llm_enabled(config) and provider is not None:
        llm_plan = plan_tools_llm(
            provider,
            context,
            entities,
            model=model,
            skill_allowed=skill_allowed,
            min_confidence=min_conf,
            config=config,
            task=task,
            session_metadata=session_metadata,
        )
        if llm_plan:
            return llm_plan

    return plan


def _parse_plan_json(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None
    candidates = [raw]
    if match := _JSON_BLOCK_RE.search(raw):
        candidates.insert(0, match.group(1).strip())
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _normalize_tool_list(value: Any, catalog: list[str]) -> list[str]:
    catalog_set = set(catalog)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        name = str(item or "").strip()
        if name and name in catalog_set and name not in out:
            out.append(name)
    return out


def _normalize_steps(value: Any, tools: list[str]) -> list[ToolPlanStep]:
    if not isinstance(value, list):
        return [ToolPlanStep(t, "") for t in tools]
    steps: list[ToolPlanStep] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip()
        if not tool:
            continue
        steps.append(
            ToolPlanStep(
                tool=tool,
                purpose=str(item.get("purpose") or ""),
                args_hint=dict(item.get("args_hint") or {}),
            )
        )
    return steps or [ToolPlanStep(t, "") for t in tools]


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, score))
