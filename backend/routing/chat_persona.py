"""UI chat personas — explicit routing scope instead of regex-only guessing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

ChatPersona = Literal["support", "tech", "all", "general"]

_PERSONA_VALUES = frozenset({"support", "tech", "all", "general"})

_LEGACY_PERSONA_MAP = {
    "auto": "support",
    "qa": "support",
    "debug": "tech",
}

_BROADER_SEARCH_RE = re.compile(
    r"\b("
    r"cipher|codebase|code repo|in (?:the )?repo|search (?:the )?(?:code|repo|cipher)|"
    r"check (?:the )?code|grep|playbook|runbook|investigate|main repo|"
    r"FlexyPe/cipher|dailyscripts|scripts repo"
    r")\b",
    re.I,
)
_DOC_HINT_RE = re.compile(
    r"\b(doc(umentation)?s?|handbook|how to|what is|what's|tell me about|explain|"
    r"as per (?:our )?docs|refer to doc|our docs|per our docs|from our docs|"
    r"configure|integration|feature|upsell|merchant|checkout)\b",
    re.I,
)
_DOC_SOURCE_RE = re.compile(r"`(?:handbook|integrations|docs)/[^`]+`", re.I)
_TECH_HINT_RE = re.compile(
    r"\b(error|exception|stack\s*trace|log(s)?|grep|debug|incident|prod(uction)?|"
    r"cloudwatch|athena|500|timeout|failed|bug|playbook|runbook)\b",
    re.I,
)


def normalize_persona(raw: str | None) -> ChatPersona:
    value = (raw or "support").strip().lower()
    value = _LEGACY_PERSONA_MAP.get(value, value)
    if value in _PERSONA_VALUES:
        return value  # type: ignore[return-value]
    return "support"


def user_wants_broader_search(query: str) -> bool:
    """True when the user explicitly asks to search outside handbook/docs repos."""
    return bool(_BROADER_SEARCH_RE.search(query or ""))


def infer_persona_from_session(session: Any | None, message: str) -> ChatPersona:
    """Guess persona from sticky session metadata and recent turns."""
    if session is not None:
        sticky = normalize_persona(session.metadata.get("chat_persona"))
        if sticky != "support" or session.metadata.get("chat_persona") not in (None, "", "auto", "support"):
            # User picked a non-default persona — keep it sticky.
            if session.metadata.get("chat_persona") not in (None, "", "auto"):
                return sticky
        if session.metadata.get("last_intent_class") == "repo.docs.qa":
            return "support"
        if session and session.turns:
            for turn in reversed(session.turns[-4:]):
                if turn.role != "assistant":
                    continue
                body = turn.content or ""
                if _DOC_SOURCE_RE.search(body) or "indexed documentation" in body.lower():
                    return "support"

    text = (message or "").strip()
    if _TECH_HINT_RE.search(text) and not _DOC_HINT_RE.search(text):
        return "tech"
    if _DOC_HINT_RE.search(text):
        return "support"
    return "support"


def resolve_effective_persona(task: Task, session: Any | None) -> ChatPersona:
    """Resolve persona for a UI task (explicit metadata wins, then inference)."""
    if task.source != "ui":
        return "all"
    effective = str(task.metadata.get("chat_persona_effective") or "").strip()
    if effective:
        return normalize_persona(effective)
    sticky = ""
    if session is not None:
        sticky = str(session.metadata.get("last_persona") or session.metadata.get("chat_persona") or "").strip()
    if not sticky:
        sticky = str(task.metadata.get("chat_persona") or "support").strip()
    if sticky:
        return normalize_persona(sticky)
    return infer_persona_from_session(session, task.cleaned_intent)


def build_support_doc_plan(task: Task) -> ToolPlan:
    """Deterministic handbook/documentation Q&A plan."""
    query = (task.cleaned_intent or task.raw_text or "").strip()
    return ToolPlan(
        goal="Answer from indexed support documentation (FlexyPe/docs)",
        confidence=0.97,
        tools_needed=["search_repo_docs", "read_repo_doc"],
        steps=[ToolPlanStep("search_repo_docs", "search docs", {"query": query})],
        intent_class="repo.docs.qa",
        strategy="persona",
    )


# Backwards-compatible alias
build_qa_doc_plan = build_support_doc_plan

SUPPORT_TOOL_PRIORITY: tuple[str, ...] = (
    "search_repo_docs",
    "read_repo_doc",
    "list_repo_docs",
    "web_search",
)

TECH_TOOL_PRIORITY: tuple[str, ...] = (
    "grep_repo",
    "read_file",
    "query_graph",
    "search_repo_docs",
    "read_repo_doc",
    "git_log",
    "git_blame",
    "cloudwatch_query",
    "athena_query",
    "web_search",
)

QA_TOOL_PRIORITY = SUPPORT_TOOL_PRIORITY
DEBUG_TOOL_PRIORITY = TECH_TOOL_PRIORITY


def persona_skill_name(persona: ChatPersona) -> str | None:
    if persona == "support":
        return "repo_knowledge"
    if persona == "tech":
        return "investigate_bug"
    return None


def filter_tools_for_persona(
    persona: ChatPersona,
    tools: list[str],
    *,
    registered: set[str] | None = None,
) -> list[str]:
    """Order and restrict scoped tools for a persona."""
    if persona in ("all", "general"):
        return list(tools)
    priority = SUPPORT_TOOL_PRIORITY if persona == "support" else TECH_TOOL_PRIORITY
    allowed = set(tools)
    if registered is not None:
        allowed &= registered
    ordered = [name for name in priority if name in allowed]
    rest = [name for name in tools if name in allowed and name not in ordered]
    return ordered + rest


def doc_search_scope_for_persona(
    config: AlfredConfig,
    data_dir: Path,
    persona: ChatPersona,
    query: str,
    *,
    default_slugs: list[str],
) -> tuple[list[str], tuple[str, ...], tuple[str, ...]]:
    """Return (repo slugs, exclude prefixes, include-only prefixes) for doc search."""
    from backend.context.repo_profiles import (
        knowledge_doc_repo_slugs,
        knowledge_tech_doc_repo_slugs,
    )

    persona = normalize_persona(persona)
    exclude: tuple[str, ...] = ()
    include_only: tuple[str, ...] = ()

    if persona == "support":
        if user_wants_broader_search(query):
            return default_slugs, exclude, include_only
        docs_only = knowledge_doc_repo_slugs(config, data_dir)
        slugs = docs_only or default_slugs
        exclude = ("playbooks/",)
        return slugs, exclude, include_only

    if persona == "tech":
        tech_slugs = knowledge_tech_doc_repo_slugs(config, data_dir)
        slugs = tech_slugs or default_slugs
        include_only = ("playbooks/", "runbooks/")
        return slugs, exclude, include_only

    lower = (query or "").lower()
    if not any(token in lower for token in ("playbook", "runbook", "investigate")):
        exclude = ("playbooks/",)
    return default_slugs, exclude, include_only


def persona_from_interaction_context() -> ChatPersona | None:
    from backend.observability.context import get_interaction_context

    ctx = get_interaction_context()
    if ctx is None:
        return None
    raw = str(
        ctx.metadata.get("chat_persona_effective")
        or ctx.metadata.get("chat_persona")
        or ""
    ).strip()
    if not raw:
        return None
    return normalize_persona(raw)
