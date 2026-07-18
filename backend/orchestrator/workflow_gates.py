"""Workflow entry gates — clarify context before create-PR and plan commands."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.git.api import resolve_repo_slug
from backend.models.config import AlfredConfig
from backend.models.session import ConversationSession
from backend.models.task import Task

_CREATE_PR_BARE = re.compile(
    r"^(?:@alfred\s+)?(?:alfred\s+)?(?:pr|create(?:\s+a)?\s+pr)\s*$",
    re.IGNORECASE,
)
_PLAN_BARE = re.compile(
    r"^(?:@alfred\s+)?(?:alfred\s+)?plan\s*$",
    re.IGNORECASE,
)
_REPO_SLUG_RE = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
_GITHUB_REPO_RE = re.compile(
    r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
_SHORT_REPO_RE = re.compile(r"\b(?:on|in|for|repo)\s+([a-zA-Z0-9_.-]+)\b", re.IGNORECASE)

_PLAN_HANDOFF = re.compile(
    r"\b(?:implement|execute|continue(?:\s+with)?|start|run|open\s+pr\s+for)\s+(?:the\s+)?plan\b",
    re.IGNORECASE,
)

_TECH_SIGNALS = (
    "error",
    "bug",
    "fix",
    "handler",
    "test",
    "logging",
    "instrument",
    "fp_id",
    "stack trace",
    "exception",
    "implement",
    "add ",
    "update ",
    "refactor",
)


@dataclass
class WorkflowGateResult:
    ready: bool
    message: str = ""
    metadata_patch: dict[str, Any] = field(default_factory=dict)
    enriched_intent: str | None = None


def _workflow_draft(session: ConversationSession | None, key: str) -> dict[str, Any]:
    if not session:
        return {}
    bucket = session.metadata.get(key)
    return dict(bucket) if isinstance(bucket, dict) else {}


def _strip_command_prefix(intent: str) -> str:
    text = intent.strip()
    for prefix in (
        r"^@alfred\s+",
        r"^alfred\s+pr\s*",
        r"^alfred\s+create\s+pr\s*",
        r"^alfred\s+plan\s*",
        r"^create\s+pr\s*",
        r"^pr\s*",
        r"^plan\s*",
    ):
        text = re.sub(prefix, "", text, flags=re.IGNORECASE).strip()
    return text


def _detect_repo(
    intent: str,
    config: AlfredConfig,
    *,
    slack_context: str | None,
    draft: dict[str, Any],
    task: Task,
) -> str | None:
    if draft.get("repo"):
        return str(draft["repo"])
    meta_repo = str(task.metadata.get("repo") or task.metadata.get("repository") or "").strip()
    if meta_repo:
        try:
            return resolve_repo_slug(meta_repo, config.git)
        except ValueError:
            return meta_repo

    haystack = f"{intent}\n{slack_context or ''}"
    match = _GITHUB_REPO_RE.search(haystack)
    if match:
        try:
            return resolve_repo_slug(match.group(1), config.git)
        except ValueError:
            return match.group(1)

    match = _REPO_SLUG_RE.search(intent)
    if match:
        try:
            return resolve_repo_slug(match.group(1), config.git)
        except ValueError:
            pass

    short = _SHORT_REPO_RE.search(intent)
    if short:
        try:
            return resolve_repo_slug(short.group(1), config.git)
        except ValueError:
            pass

    if config.git.main_repo:
        try:
            main = resolve_repo_slug(config.git.main_repo, config.git)
            short_main = main.rsplit("/", 1)[-1].lower()
            if short_main in intent.lower():
                return main
        except ValueError:
            pass
        if len(_strip_command_prefix(intent)) >= 20:
            try:
                return resolve_repo_slug(config.git.main_repo, config.git)
            except ValueError:
                return config.git.main_repo.strip()

    return None


def _goal_text(
    intent: str,
    *,
    slack_context: str | None,
    draft: dict[str, Any],
) -> str:
    if draft.get("goal"):
        return str(draft["goal"]).strip()
    remainder = _strip_command_prefix(intent)
    if remainder and not _CREATE_PR_BARE.match(intent) and not _PLAN_BARE.match(intent):
        return remainder
    if slack_context:
        for line in slack_context.splitlines():
            lower = line.lower()
            if any(sig in lower for sig in _TECH_SIGNALS) and len(line.strip()) > 15:
                return line.strip()[:500]
    return ""


def _merge_draft_from_message(
    draft: dict[str, Any],
    message: str,
    *,
    awaiting: list[str],
) -> dict[str, Any]:
    updated = dict(draft)
    text = message.strip()
    if not text or not awaiting:
        return updated
    field = awaiting[0]
    if field == "repo" and text.lower() in ("use default", "default"):
        updated.pop("awaiting", None)
        return updated
    updated[field] = text
    updated["awaiting"] = awaiting[1:]
    return updated


def _format_questions(title: str, questions: list[str], *, draft: dict[str, Any]) -> str:
    lines = [title, ""]
    if draft.get("repo"):
        lines.append(f"*Repo:* `{draft['repo']}`")
    if draft.get("goal"):
        lines.append(f"*Goal so far:* {draft['goal'][:200]}")
    if draft.get("repo") or draft.get("goal"):
        lines.append("")
    lines.append("I need a bit more context before continuing:")
    for idx, question in enumerate(questions, 1):
        lines.append(f"{idx}. {question}")
    lines.append("")
    lines.append("Reply in this thread with the details — I'll pick up where we left off.")
    return "\n".join(lines)


def _merge_plan_workflow_draft(
    draft: dict[str, Any],
    session: ConversationSession | None,
) -> dict[str, Any]:
    """Inherit goal/repo from a prior @alfred plan turn in the same thread."""
    updated = dict(draft)
    plan_draft = _workflow_draft(session, "workflow_plan")
    if plan_draft.get("goal") and not updated.get("goal"):
        updated["goal"] = plan_draft["goal"]
    if plan_draft.get("repo") and not updated.get("repo"):
        updated["repo"] = plan_draft["repo"]
    return updated


def _goal_from_session_plan(session: ConversationSession | None) -> str:
    if not session:
        return ""
    plan_path = session.metadata.get("plan_file")
    if not plan_path:
        return ""
    from backend.orchestrator.planning import load_plan_file

    content = load_plan_file(str(plan_path))
    if not content:
        return ""
    for line in content.splitlines():
        stripped = line.strip().lstrip("#-* ").strip()
        lower = stripped.lower()
        if len(stripped) < 15:
            continue
        if lower.startswith(("task plan", "checklist", "objective")):
            continue
        if stripped.startswith("- [ ]") or stripped.startswith("- [x]"):
            stripped = stripped[5:].strip()
        if len(stripped) >= 12:
            return stripped[:500]
    return ""


def _has_session_plan(session: ConversationSession | None) -> bool:
    if not session:
        return False
    plan_path = session.metadata.get("plan_file")
    if not plan_path:
        return False
    from backend.orchestrator.planning import load_plan_file

    return load_plan_file(str(plan_path)) is not None


def gate_create_pr(
    task: Task,
    config: AlfredConfig,
    *,
    session: ConversationSession | None,
    slack_context: str | None,
) -> WorkflowGateResult:
    """Return clarifying questions when create-PR context is insufficient."""
    if not config.git.enabled:
        return WorkflowGateResult(
            ready=False,
            message="Git is disabled. Enable Git under Admin → Integrations first.",
        )
    if not config.git.write_enabled:
        return WorkflowGateResult(
            ready=False,
            message=(
                "Git write is disabled. Enable *Phase 1 git write* under Admin → Integrations, "
                "then try `@alfred pr` again."
            ),
        )

    draft = _workflow_draft(session, "workflow_create_pr")
    draft = _merge_plan_workflow_draft(draft, session)
    awaiting = list(draft.get("awaiting") or [])
    if awaiting and session and session.turns:
        draft = _merge_draft_from_message(draft, task.cleaned_intent, awaiting=awaiting)
        if awaiting and awaiting[0] == "repo" and task.cleaned_intent.strip().lower() in ("use default", "default"):
            if config.git.main_repo:
                try:
                    draft["repo"] = resolve_repo_slug(config.git.main_repo, config.git)
                except ValueError:
                    draft["repo"] = config.git.main_repo
                draft["awaiting"] = [a for a in draft.get("awaiting", []) if a != "repo"]

    repo = _detect_repo(task.cleaned_intent, config, slack_context=slack_context, draft=draft, task=task)
    if repo:
        draft["repo"] = repo
    goal = _goal_text(task.cleaned_intent, slack_context=slack_context, draft=draft)
    if goal:
        draft["goal"] = goal
    elif _has_session_plan(session):
        plan_goal = _goal_from_session_plan(session)
        if plan_goal:
            draft["goal"] = plan_goal

    bare = bool(_CREATE_PR_BARE.match(task.cleaned_intent.strip()))
    plan_handoff = bool(_PLAN_HANDOFF.search(task.cleaned_intent))
    questions: list[str] = []
    new_awaiting: list[str] = []

    if not draft.get("repo"):
        if config.git.main_repo:
            questions.append(
                f"Which repository? (default: `{config.git.main_repo}` — reply *use default* or give `owner/repo`)"
            )
        else:
            questions.append("Which repository (`owner/name`, e.g. `YourOrg/cipher`)?")
        new_awaiting.append("repo")

    if not draft.get("goal") or len(str(draft.get("goal") or "")) < 12:
        if bare and _has_session_plan(session):
            plan_goal = _goal_from_session_plan(session)
            if plan_goal:
                draft["goal"] = plan_goal
        if not draft.get("goal") or len(str(draft.get("goal") or "")) < 12:
            questions.append(
                "What should the PR implement? Include the problem, expected behavior, and any test requirements."
            )
            new_awaiting.append("goal")

    if questions and (bare or new_awaiting):
        draft["awaiting"] = new_awaiting
        return WorkflowGateResult(
            ready=False,
            message=_format_questions(
                "*Create PR — need a few details*",
                questions,
                draft=draft,
            ),
            metadata_patch={"workflow_create_pr": draft},
        )

    if not draft.get("repo") or not draft.get("goal"):
        draft["awaiting"] = [k for k in ("repo", "goal") if not draft.get(k)]
        return WorkflowGateResult(
            ready=False,
            message=_format_questions(
                "*Create PR — need a few details*",
                questions or ["What should I implement in the PR?"],
                draft=draft,
            ),
            metadata_patch={"workflow_create_pr": draft},
        )

    plan_note = ""
    if _has_session_plan(session) or plan_handoff:
        plan_note = (
            " Implement the approved task plan from the prior @alfred plan step — follow its checklist."
        )
    enriched = (
        f"Create a draft PR on {draft['repo']}: {draft['goal']}.{plan_note} "
        "Follow the create_pr skill — read code first, add tests, open a draft PR."
    )
    draft.pop("awaiting", None)
    draft["ready"] = True
    metadata_patch: dict[str, Any] = {"workflow_create_pr": draft}
    if session and session.metadata.get("plan_file"):
        metadata_patch["inherit_plan_file"] = session.metadata["plan_file"]
    return WorkflowGateResult(
        ready=True,
        enriched_intent=enriched,
        metadata_patch=metadata_patch,
    )


def gate_plan_task(
    task: Task,
    config: AlfredConfig,
    *,
    session: ConversationSession | None,
    slack_context: str | None,
) -> WorkflowGateResult:
    """Return clarifying questions when plan context is insufficient."""
    draft = _workflow_draft(session, "workflow_plan")
    awaiting = list(draft.get("awaiting") or [])
    if awaiting and session and session.turns:
        draft = _merge_draft_from_message(draft, task.cleaned_intent, awaiting=awaiting)

    goal = _goal_text(task.cleaned_intent, slack_context=slack_context, draft=draft)
    if goal:
        draft["goal"] = goal

    repo = _detect_repo(task.cleaned_intent, config, slack_context=slack_context, draft=draft, task=task)
    if repo:
        draft["repo"] = repo
    elif config.git.main_repo and not draft.get("repo"):
        draft["repo_hint"] = config.git.main_repo

    bare = bool(_PLAN_BARE.match(task.cleaned_intent.strip()))
    questions: list[str] = []
    new_awaiting: list[str] = []

    if not draft.get("goal") or len(str(draft.get("goal") or "")) < 10:
        questions.append(
            "What task should I plan? Describe the goal, constraints, and what success looks like."
        )
        new_awaiting.append("goal")

    if bare or (not draft.get("goal") and new_awaiting):
        draft["awaiting"] = new_awaiting
        return WorkflowGateResult(
            ready=False,
            message=_format_questions(
                "*Plan — need a bit more context*",
                questions,
                draft=draft,
            ),
            metadata_patch={"workflow_plan": draft},
        )

    if not draft.get("goal"):
        draft["awaiting"] = ["goal"]
        return WorkflowGateResult(
            ready=False,
            message=_format_questions(
                "*Plan — what should I plan?*",
                ["Describe the task, problem, or outcome you want a checklist for."],
                draft=draft,
            ),
            metadata_patch={"workflow_plan": draft},
        )

    repo_note = ""
    if draft.get("repo"):
        repo_note = f" Repo context: {draft['repo']}."
    elif draft.get("repo_hint"):
        repo_note = f" Primary repo: {draft['repo_hint']}."
    enriched = f"Create a detailed execution plan for: {draft['goal']}.{repo_note}"
    draft.pop("awaiting", None)
    draft["ready"] = True
    return WorkflowGateResult(
        ready=True,
        enriched_intent=enriched,
        metadata_patch={"workflow_plan": draft},
    )


def build_cli_create_pr_intent(
    context: str | None,
    *,
    repo: str | None,
    interactive: bool,
    config: AlfredConfig,
) -> str:
    """Build intent string for `alfred pr` CLI."""
    if interactive:
        import click

        default_repo = repo or config.git.main_repo or ""
        chosen_repo = click.prompt("Repository (owner/name)", default=default_repo or "")
        goal = click.prompt("What should this PR implement?")
        tests = click.prompt("Tests / edge cases (optional)", default="", show_default=False)
        intent = f"alfred pr on {chosen_repo}: {goal}"
        if tests.strip():
            intent += f" Tests: {tests.strip()}"
        return intent

    parts: list[str] = ["alfred pr"]
    if repo:
        parts.append(f"on {repo}")
    if context and context.strip():
        parts.append(context.strip())
    return " ".join(parts).strip()


def build_cli_plan_intent(
    description: str | None,
    *,
    repo: str | None,
    interactive: bool,
    config: AlfredConfig,
) -> str:
    if interactive:
        import click

        goal = click.prompt("What task should I plan?")
        repo_answer = click.prompt(
            "Repo context (owner/name, optional)",
            default=repo or config.git.main_repo or "",
            show_default=bool(repo or config.git.main_repo),
        )
        intent = f"alfred plan: {goal}"
        if repo_answer.strip():
            intent += f" (repo: {repo_answer.strip()})"
        return intent

    parts = ["alfred plan"]
    if description and description.strip():
        parts.append(description.strip())
    if repo:
        parts.append(f"on {repo}")
    return " ".join(parts).strip()
