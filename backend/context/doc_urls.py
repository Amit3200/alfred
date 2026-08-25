"""Map indexed doc paths to public documentation URLs."""

from __future__ import annotations

from typing import Any

DEFAULT_DOCS_PUBLIC_BASE: dict[str, str] = {
    "flexype/docs": "https://docs.flexype.io",
}

_STRIP_SUFFIXES = (".mdx", ".markdown", ".md")


def _normalize_slug(repo: str) -> str:
    return (repo or "").strip().strip("/").lower()


def docs_public_base_url(repo: str, *, config: Any | None = None) -> str:
    slug = _normalize_slug(repo)
    if not slug:
        return ""
    if config is not None:
        git = getattr(config, "git", None)
        if git is not None:
            from backend.context.repo_profiles import profile_for_repo

            profile = profile_for_repo(git, (repo or "").strip())
            extra = str(getattr(profile, "docs_public_base_url", "") or "").strip() if profile else ""
            if extra:
                return extra.rstrip("/")
    return DEFAULT_DOCS_PUBLIC_BASE.get(slug, "").rstrip("/")


def public_doc_url(
    path: str,
    *,
    repo: str = "",
    config: Any | None = None,
    base: str = "",
) -> str:
    """`platforms/hydrogen.mdx` on FlexyPe/docs → https://docs.flexype.io/platforms/hydrogen"""
    root = (base or docs_public_base_url(repo, config=config)).rstrip("/")
    rel = (path or "").replace("\\", "/").strip().lstrip("/")
    if not root or not rel:
        return ""
    lower = rel.lower()
    for suffix in _STRIP_SUFFIXES:
        if lower.endswith(suffix):
            rel = rel[: -len(suffix)]
            break
    if rel.endswith("/index"):
        rel = rel[: -len("/index")]
    elif rel == "index":
        return root
    return f"{root}/{rel}"


def attach_public_doc_urls(
    items: list[dict[str, Any]],
    *,
    repo: str = "",
    config: Any | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        hit = dict(item)
        slug = str(hit.get("repo") or repo or "")
        url = public_doc_url(str(hit.get("path") or ""), repo=slug, config=config)
        if url:
            hit["url"] = url
        out.append(hit)
    return out
