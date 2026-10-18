"""Detect Periskope / inbound-connector intents so chat can call real tools."""

from __future__ import annotations

import re

from backend.integrations.periskope.time_range import looks_like_date_window, resolve_message_window
from backend.models.task import Task
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

_PERISKOPE_RE = re.compile(
    r"\b(periskope|inbound\s+connectors?|connector_(?:list|poll|list_chats|list_tickets|list_tasks|get_messages))\b",
    re.I,
)
_WHATSAPP_RE = re.compile(r"\bwhatsapp\b", re.I)
_CHAT_RE = re.compile(r"\b(chats?|groups?)\b", re.I)
_TICKET_RE = re.compile(r"\b(tickets?)\b", re.I)
_TASK_RE = re.compile(r"\b(tasks?)\b", re.I)
# "pull" is too broad ("pull tickets", prior-turn "I'll pull chats"). Poll only
# when the user asks to poll/replicate/preview the connector feed.
_POLL_RE = re.compile(r"\b(poll|replicate|preview)\b", re.I)
_MESSAGE_RE = re.compile(r"\b(messages?|summar(?:y|ise|ize)|digest)\b", re.I)
_CHAT_ID_RE = re.compile(r"\b(\d{5,}@(?:g|c)\.us)\b", re.I)


def looks_like_connector_request(text: str) -> bool:
    """True when the user is asking Alfred to use Periskope / WhatsApp connector tools."""
    raw = text or ""
    if _PERISKOPE_RE.search(raw):
        return True
    if not _WHATSAPP_RE.search(raw):
        return False
    return bool(
        _CHAT_RE.search(raw)
        or _TICKET_RE.search(raw)
        or _TASK_RE.search(raw)
        or _POLL_RE.search(raw)
        or _MESSAGE_RE.search(raw)
        or _CHAT_ID_RE.search(raw)
    )


def _ok(name: str, allowed: set[str]) -> bool:
    return not allowed or name in allowed


def _intent_text(task: Task) -> str:
    """Latest user utterance only — do not concatenate raw_text (thread history)."""
    return (task.cleaned_intent or task.raw_text or "").strip()


def _window_args(text: str) -> tuple[str, str]:
    return resolve_message_window(intent=text)


def build_connector_tool_plan(
    task: Task,
    *,
    skill_allowed: list[str] | None = None,
) -> ToolPlan | None:
    """Deterministic plan for listing/polling Periskope data (no webhook needed)."""
    text = _intent_text(task)
    if not looks_like_connector_request(text):
        return None
    allowed = set(skill_allowed or [])

    chat_id = ""
    match = _CHAT_ID_RE.search(text)
    if match:
        chat_id = match.group(1)

    if chat_id and _MESSAGE_RE.search(text) and _ok("connector_get_messages", allowed):
        start, end = _window_args(text)
        args: dict[str, str] = {"chat_id": chat_id}
        if start:
            args["start_time"] = start
        if end:
            args["end_time"] = end
        return ToolPlan(
            goal=f"Fetch WhatsApp messages for {chat_id}",
            confidence=0.96,
            tools_needed=["connector_get_messages"],
            steps=[ToolPlanStep("connector_get_messages", "fetch chat messages", args)],
            intent_class="connector.read.messages",
            strategy="rules",
        )

    if (_MESSAGE_RE.search(text) or looks_like_date_window(text)) and _ok(
        "connector_get_messages", allowed
    ):
        start, end = _window_args(text)
        args = {}
        if start:
            args["start_time"] = start
        if end:
            args["end_time"] = end
        tools = ["connector_get_messages"]
        steps = [ToolPlanStep("connector_get_messages", "fetch messages for window", args)]
        if _CHAT_RE.search(text) and _ok("connector_list_chats", allowed):
            tools.append("connector_list_chats")
            steps.append(ToolPlanStep("connector_list_chats", "resolve chat names"))
        return ToolPlan(
            goal="Fetch Periskope WhatsApp messages and summarize by chat",
            confidence=0.96,
            tools_needed=tools,
            steps=steps,
            intent_class="connector.read.messages",
            strategy="rules",
        )

    if _TICKET_RE.search(text) and _ok("connector_list_tickets", allowed):
        return ToolPlan(
            goal="List Periskope tickets",
            confidence=0.95,
            tools_needed=["connector_list_tickets"],
            steps=[ToolPlanStep("connector_list_tickets", "list tickets")],
            intent_class="connector.read.tickets",
            strategy="rules",
        )

    if _TASK_RE.search(text) and not _TICKET_RE.search(text) and _ok("connector_list_tasks", allowed):
        return ToolPlan(
            goal="List Periskope tasks",
            confidence=0.94,
            tools_needed=["connector_list_tasks"],
            steps=[ToolPlanStep("connector_list_tasks", "list tasks")],
            intent_class="connector.read.tasks",
            strategy="rules",
        )

    if _CHAT_RE.search(text) and _ok("connector_list_chats", allowed):
        return ToolPlan(
            goal="List Periskope WhatsApp chats",
            confidence=0.96,
            tools_needed=["connector_list_chats"],
            steps=[ToolPlanStep("connector_list_chats", "list chats")],
            intent_class="connector.read.chats",
            strategy="rules",
        )

    if _POLL_RE.search(text) and _ok("connector_poll", allowed):
        replicate = bool(re.search(r"\breplicate\b", text, re.I))
        return ToolPlan(
            goal="Poll Periskope over REST (no webhook)",
            confidence=0.95,
            tools_needed=["connector_poll"],
            steps=[
                ToolPlanStep(
                    "connector_poll",
                    "poll connector",
                    {"replicate": replicate, "kinds": ["tickets", "tasks", "chats"]},
                )
            ],
            intent_class="connector.read.poll",
            strategy="rules",
        )

    if _ok("connector_list", allowed):
        return ToolPlan(
            goal="List inbound connectors",
            confidence=0.9,
            tools_needed=["connector_list"],
            steps=[ToolPlanStep("connector_list", "list connectors")],
            intent_class="connector.read.list",
            strategy="rules",
        )
    return None
