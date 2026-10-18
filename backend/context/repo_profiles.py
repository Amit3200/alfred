"""Resolve configured repository roles and knowledge-base flags."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.context.doc_index import load_doc_index
from backend.context.generator import resolve_main_repo, shared_mirror_path
from backend.context.graphify import graph_json_path, graph_summary
from backend.integrations.git.api import resolve_repo_slug
from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile


def normalize_repo_slug(raw: str, git: GitConfig) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return resolve_repo_slug(text, git)
    except ValueError:
        if "/" in text:
            return text.strip("/")
        return None


def profile_map(git: GitConfig) -> dict[str, GitRepoProfile]:
    out: dict[str, GitRepoProfile] = {}
    for profile in git.repo_profiles:
        slug = normalize_repo_slug(profile.repo, git)
        if slug:
            out[slug] = profile
    return out


def profile_for_repo(git: GitConfig, repo_slug: str) -> GitRepoProfile | None:
    return profile_map(git).get(repo_slug)


def effective_doc_index(profile: GitRepoProfile) -> bool:
    if profile.doc_index is not None:
        return profile.doc_index
    return profile.role == "docs"


def effective_graphify(profile: GitRepoProfile, *, graphify_enabled: bool) -> bool:
    if not graphify_enabled:
        return False
    if profile.graphify is not None:
        return profile.graphify
    return profile.role == "docs"


def list_configured_repos(git: GitConfig) -> list[str]:
    """All repo slugs Alfred should mirror or show in knowledge UI."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add(raw: str) -> None:
        slug = normalize_repo_slug(raw, git)
        if not slug:
            return
        key = slug.lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(slug)

    main = resolve_main_repo(git)
    if main:
        add(main)
    for repo in git.repos:
        add(repo)
    for profile in git.repo_profiles:
        add(profile.repo)
    return ordered


def should_doc_index_on_sync(config: AlfredConfig, repo_slug: str) -> bool:
    if not config.repo_knowledge.enabled or not config.repo_knowledge.index_on_sync:
        return False
    profile = profile_for_repo(config.git, repo_slug)
    if profile:
        return effective_doc_index(profile)
    return True


def should_graphify_on_sync(config: AlfredConfig, repo_slug: str) -> bool:
    profile = profile_for_repo(config.git, repo_slug)
    if profile:
        return effective_graphify(profile, graphify_enabled=config.git.graphify_enabled)
    if not config.git.graphify_enabled:
        return False
    main = resolve_main_repo(config.git)
    return repo_slug == main


def docs_only_query(query: str) -> bool:
    """User explicitly asked for product/handbook docs — never search code/playbooks first."""
    lower = (query or "").lower()
    return any(
        phrase in lower
        for phrase in (
            "as per our docs",
            "as per the docs",
            "as per docs",
            "per our docs",
            "refer to doc",
            "refer to the doc",
            "refer to our doc",
            "from our docs",
            "our documentation",
            "our docs",
            "handbook",
        )
    )


def knowledge_doc_repo_slugs(config: AlfredConfig, data_dir: Path) -> list[str]:
    """Documentation-role repos only (e.g. Acme/docs)."""
    slugs: list[str] = []
    for slug in list_configured_repos(config.git):
        profile = profile_for_repo(config.git, slug)
        if not profile or profile.role != "docs":
            continue
        if not effective_doc_index(profile):
            continue
        if load_doc_index(data_dir, slug):
            slugs.append(slug)
    return slugs


def knowledge_tech_doc_repo_slugs(config: AlfredConfig, data_dir: Path) -> list[str]:
    """Code-role repos with indexed playbooks/runbooks (e.g. Acme/app)."""
    slugs: list[str] = []
    main = resolve_main_repo(config.git)
    for slug in list_configured_repos(config.git):
        profile = profile_for_repo(config.git, slug)
        if profile and profile.role == "docs":
            continue
        if profile and not effective_doc_index(profile):
            continue
        if not load_doc_index(data_dir, slug):
            continue
        tag_set = {t.strip().lower() for t in (profile.tags if profile else []) if t.strip()}
        if profile and profile.role == "code":
            slugs.append(slug)
        elif tag_set & {"playbook", "runbook", "tech", "code"}:
            slugs.append(slug)
        elif main and slug == main:
            slugs.append(slug)
    # Preserve order, dedupe
    seen: set[str] = set()
    ordered: list[str] = []
    for slug in slugs:
        key = slug.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(slug)
    if ordered:
        return ordered
    if main and load_doc_index(data_dir, main):
        return [main]
    return []


def doc_search_repo_slugs(config: AlfredConfig, data_dir: Path) -> list[str]:
    """Repos eligible for doc search — docs-role first, skip disabled profiles."""
    docs_slugs: list[str] = []
    other_slugs: list[str] = []
    for slug in list_configured_repos(config.git):
        profile = profile_for_repo(config.git, slug)
        if profile and not effective_doc_index(profile):
            continue
        if not load_doc_index(data_dir, slug):
            continue
        if profile and profile.role == "docs":
            docs_slugs.append(slug)
        else:
            other_slugs.append(slug)
    ordered = docs_slugs + other_slugs
    if ordered:
        return ordered
    main = resolve_main_repo(config.git)
    return [main] if main and load_doc_index(data_dir, main) else []


def _mirror_present(data_dir: Path, repo_slug: str) -> bool:
    mirror = shared_mirror_path(data_dir, repo_slug)
    return mirror.is_dir() and any(mirror.iterdir())


def _doc_index_entry(data_dir: Path, repo_slug: str) -> dict[str, Any]:
    index = load_doc_index(data_dir, repo_slug)
    if not index:
        return {
            "indexed": False,
            "chunk_count": 0,
            "generated_at": None,
            "head_sha": None,
        }
    return {
        "indexed": True,
        "chunk_count": int(index.get("chunk_count") or 0),
        "generated_at": index.get("generated_at"),
        "head_sha": index.get("head_sha"),
    }


def _graph_entry(data_dir: Path, repo_slug: str) -> dict[str, Any]:
    graph_path = graph_json_path(data_dir, repo_slug)
    summary = graph_summary(data_dir, repo_slug)
    return {
        "present": graph_path is not None,
        "node_count": summary.get("node_count", 0),
        "edge_count": summary.get("edge_count", 0),
    }


def doc_paths_for_repo(config: AlfredConfig, repo_slug: str) -> list[str]:
    """Mirror paths to scan when building the doc index for a repository."""
    profile = profile_for_repo(config.git, repo_slug)
    if profile and profile.role == "docs":
        return ["."]
    return list(config.repo_knowledge.doc_paths)


def knowledge_base_status(data_dir: Path, config: AlfredConfig) -> dict[str, Any]:
    """Admin payload listing each configured repo and its knowledge state."""
    profiles = profile_map(config.git)
    entries: list[dict[str, Any]] = []
    for slug in list_configured_repos(config.git):
        profile = profiles.get(slug)
        role = profile.role if profile else ("code" if slug == resolve_main_repo(config.git) else "code")
        doc_flag = effective_doc_index(profile) if profile else should_doc_index_on_sync(config, slug)
        graph_flag = (
            effective_graphify(profile, graphify_enabled=config.git.graphify_enabled)
            if profile
            else should_graphify_on_sync(config, slug)
        )
        entries.append(
            {
                "repo": slug,
                "role": role,
                "doc_index": doc_flag,
                "graphify": graph_flag,
                "tags": list(profile.tags) if profile and profile.tags else [],
                "mirror_present": _mirror_present(data_dir, slug),
                "doc": _doc_index_entry(data_dir, slug),
                "graph": _graph_entry(data_dir, slug),
                "is_main_repo": slug == resolve_main_repo(config.git),
            }
        )
    return {
        "graphify_enabled": config.git.graphify_enabled,
        "repo_knowledge_enabled": config.repo_knowledge.enabled,
        "index_on_sync": config.repo_knowledge.index_on_sync,
        "repos": entries,
    }
