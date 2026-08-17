"""Tests for reply confidence and relevancy metadata."""

from __future__ import annotations

from backend.models.response import AssistantResponse
from backend.routing.reply_meta import (
    attach_reply_meta,
    doc_reply_meta,
    finalize_reply_meta,
    normalize_reply_meta,
    plan_reply_meta,
)
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep


def test_doc_not_found_meta():
    meta = doc_reply_meta("Do we have bytespeed integration?", None, not_found=True)
    assert meta["relevancy"] == "not_found"
    assert meta["confidence"] < 0.2
    assert "Not documented" in meta["classification"]


def test_doc_exact_match_meta():
    hit = {"path": "platforms/bytespeed.mdx", "title": "ByteSpeed", "score": 8.5, "excerpt": "ByteSpeed integration"}
    meta = doc_reply_meta("How do we configure bytespeed?", hit)
    assert meta["relevancy"] == "high"
    assert meta["confidence"] >= 0.75


def test_attach_reply_meta_preserves_text():
    response = AssistantResponse.from_text("Hello")
    updated = attach_reply_meta(response, {"confidence": 0.5, "relevancy": "medium"})
    assert updated.text == "Hello"
    assert updated.payload.data["reply_meta"]["confidence"] == 0.5


def test_finalize_uses_explicit_over_plan():
    response = AssistantResponse.from_text("No")
    explicit = doc_reply_meta("bytespeed integration", None, not_found=True)
    plan = ToolPlan(
        goal="docs",
        confidence=0.97,
        tools_needed=["search_repo_docs"],
        steps=[ToolPlanStep("search_repo_docs", "search", {})],
        strategy="persona",
    )
    finalized = finalize_reply_meta(response, tool_plan=plan, explicit=explicit)
    assert finalized.payload.data["reply_meta"]["relevancy"] == "not_found"


def test_plan_reply_meta_high():
    plan = ToolPlan(
        goal="grep logs",
        confidence=0.91,
        tools_needed=["grep_repo"],
        steps=[],
        strategy="rules",
    )
    meta = plan_reply_meta(plan)
    assert meta["relevancy"] == "high"
    assert meta["confidence"] == 0.91


def test_normalize_reply_meta_clamps():
    meta = normalize_reply_meta({"confidence": 1.8, "relevancy": "HIGH", "classification": "Test"})
    assert meta["confidence"] == 1.0
    assert meta["relevancy"] == "high"
