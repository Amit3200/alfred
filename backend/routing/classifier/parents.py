"""Tool parents — first hop of hierarchical prompt routing."""

from __future__ import annotations

from dataclasses import dataclass

from backend.models.config import AlfredConfig


@dataclass(frozen=True)
class ToolParent:
    """A family of tools the router picks before a specific capability."""

    id: str
    description: str
    capabilities: tuple[str, ...]


# Closed parent catalog. Capabilities are fine-grained keys in capabilities.py / intent_classes.
TOOL_PARENTS: tuple[ToolParent, ...] = (
    ToolParent(
        id="jira",
        description=(
            "Atlassian Jira issues: create tickets, search, assign, transition status, "
            "comment, or link a PR. Use when the user names Jira, a project key (TECH-12), "
            "or an issue tracker — not a Slack List board."
        ),
        capabilities=(
            "jira.write.create",
            "jira.write.assign",
            "jira.write.transition",
            "jira.write.comment",
            "jira.write.update",
            "jira.write.link",
            "jira.read.single",
            "jira.read.list",
            "identity.lookup",
        ),
    ),
    ToolParent(
        id="slack_board",
        description=(
            "Slack List board for THIS channel: create/update/search board tasks. "
            "Use when the channel has a linked List and the user says board/task without naming Jira."
        ),
        capabilities=(
            "slack.board.write.create",
            "slack.board.write.update",
            "slack.board.write.comment",
            "slack.board.read.search",
        ),
    ),
    ToolParent(
        id="slack_read",
        description="Read Slack thread or channel history (no board writes).",
        capabilities=("slack.read.thread",),
    ),
    ToolParent(
        id="git",
        description="GitHub PRs, repos, local code search, blame, and opening a pull request.",
        capabilities=("git.pr.review", "git.pr.read", "git.repo.read"),
    ),
    ToolParent(
        id="repo_docs",
        description="Internal docs, runbooks, and repo markdown (BM25), not public web.",
        capabilities=("repo.docs.qa",),
    ),
    ToolParent(
        id="google",
        description="Google Sheets and Google Docs: create, read, write, append.",
        capabilities=("google.write.sheet", "google.read.sheet", "google.write.doc", "google.read.doc"),
    ),
    ToolParent(
        id="aws",
        description="Amazon Athena SQL and CloudWatch Logs Insights (read-only analytics/logs).",
        capabilities=("aws.read.query",),
    ),
    ToolParent(
        id="web",
        description="Public web search for docs, errors, and facts not in the repo or Jira.",
        capabilities=("web.search",),
    ),
    ToolParent(
        id="artifact",
        description="HTML slide decks: save and publish a presentation.",
        capabilities=("artifact.write.deck",),
    ),
    ToolParent(
        id="schedule",
        description="Recurring Alfred jobs (cron): list, create, update, toggle, delete.",
        capabilities=(
            "schedule.write.create",
            "schedule.read.list",
            "schedule.write.toggle",
            "schedule.write.delete",
            "schedule.write.update",
        ),
    ),
    ToolParent(
        id="script",
        description="Curated company scripts under .alfred/scripts/ (list, read, write, run).",
        capabilities=("script.run",),
    ),
    ToolParent(
        id="conversational",
        description="Chat, clarify, or refuse — no tools. Use when the request is ambiguous or social.",
        capabilities=("conversational",),
    ),
)

PARENT_BY_ID: dict[str, ToolParent] = {parent.id: parent for parent in TOOL_PARENTS}


def enabled_parents(config: AlfredConfig, *, slack_board_linked: bool) -> list[ToolParent]:
    """Parents whose integrations are configured for this workspace/channel."""
    out: list[ToolParent] = []
    for parent in TOOL_PARENTS:
        if parent.id == "jira" and not config.jira.enabled:
            continue
        if parent.id == "slack_board" and not (config.slack.enabled and slack_board_linked):
            continue
        if parent.id == "slack_read" and not config.slack.enabled:
            continue
        if parent.id == "git" and not config.git.enabled:
            continue
        if parent.id == "repo_docs" and not (config.repo_knowledge.enabled and config.git.enabled):
            continue
        if parent.id == "google" and not config.google.enabled:
            continue
        if parent.id == "aws" and not config.aws.enabled:
            continue
        if parent.id == "web" and not config.web_search.enabled:
            continue
        if parent.id == "script" and not config.scripts.enabled:
            continue
        out.append(parent)
    if not any(p.id == "conversational" for p in out):
        out.append(PARENT_BY_ID["conversational"])
    return out
