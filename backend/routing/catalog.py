"""Build skill catalogs for routing prompts."""

from __future__ import annotations

from backend.routing.playbooks import Playbook, PlaybookStore
from backend.routing.types import RouteMode, SkillCatalogEntry


def playbook_to_catalog_entry(playbook: Playbook) -> SkillCatalogEntry:
    return SkillCatalogEntry(
        name=playbook.name,
        description=playbook.description,
        mode=playbook.mode,
        triggers=tuple(playbook.triggers),
        tools=tuple(playbook.allowed_tools),
        repos=tuple(playbook.repos),
    )


def list_catalog_entries(
    store: PlaybookStore,
    *,
    mode: RouteMode,
    channel_id: str = "",
    repo: str = "",
) -> list[SkillCatalogEntry]:
    """Return routable skills for *mode*, respecting channel/repo filters."""
    repo_lower = repo.strip().lower()
    entries: list[SkillCatalogEntry] = []

    for playbook in store.list_playbooks():
        if not _playbook_visible(playbook, mode, channel_id, repo_lower):
            continue
        entries.append(playbook_to_catalog_entry(playbook))

    return sorted(entries, key=lambda entry: entry.name.lower())


def format_catalog_for_router(
    entries: list[SkillCatalogEntry],
    *,
    mode: RouteMode,
) -> str:
    if not entries:
        return f"(No {mode.value} skills registered.)"
    header = (
        f"## Skill catalog ({mode.value})\n"
        "Pick at most one skill name from this list. Use the exact `name` field."
    )
    lines = [header, ""]
    lines.extend(entry.to_prompt_line() for entry in entries)
    return "\n".join(lines)


def _playbook_visible(
    playbook: Playbook,
    mode: RouteMode,
    channel_id: str,
    repo_lower: str,
) -> bool:
    if mode == RouteMode.INVESTIGATION:
        if playbook.mode not in ("investigation", "workflow"):
            return False
        if not playbook.allowed_tools:
            return False
    elif playbook.mode != "conversational":
        return False

    if playbook.channels and channel_id not in playbook.channels:
        return False

    if playbook.repos and repo_lower:
        matched = False
        for repo in playbook.repos:
            needle = repo.strip().lower()
            if repo_lower == needle or repo_lower.endswith("/" + needle.split("/")[-1]):
                matched = True
                break
        if not matched:
            return False

    return bool(playbook.triggers) or bool(playbook.description)
