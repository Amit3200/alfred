"""Fetch PR metadata, diffs, and mirror snippets — data for skill-guided review."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.git.api import GitApiClient
from backend.git.mirror import WorkspaceMirrorManager
from backend.git.sandbox import PathSandboxError, resolve_repo_path
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)

MAX_FILES = 15
MAX_PATCH_CHARS = 3500
MAX_FILE_LINES = 120
MAX_MIRROR_FILE_LINES = 400
MAX_LLM_FILES = 4
MAX_TOTAL_CONTEXT = 12000

_BAD_HALLUCINATION_MARKERS = (
    "magento",
    "set_merchant",
    "set_merchants",
    "restful apis",
    "pep 8 naming conventions",
    "redundant imports",
)


@dataclass
class PrContext:
    """Factual PR data gathered before the investigation agent runs."""

    detail: dict[str, Any]
    files: list[dict[str, Any]]
    mirror_note: str = ""
    snippets: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def gather_pr_context(
    config: AlfredConfig,
    *,
    data_dir: Path,
    workspace_id: str,
    repo: str,
    number: int,
) -> PrContext:
    """Fetch PR metadata, file list, mirror checkout, and key file snippets."""
    client = GitApiClient.from_alfred_config(config)
    detail = client.get_pr(repo, number)
    files = client.get_pr_files(repo, number)
    head = detail.get("head")
    prioritized = _prioritize_files(files)

    mirror_note = ""
    mirror_state = None
    if head:
        try:
            mirror = WorkspaceMirrorManager(config.git, data_dir)
            mirror_state = mirror.ensure_repo(workspace_id, repo, ref=str(head))
            mirror_note = (
                f"Branch `{head}` checked out locally "
                f"(commit `{mirror_state.head_sha or 'unknown'}`)."
            )
        except Exception as exc:
            logger.warning("PR mirror checkout failed: %s", exc)
            mirror_note = f"Local checkout of `{head}` failed: {exc}"

    snippets = _read_key_files_from_mirror(
        config,
        data_dir,
        workspace_id,
        repo,
        head,
        prioritized,
        mirror_state=mirror_state,
    )
    metadata = {
        "repo": detail.get("repo") or repo,
        "number": detail.get("number") or number,
        "head": head,
        "base": detail.get("base"),
        "title": detail.get("title"),
        "url": detail.get("url"),
    }
    return PrContext(
        detail=detail,
        files=files,
        mirror_note=mirror_note,
        snippets=snippets,
        metadata=metadata,
    )


def format_pr_context_for_prompt(ctx: PrContext) -> str:
    """Format gathered PR data for injection alongside the review_pr skill."""
    prioritized = _prioritize_files(ctx.files)
    sections = [
        "## Pre-fetched PR data",
        "Factual context only — follow the review skill for analysis and response format. "
        "Use tools (`grep_repo`, `read_file`, etc.) when you need imports, callers, or more file context.",
        "",
        build_deterministic_pr_overview(ctx.detail, ctx.files),
    ]
    if ctx.mirror_note:
        sections.extend(["", ctx.mirror_note])
    sections.extend(["", _format_file_list(prioritized), "", _format_diffs(prioritized, ctx.snippets)])
    text = "\n".join(sections)
    if len(text) > MAX_TOTAL_CONTEXT:
        text = text[:MAX_TOTAL_CONTEXT] + "\n\n...(truncated for context limit)"
    return text


def build_deterministic_pr_overview(
    detail: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    focus: str = "review",
) -> str:
    """Structured PR summary from API metadata — always factual, no LLM."""
    number = detail.get("number")
    title = detail.get("title") or "Untitled"
    repo = detail.get("repo") or ""
    repo_short = repo.rsplit("/", 1)[-1] if repo else repo
    url = detail.get("url") or ""
    head = detail.get("head") or "?"
    base = detail.get("base") or "?"
    author = detail.get("author") or ""
    body = (detail.get("body") or "").strip()

    lines = [
        f"*PR #{number}: {title}*",
        f"`{repo}` · `{head}` → `{base}`" + (f" · by `{author}`" if author else ""),
    ]
    if url:
        lines.append(url)

    added = [f for f in files if f.get("status") == "added"]
    modified = [f for f in files if f.get("status") == "modified"]
    other = [f for f in files if f.get("status") not in ("added", "modified")]

    lines.extend(["", "**Key changes**"])
    for item in _prioritize_files(files)[:10]:
        path = item.get("filename") or "?"
        status = item.get("status") or "?"
        adds = int(item.get("additions") or 0)
        dels = int(item.get("deletions") or 0)
        lines.append(f"• [{status}] `{path}` (+{adds}/-{dels})")
    if len(files) > 10:
        lines.append(f"• … and {len(files) - 10} more files")

    if focus == "business":
        lines.extend(["", "**What it does**"])
        if body:
            lines.append(_extract_purpose_from_body(body))
        elif added:
            names = ", ".join(f"`{f.get('filename')}`" for f in added[:5])
            lines.append(f"Adds {names} and updates {len(modified)} existing file(s).")
        else:
            lines.append(f"Updates {len(modified)} file(s) in `{repo_short}`.")
        lines.extend(["", "**Business impact**"])
        lines.append(
            _extract_business_impact(body)
            if body
            else "See key changes above — no PR description was provided."
        )
    else:
        lines.extend(["", "**Summary**"])
        if body:
            lines.append(_extract_purpose_from_body(body))
        elif added:
            names = ", ".join(f"`{f.get('filename')}`" for f in added[:5])
            lines.append(f"Adds {names} (+{sum(int(f.get('additions') or 0) for f in added)} lines).")
        else:
            lines.append(f"Changes {len(files)} file(s) across `{repo_short}`.")

        if added:
            lines.extend(["", "**New files**"])
            for item in added:
                path = item.get("filename") or "?"
                lines.append(f"• `{path}` — {int(item.get('additions') or 0)} lines added")

    if body and focus != "business":
        excerpt = _description_excerpt(body)
        if excerpt:
            lines.extend(["", "**From PR description**", excerpt])

    stats = []
    if added:
        stats.append(f"{len(added)} added")
    if modified:
        stats.append(f"{len(modified)} modified")
    if other:
        stats.append(f"{len(other)} other")
    if stats:
        lines.extend(["", f"_({', '.join(stats)}, {len(files)} files total)_"])

    return "\n".join(lines)


def _prioritize_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface new/substantive files before formatting-only edits."""

    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        status = str(item.get("status") or "")
        adds = int(item.get("additions") or 0)
        dels = int(item.get("deletions") or 0)
        total = adds + dels
        if status == "added":
            rank = 0
        elif status == "modified" and total >= 40:
            rank = 1
        elif status == "modified":
            rank = 2
        else:
            rank = 3
        return (rank, -total, str(item.get("filename") or ""))

    return sorted(files, key=sort_key)


def _is_grounded_response(
    text: str,
    detail: dict[str, Any],
    files: list[dict[str, Any]],
) -> bool:
    lower = text.lower()
    if any(marker in lower for marker in _BAD_HALLUCINATION_MARKERS):
        return False

    anchors: list[str] = []
    title = str(detail.get("title") or "")
    for word in title.lower().split():
        if len(word) >= 4 and word.isalpha():
            anchors.append(word)

    repo = str(detail.get("repo") or "")
    if repo:
        anchors.append(repo.rsplit("/", 1)[-1].lower())

    for item in _prioritize_files(files)[:5]:
        path = str(item.get("filename") or "")
        if path:
            anchors.append(path.rsplit("/", 1)[-1].lower())

    if not anchors:
        return True
    return any(anchor in lower for anchor in anchors if anchor)


def _extract_purpose_from_body(body: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return "(no description)"
    chunk: list[str] = []
    for line in lines[:12]:
        if line.startswith("#"):
            continue
        chunk.append(line.lstrip("-*• "))
        if len(" ".join(chunk)) > 280:
            break
    text = " ".join(chunk).strip()
    return text[:600] + ("…" if len(text) > 600 else "")


def _extract_business_impact(body: str) -> str:
    markers = (
        "business",
        "impact",
        "migration",
        "enable",
        "problem",
        "why",
        "purpose",
        "goal",
    )
    hits = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and any(m in line.lower() for m in markers)
    ]
    if hits:
        return "\n".join(f"• {line.lstrip('-*• ')}" for line in hits[:6])
    return _extract_purpose_from_body(body)


def _description_excerpt(body: str) -> str:
    lines = [line.rstrip() for line in body.splitlines()]
    kept: list[str] = []
    for line in lines:
        if not line.strip():
            if kept:
                break
            continue
        kept.append(line)
        if sum(len(x) for x in kept) > 900:
            break
    text = "\n".join(kept).strip()
    return text[:1000] + ("…" if len(text) > 1000 else "")


def _read_key_files_from_mirror(
    config: AlfredConfig,
    data_dir: Path,
    workspace_id: str,
    repo: str,
    head: str | None,
    files: list[dict[str, Any]],
    *,
    mirror_state: Any | None = None,
) -> list[dict[str, str]]:
    """Load full content of the most important changed files from the session mirror."""
    if not head:
        return []

    state = mirror_state
    if state is None:
        try:
            mirror = WorkspaceMirrorManager(config.git, data_dir)
            state = mirror.ensure_repo(workspace_id, repo, ref=str(head))
        except Exception as exc:
            logger.debug("Skipping mirror reads: %s", exc)
            return []

    snippets: list[dict[str, str]] = []
    for item in files[:MAX_LLM_FILES]:
        path = str(item.get("filename") or "").strip()
        if not path:
            continue
        try:
            file_path = resolve_repo_path(state.path, path)
        except PathSandboxError:
            continue
        if not file_path.is_file():
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        limit = MAX_MIRROR_FILE_LINES if item.get("status") == "added" else MAX_FILE_LINES
        content = "\n".join(lines[:limit])
        if len(lines) > limit:
            content += f"\n... ({len(lines) - limit} more lines)"
        snippets.append({"path": path, "content": content, "status": str(item.get("status") or "")})
    return snippets


def _format_file_list(files: list[dict[str, Any]]) -> str:
    if not files:
        return "Changed files: (none returned by API)"
    lines = [f"Changed files ({len(files)} total):"]
    for item in files[:MAX_FILES]:
        path = item.get("filename") or "?"
        status = item.get("status") or "?"
        adds = item.get("additions")
        dels = item.get("deletions")
        stats = ""
        if adds or dels:
            stats = f" (+{adds}/-{dels})"
        lines.append(f"- [{status}] `{path}`{stats}")
    if len(files) > MAX_FILES:
        lines.append(f"- ... and {len(files) - MAX_FILES} more files")
    return "\n".join(lines)


def _format_diffs(
    files: list[dict[str, Any]],
    mirror_snippets: list[dict[str, str]],
) -> str:
    parts: list[str] = []
    total = 0
    for item in files[:MAX_FILES]:
        path = str(item.get("filename") or "")
        patch = str(item.get("patch") or "").strip()
        if not patch:
            continue
        chunk = patch[:MAX_PATCH_CHARS]
        if len(patch) > MAX_PATCH_CHARS:
            chunk += "\n...(patch truncated)"
        block = f"### `{path}`\n```diff\n{chunk}\n```"
        if total + len(block) > MAX_TOTAL_CONTEXT - 2000:
            parts.append("...(remaining diffs omitted for context limit)")
            break
        parts.append(block)
        total += len(block)

    for snippet in mirror_snippets:
        path = snippet["path"]
        block = f"### `{path}` (from branch checkout)\n```\n{snippet['content']}\n```"
        if total + len(block) > MAX_TOTAL_CONTEXT - 500:
            break
        parts.append(block)
        total += len(block)

    if not parts:
        return "Diffs: (no patch data — rely on description and file list)"
    return "Diffs and file contents:\n\n" + "\n\n".join(parts)
