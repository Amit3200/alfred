"""Tests for chat persona routing and doc asset helpers."""

from __future__ import annotations

from backend.context.doc_assets import append_doc_image_gallery, extract_doc_images
from backend.models.config import AlfredConfig, RepoKnowledgeConfig, RoutingConfig
from backend.models.session import ConversationSession, ConversationTurn
from backend.models.task import Task
from backend.routing.chat_persona import (
    build_support_doc_plan,
    infer_persona_from_session,
    normalize_persona,
    user_wants_broader_search,
)
from backend.routing.tool_planner import resolve_tool_plan
from backend.routing.types import RouteContext, RouteMode


def test_legacy_persona_aliases():
    assert normalize_persona("qa") == "support"
    assert normalize_persona("debug") == "tech"
    assert normalize_persona("auto") == "support"


def test_upselling_question_builds_support_plan():
    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="what is the upselling all about?",
        cleaned_intent="what is the upselling all about?",
        metadata={"chat_persona": "support", "chat_persona_effective": "support"},
    )
    plan = build_support_doc_plan(task)
    assert plan.intent_class == "repo.docs.qa"
    assert plan.strategy == "persona"
    assert plan.steps[0].tool == "search_repo_docs"


def test_resolve_tool_plan_uses_persona_support_without_regex():
    config = AlfredConfig(
        repo_knowledge=RepoKnowledgeConfig(enabled=True),
        routing=RoutingConfig(tool_planner_enabled=True),
    )
    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="what is the upselling all about?",
        cleaned_intent="what is the upselling all about?",
        metadata={"chat_persona_effective": "support"},
    )
    context = RouteContext(
        intent=task.cleaned_intent,
        channel_id=task.channel_id,
        repo="",
        mode=RouteMode.INVESTIGATION,
    )
    plan = resolve_tool_plan(
        config,
        task,
        context,
        skill_allowed=["search_repo_docs", "read_repo_doc"],
    )
    assert plan is not None
    assert plan.strategy == "persona"
    assert plan.intent_class == "repo.docs.qa"


def test_infer_persona_from_recent_doc_answer():
    session = ConversationSession(
        key="ui:c1:c1",
        source="ui",
        scope_id="c1",
        thread_id="c1",
        turns=[
            ConversationTurn(role="user", content="what is upselling?"),
            ConversationTurn(
                role="assistant",
                content="Upselling shows complementary products. Source: `handbook/upsell.mdx`",
            ),
        ],
    )
    assert infer_persona_from_session(session, "tell me more") == "support"


def test_user_wants_broader_search():
    assert user_wants_broader_search("search cipher for the handler") is True
    assert user_wants_broader_search("what is upselling per our docs") is False


def test_extract_doc_images_from_mdx():
    content = (
        '# Upsell\n<img className="rounded-lg" src="/images/upsell/image1.png" alt="Add products" />\n'
        "![Step 2](./images/upsell/image2.png)"
    )
    images = extract_doc_images(content, doc_path="handbook/upsell.mdx")
    paths = {item["path"] for item in images}
    assert "images/upsell/image1.png" in paths


def test_append_doc_image_gallery_adds_markdown():
    content = "# Upsell\n\nUse checkout upsells."
    raw = '<img src="/images/upsell/image1.png" alt="Step 1" />'
    answer, images = append_doc_image_gallery(
        content,
        doc_content=raw,
        doc_path="handbook/upsell.mdx",
        repo="Acme/docs",
    )
    assert "Visual steps" in answer
    assert "assets/images/upsell/image1.png" in answer
    assert images
