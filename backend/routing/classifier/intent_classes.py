"""Closed intent-class enum for capability routing."""

from __future__ import annotations

from typing import Literal

IntentClass = Literal[
    "jira.read.single",
    "jira.read.list",
    "jira.write.create",
    "jira.write.assign",
    "jira.write.transition",
    "jira.write.comment",
    "jira.write.update",
    "jira.write.link",
    "slack.board.write.create",
    "slack.board.write.update",
    "slack.board.write.comment",
    "slack.board.read.search",
    "repo.docs.qa",
    "artifact.write.deck",
    "google.write.sheet",
    "google.read.sheet",
    "git.pr.review",
    "identity.lookup",
    "git.pr.read",
    "git.repo.read",
    "aws.read.query",
    "web.search",
    "slack.read.thread",
    "google.write.doc",
    "google.read.doc",
    "script.run",
    "schedule.write.create",
    "schedule.read.list",
    "schedule.write.toggle",
    "schedule.write.delete",
    "schedule.write.update",
    "conversational",
    "unknown",
]

INTENT_CLASSES: frozenset[str] = frozenset(
    {
        "jira.read.single",
        "jira.read.list",
        "jira.write.create",
        "jira.write.assign",
        "jira.write.transition",
        "jira.write.comment",
        "jira.write.update",
        "jira.write.link",
        "slack.board.write.create",
        "slack.board.write.update",
        "slack.board.write.comment",
        "slack.board.read.search",
        "repo.docs.qa",
        "artifact.write.deck",
        "google.write.sheet",
        "google.read.sheet",
        "git.pr.review",
        "identity.lookup",
        "git.pr.read",
        "git.repo.read",
        "aws.read.query",
        "web.search",
        "slack.read.thread",
        "google.write.doc",
        "google.read.doc",
        "script.run",
        "schedule.write.create",
        "schedule.read.list",
        "schedule.write.toggle",
        "schedule.write.delete",
        "schedule.write.update",
        "conversational",
        "unknown",
    }
)

# intent_class → capability key in capabilities map
INTENT_TO_CAPABILITY: dict[str, str] = {
    "jira.read.single": "jira.read.single",
    "jira.read.list": "jira.read.list",
    "jira.write.create": "jira.write.create",
    "jira.write.assign": "jira.write.assign",
    "jira.write.transition": "jira.write.transition",
    "jira.write.comment": "jira.write.comment",
    "jira.write.update": "jira.write.update",
    "jira.write.link": "jira.write.link",
    "slack.board.write.create": "slack.board.write.create",
    "slack.board.write.update": "slack.board.write.update",
    "slack.board.write.comment": "slack.board.write.comment",
    "slack.board.read.search": "slack.board.read.search",
    "repo.docs.qa": "repo.docs.qa",
    "artifact.write.deck": "artifact.write.deck",
    "google.write.sheet": "google.write.sheet",
    "google.read.sheet": "google.read.sheet",
    "git.pr.review": "git.pr.review",
    "git.pr.read": "git.pr.read",
    "git.repo.read": "git.repo.read",
    "aws.read.query": "aws.read.query",
    "web.search": "web.search",
    "slack.read.thread": "slack.read.thread",
    "google.write.doc": "google.write.doc",
    "google.read.doc": "google.read.doc",
    "script.run": "script.run",
    "schedule.write.create": "schedule.write.create",
    "schedule.read.list": "schedule.read.list",
    "schedule.write.toggle": "schedule.write.toggle",
    "schedule.write.delete": "schedule.write.delete",
    "schedule.write.update": "schedule.write.update",
    "identity.lookup": "identity.lookup",
}

INTENT_TO_SKILL: dict[str, str] = {
    "jira.read.single": "jira_management",
    "jira.read.list": "jira_management",
    "jira.write.create": "jira_management",
    "jira.write.assign": "jira_management",
    "jira.write.transition": "jira_management",
    "jira.write.comment": "jira_management",
    "jira.write.update": "jira_management",
    "jira.write.link": "jira_management",
    "slack.board.write.create": "slack_board_management",
    "slack.board.write.update": "slack_board_management",
    "slack.board.write.comment": "slack_board_management",
    "slack.board.read.search": "slack_board_management",
    "repo.docs.qa": "repo_knowledge",
    "artifact.write.deck": "html_slides",
    "google.write.sheet": "google_workspace",
    "google.read.sheet": "google_workspace",
    "git.pr.review": "review_pr",
    "git.pr.read": "git_status",
    "git.repo.read": "investigate_bug",
    "aws.read.query": "aws_query",
    "web.search": "web_research",
    "slack.read.thread": "summarize_bugs",
    "google.write.doc": "google_workspace",
    "google.read.doc": "google_workspace",
    "script.run": "investigate_bug",
    "schedule.write.create": "schedule_management",
    "schedule.read.list": "schedule_management",
    "schedule.write.toggle": "schedule_management",
    "schedule.write.delete": "schedule_management",
    "schedule.write.update": "schedule_management",
    "identity.lookup": "jira_management",
}

INTENT_TO_TOOLS: dict[str, tuple[str, ...]] = {
    "jira.read.single": ("get_jira_issue",),
    "jira.read.list": ("jira_search", "list_jira_issues"),
    "jira.write.create": ("jira_create_issue",),
    "jira.write.assign": ("jira_assign_issue",),
    "jira.write.transition": ("transition_jira_issue",),
    "jira.write.comment": ("jira_add_comment",),
    "jira.write.update": ("jira_update_issue",),
    "jira.write.link": ("link_jira_issue",),
    "slack.board.write.create": ("slack_fetch_thread", "slack_board_create_task"),
    "slack.board.write.update": ("slack_board_update_task",),
    "slack.board.write.comment": ("slack_board_comment",),
    "slack.board.read.search": ("slack_board_search_tasks", "slack_board_get_task"),
    "repo.docs.qa": ("search_repo_docs", "read_repo_doc"),
    "artifact.write.deck": ("save_html_deck", "publish_html_artifact"),
    "google.write.sheet": ("google_create_sheet", "google_write_sheet"),
    "google.read.sheet": ("google_read_sheet",),
    "git.pr.review": ("get_pr", "get_pr_changes"),
    "git.pr.read": ("list_my_prs", "list_prs", "get_pr"),
    "git.repo.read": ("grep_repo", "read_file", "query_graph"),
    "aws.read.query": ("athena_query", "cloudwatch_query"),
    "web.search": ("web_search",),
    "slack.read.thread": ("slack_fetch_thread", "slack_fetch_channel_history"),
    "google.write.doc": ("google_create_doc", "google_append_doc"),
    "google.read.doc": ("google_read_doc",),
    "script.run": ("list_company_scripts", "run_company_script"),
    "schedule.write.create": ("create_schedule",),
    "schedule.read.list": ("list_schedules",),
    "schedule.write.toggle": ("toggle_schedule",),
    "schedule.write.delete": ("delete_schedule",),
    "schedule.write.update": ("update_schedule",),
    "identity.lookup": ("lookup_user_identity",),
}


# ToolPlan / GoalSpec still emit some pre-v2 labels. Map both directions.
INTENT_ALIASES: dict[str, str] = {
    "slack.board.create": "slack.board.write.create",
    "slack.board.update": "slack.board.write.update",
    "slack.board.comment": "slack.board.write.comment",
    "slack.board.search": "slack.board.read.search",
    "html_slides": "artifact.write.deck",
}

_CANONICAL_TO_LEGACY: dict[str, str] = {
    "slack.board.write.create": "slack.board.create",
    "slack.board.write.update": "slack.board.update",
    "slack.board.write.comment": "slack.board.comment",
    "slack.board.read.search": "slack.board.search",
    "artifact.write.deck": "html_slides",
}


def canonical_intent_class(value: str) -> str:
    """Map alias or canonical label onto the closed enum (unknown if invalid)."""
    raw = (value or "").strip()
    raw = INTENT_ALIASES.get(raw, raw)
    if raw in INTENT_CLASSES:
        return raw
    return "unknown"


def normalize_intent_class(value: str) -> str:
    return canonical_intent_class(value)


def legacy_intent_class(value: str) -> str:
    """Names still used by ToolPlan, GoalSpec, and session metadata."""
    canonical = canonical_intent_class(value)
    if canonical == "unknown":
        return (value or "").strip()
    return _CANONICAL_TO_LEGACY.get(canonical, canonical)


def is_html_slides_intent(value: str) -> bool:
    return canonical_intent_class(value) == "artifact.write.deck"


def is_slack_board_create_intent(value: str) -> bool:
    return canonical_intent_class(value) == "slack.board.write.create"


def is_slack_board_write_intent_class(value: str) -> bool:
    return canonical_intent_class(value) in {
        "slack.board.write.create",
        "slack.board.write.update",
        "slack.board.write.comment",
    }
