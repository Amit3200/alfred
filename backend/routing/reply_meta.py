"""Confidence and relevancy metadata attached to assistant replies."""

from __future__ import annotations

from typing import Any

from backend.models.response import AssistantResponse
from backend.routing.tool_plan_types import ToolPlan


def attach_reply_meta(response: AssistantResponse, meta: dict[str, Any]) -> AssistantResponse:
    """Merge reply_meta into the response payload without changing rendered text."""
    if response.payload.data.get("reply_meta"):
        return response
    data = dict(response.payload.data)
    data["reply_meta"] = normalize_reply_meta(meta)
    return AssistantResponse(
        payload=response.payload.model_copy(update={"data": data}),
        text=response.text,
    )


def normalize_reply_meta(meta: dict[str, Any]) -> dict[str, Any]:
    confidence = float(meta.get("confidence") or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    relevancy = str(meta.get("relevancy") or "unverified").lower()
    if relevancy not in {"high", "medium", "low", "not_found", "unverified"}:
        relevancy = "unverified"
    out: dict[str, Any] = {
        "confidence": round(confidence, 2),
        "relevancy": relevancy,
        "classification": str(meta.get("classification") or _default_classification(relevancy)),
    }
    strategy = str(meta.get("strategy") or "").strip()
    if strategy:
        out["strategy"] = strategy
    return out


def _default_classification(relevancy: str) -> str:
    return {
        "high": "Strong match",
        "medium": "Partial match",
        "low": "Weak match",
        "not_found": "Not documented",
        "unverified": "Unverified",
    }.get(relevancy, "Unverified")


def doc_reply_meta(
    query: str,
    hit: dict[str, Any] | None,
    *,
    not_found: bool = False,
    web_fallback: bool = False,
) -> dict[str, Any]:
    from backend.context.doc_index import doc_hit_matches_query, significant_query_tokens

    if web_fallback:
        return {
            "confidence": 0.28,
            "relevancy": "low",
            "classification": "Web fallback",
            "strategy": "doc_search",
        }

    if not_found or hit is None:
        return {
            "confidence": 0.08,
            "relevancy": "not_found",
            "classification": "Not documented",
            "strategy": "doc_search",
        }

    score = float(hit.get("score") or 0)
    path = str(hit.get("path") or "")
    title = str(hit.get("title") or "")
    entities = significant_query_tokens(query)
    path_match = bool(entities) and any(
        _field_has_token(token, path) or _field_has_token(token, title) for token in entities
    )

    if entities and path_match:
        confidence = min(0.97, 0.78 + score * 0.025)
        return {
            "confidence": round(confidence, 2),
            "relevancy": "high",
            "classification": "Exact doc match",
            "strategy": "doc_search",
        }

    if entities and doc_hit_matches_query(hit, query):
        confidence = min(0.92, 0.62 + score * 0.035)
        return {
            "confidence": round(confidence, 2),
            "relevancy": "high" if confidence >= 0.8 else "medium",
            "classification": "Entity match in docs",
            "strategy": "doc_search",
        }

    if not entities:
        confidence = min(0.78, 0.45 + score * 0.04)
        return {
            "confidence": round(confidence, 2),
            "relevancy": "medium",
            "classification": "Topic match",
            "strategy": "doc_search",
        }

    confidence = min(0.42, 0.18 + score * 0.025)
    return {
        "confidence": round(confidence, 2),
        "relevancy": "low",
        "classification": "Weak doc match",
        "strategy": "doc_search",
    }


def plan_reply_meta(plan: ToolPlan | None) -> dict[str, Any]:
    if plan is None:
        return generic_reply_meta("text")
    confidence = float(plan.confidence or 0.0)
    if confidence >= 0.85:
        relevancy = "high"
        classification = "Plan grounded"
    elif confidence >= 0.6:
        relevancy = "medium"
        classification = "Plan matched"
    else:
        relevancy = "low"
        classification = "Low plan confidence"
    return {
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "relevancy": relevancy,
        "classification": classification,
        "strategy": str(plan.strategy or "plan"),
    }


def tool_result_reply_meta(kind: str) -> dict[str, Any]:
    grounded = {
        "pr_list",
        "pr_detail",
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
        "doc_content",
        "doc_answer",
        "web_search",
    }
    if kind in grounded:
        return {
            "confidence": 0.9 if kind.startswith(("pr_", "git_", "jira_", "code_", "file_")) else 0.82,
            "relevancy": "high",
            "classification": "Tool result",
            "strategy": kind,
        }
    if kind == "doc_search":
        return {
            "confidence": 0.35,
            "relevancy": "low",
            "classification": "Search only",
            "strategy": "doc_search",
        }
    if kind == "error":
        return {
            "confidence": 0.0,
            "relevancy": "unverified",
            "classification": "Error",
            "strategy": "error",
        }
    return generic_reply_meta(kind)


def generic_reply_meta(kind: str = "text", *, skill_name: str = "") -> dict[str, Any]:
    if skill_name in ("repo_knowledge", "investigate_bug"):
        return {
            "confidence": 0.45,
            "relevancy": "medium",
            "classification": "Skill routed",
            "strategy": skill_name,
        }
    return {
        "confidence": 0.32,
        "relevancy": "unverified",
        "classification": "LLM only",
        "strategy": kind or "text",
    }


def finalize_reply_meta(
    response: AssistantResponse,
    *,
    tool_plan: ToolPlan | None = None,
    skill_name: str = "",
    explicit: dict[str, Any] | None = None,
) -> AssistantResponse:
    if response.payload.data.get("reply_meta"):
        return response
    if explicit:
        return attach_reply_meta(response, explicit)
    if tool_plan is not None:
        return attach_reply_meta(response, plan_reply_meta(tool_plan))
    return attach_reply_meta(response, tool_result_reply_meta(response.payload.kind))


def _field_has_token(token: str, field: str) -> bool:
    from backend.context.doc_index import _token_matches_field

    return _token_matches_field(token, field)
