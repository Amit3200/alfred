"""BM25 doc index over mirrored markdown and Alfred playbooks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.context.generator import shared_mirror_path, resolve_main_repo
from backend.models.config import AlfredConfig, GitConfig, RepoKnowledgeConfig
from backend.paths import bundled_skills_dir, playbooks_dir, repo_context_dir

logger = logging.getLogger(__name__)

INDEX_NAME = "doc_index.json"
_DOC_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".mdx"})
_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        ".next",
        "coverage",
        "vendor",
        "__pycache__",
        ".venv",
        "venv",
        "graphify-out",
    }
)
_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 200

_DOC_QUERY_STOPWORDS = frozenset(
    {
        "how",
        "can",
        "could",
        "would",
        "should",
        "do",
        "does",
        "did",
        "we",
        "you",
        "your",
        "our",
        "have",
        "has",
        "had",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "the",
        "a",
        "an",
        "and",
        "or",
        "with",
        "for",
        "in",
        "to",
        "of",
        "on",
        "at",
        "it",
        "this",
        "that",
        "what",
        "when",
        "where",
        "why",
        "who",
        "which",
        "about",
        "flexype",
        "docs",
        "doc",
        "documentation",
        "handbook",
        "integration",
        "integrations",
        "integrate",
        "integrated",
        "configure",
        "configured",
        "configuration",
        "setup",
        "set",
        "up",
        "using",
        "use",
        "supported",
        "support",
        "available",
        "work",
        "works",
        "working",
        "please",
        "tell",
        "explain",
        "show",
        "find",
        "get",
        "give",
        "me",
        "my",
    }
)


@dataclass(frozen=True)
class DocChunk:
    chunk_id: str
    path: str
    title: str
    text: str
    source: str
    start_line: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.chunk_id,
            "path": self.path,
            "title": self.title,
            "text": self.text,
            "source": self.source,
            "start_line": self.start_line,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocChunk:
        return cls(
            chunk_id=str(data.get("id") or ""),
            path=str(data.get("path") or ""),
            title=str(data.get("title") or ""),
            text=str(data.get("text") or ""),
            source=str(data.get("source") or ""),
            start_line=int(data.get("start_line") or 1),
        )


def doc_index_path(data_dir: Path, repo_slug: str) -> Path:
    return repo_context_dir(data_dir, repo_slug) / INDEX_NAME


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def significant_query_tokens(query: str) -> list[str]:
    """Product/feature tokens from a support question (stopwords removed)."""
    return [token for token in _tokenize(query) if token not in _DOC_QUERY_STOPWORDS and len(token) >= 3]


def _normalize_match_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _token_matches_field(token: str, field: str) -> bool:
    normalized_field = _normalize_match_text(field)
    normalized_token = _normalize_match_text(token)
    if not normalized_token or not normalized_field:
        return False
    if normalized_token in normalized_field or normalized_field in normalized_token:
        return True
    if len(normalized_token) >= 4 and normalized_token[:4] in normalized_field:
        return True
    return False


def doc_hit_matches_query(hit: dict[str, Any], query: str) -> bool:
    """True when a BM25 hit actually relates to the product/feature asked about."""
    entities = significant_query_tokens(query)
    if not entities:
        return True

    path = str(hit.get("path") or "")
    title = str(hit.get("title") or "")
    excerpt = str(hit.get("excerpt") or "")
    combined = f"{path} {title} {excerpt}"

    joined = "".join(entities)
    if _token_matches_field(joined, combined):
        return True

    matched = sum(1 for token in entities if _token_matches_field(token, combined))
    if len(entities) == 1:
        return matched >= 1
    return matched >= len(entities)


def describe_missing_doc_topic(query: str) -> str:
    entities = significant_query_tokens(query)
    if not entities:
        return "that topic"
    if len(entities) == 1:
        return entities[0]
    return " ".join(entities)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _chunk_markdown(path: str, text: str, *, source: str) -> list[DocChunk]:
    if not text.strip():
        return []

    title = path.rsplit("/", 1)[-1]
    for line in text.splitlines()[:12]:
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip() or title
            break

    chunks: list[DocChunk] = []
    body = text.strip()
    if len(body) <= _CHUNK_CHARS:
        chunks.append(
            DocChunk(
                chunk_id=f"{path}#0",
                path=path,
                title=title,
                text=body,
                source=source,
                start_line=1,
            )
        )
        return chunks

    start = 0
    idx = 0
    while start < len(body):
        end = min(len(body), start + _CHUNK_CHARS)
        piece = body[start:end].strip()
        if piece:
            line_no = body[:start].count("\n") + 1
            chunks.append(
                DocChunk(
                    chunk_id=f"{path}#{idx}",
                    path=path,
                    title=title,
                    text=piece,
                    source=source,
                    start_line=line_no,
                )
            )
            idx += 1
        if end >= len(body):
            break
        start = max(end - _CHUNK_OVERLAP, start + 1)
    return chunks


def _collect_mirror_docs(
    mirror: Path,
    *,
    doc_paths: list[str],
    repo_slug: str,
) -> list[DocChunk]:
    chunks: list[DocChunk] = []
    seen: set[str] = set()

    def add_file(rel: str, content: str) -> None:
        if rel in seen or not content.strip():
            return
        seen.add(rel)
        chunks.extend(_chunk_markdown(rel, content, source=f"mirror:{repo_slug}"))

    for spec in doc_paths:
        spec = spec.strip().strip("/")
        if not spec:
            continue
        target = mirror / spec
        if target.is_file() and target.suffix.lower() in _DOC_SUFFIXES:
            try:
                add_file(spec, target.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
        elif spec in {".", "*"}:
            for path in sorted(mirror.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in _DOC_SUFFIXES:
                    continue
                if any(part in _SKIP_DIR_NAMES for part in path.parts):
                    continue
                rel = path.relative_to(mirror).as_posix()
                try:
                    add_file(rel, path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
        elif target.is_dir():
            for path in sorted(target.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in _DOC_SUFFIXES:
                    continue
                if any(part in _SKIP_DIR_NAMES for part in path.parts):
                    continue
                rel = path.relative_to(mirror).as_posix()
                try:
                    add_file(rel, path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue

    return chunks


def _collect_playbook_docs(data_dir: Path) -> list[DocChunk]:
    chunks: list[DocChunk] = []
    roots = [playbooks_dir(data_dir), bundled_skills_dir()]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            rel = f"playbooks/{path.relative_to(root).as_posix()}"
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chunks.extend(_chunk_markdown(rel, text, source="playbook"))
    return chunks


def build_doc_index(
    data_dir: Path,
    git: GitConfig,
    *,
    repo: str | None = None,
    config: RepoKnowledgeConfig | None = None,
    alfred_config: AlfredConfig | None = None,
) -> dict[str, Any]:
    """Index markdown docs from mirror + playbooks; write doc_index.json."""
    rk = config or RepoKnowledgeConfig()
    slug = resolve_main_repo(git) if not repo else repo
    if not slug:
        raise ValueError("main_repo is not configured")

    mirror = shared_mirror_path(data_dir, slug)
    if not mirror.is_dir():
        raise FileNotFoundError(f"Shared mirror for {slug!r} is missing")

    if alfred_config is not None:
        from backend.context.repo_profiles import doc_paths_for_repo

        doc_paths = doc_paths_for_repo(alfred_config, slug)
    else:
        doc_paths = list(rk.doc_paths)

    chunks = _collect_mirror_docs(mirror, doc_paths=doc_paths, repo_slug=slug)
    if alfred_config is not None:
        from backend.context.repo_profiles import profile_for_repo

        profile = profile_for_repo(alfred_config.git, slug)
        if profile and profile.role == "docs":
            chunks.extend(_collect_playbook_docs(data_dir))
    elif slug == resolve_main_repo(git):
        chunks.extend(_collect_playbook_docs(data_dir))

    from backend.context.generator import _head_sha

    head_sha = _head_sha(mirror)
    manifest = {
        "repo": slug,
        "head_sha": head_sha,
        "generated_at": _now_iso(),
        "chunk_count": len(chunks),
        "chunks": [c.to_dict() for c in chunks],
    }
    out = doc_index_path(data_dir, slug)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Built doc index for %s: %d chunks", slug, len(chunks))
    return manifest


def load_doc_index(data_dir: Path, repo_slug: str) -> dict[str, Any] | None:
    path = doc_index_path(data_dir, repo_slug)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def list_indexed_docs(data_dir: Path, repo_slug: str) -> list[dict[str, str]]:
    index = load_doc_index(data_dir, repo_slug)
    if not index:
        return []
    paths: dict[str, str] = {}
    for raw in index.get("chunks") or []:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or "")
        if path and path not in paths:
            paths[path] = str(raw.get("title") or path)
    return [{"path": p, "title": t} for p, t in sorted(paths.items())]


def search_repo_docs(
    data_dir: Path,
    repo_slug: str,
    query: str,
    *,
    limit: int = 8,
    exclude_path_prefixes: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """BM25 search over indexed doc chunks."""
    index = load_doc_index(data_dir, repo_slug)
    if not index:
        return []
    return _search_index_chunks(
        index,
        query,
        limit=limit,
        exclude_path_prefixes=exclude_path_prefixes,
    )


def _playbook_paths_allowed(query: str) -> bool:
    lower = (query or "").lower()
    return any(token in lower for token in ("playbook", "runbook", "investigate_bug", "investigation"))


def pick_best_doc_hit(hits: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    """Prefer handbook/product docs that match the asked-about entity."""
    if not hits:
        return None
    relevant = [hit for hit in hits if doc_hit_matches_query(hit, query)]
    if not relevant:
        return None

    allow_playbooks = _playbook_paths_allowed(query)
    lower = (query or "").lower()
    ranked: list[tuple[float, dict[str, Any]]] = []
    for hit in relevant:
        path = str(hit.get("path") or "")
        title = str(hit.get("title") or "")
        score = float(hit.get("score") or 0)
        if path.startswith("playbooks/") and not allow_playbooks:
            score -= 10.0
        if path.startswith(("handbook/", "integrations/", "docs/", "platforms/")):
            score += 2.0
        for token in significant_query_tokens(query):
            if _token_matches_field(token, path) or _token_matches_field(token, title):
                score += 8.0
            elif _token_matches_field(token, str(hit.get("excerpt") or "")):
                score += 4.0
        for token in ("upsell", "google ads", "configure", "configuration"):
            if token in lower and token.replace(" ", "") in path.lower().replace("_", "").replace("-", ""):
                score += 3.0
        ranked.append((score, hit))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def search_all_repo_docs(
    data_dir: Path,
    repo_slugs: list[str],
    query: str,
    *,
    limit: int = 8,
    exclude_path_prefixes: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Search multiple repo indexes and merge by score."""
    merged: list[dict[str, Any]] = []
    per_repo = max(1, limit // max(len(repo_slugs), 1))
    for slug in repo_slugs:
        hits = search_repo_docs(
            data_dir,
            slug,
            query,
            limit=per_repo,
            exclude_path_prefixes=exclude_path_prefixes,
        )
        for hit in hits:
            hit = {**hit, "repo": slug}
            merged.append(hit)
    merged.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return merged[:limit]


def _search_index_chunks(
    index: dict[str, Any],
    query: str,
    *,
    limit: int,
    exclude_path_prefixes: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    chunks = [
        DocChunk.from_dict(item)
        for item in index.get("chunks") or []
        if isinstance(item, dict)
    ]
    if exclude_path_prefixes:
        chunks = [
            chunk
            for chunk in chunks
            if not any(str(chunk.path).startswith(prefix) for prefix in exclude_path_prefixes)
        ]
    if not chunks:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("rank-bm25 not installed — doc search unavailable")
        return []

    corpus = [_tokenize(f"{c.title} {c.path} {c.text}") for c in chunks]
    model = BM25Okapi(corpus)
    scores = list(model.get_scores(query_tokens))
    ranked = sorted(
        zip(scores, chunks, strict=False),
        key=lambda item: item[0],
        reverse=True,
    )

    results: list[dict[str, Any]] = []
    for score, chunk in ranked[:limit]:
        excerpt = chunk.text.strip()
        if len(excerpt) > 500:
            excerpt = excerpt[:500].rstrip() + "…"
        results.append(
            {
                "path": chunk.path,
                "title": chunk.title,
                "source": chunk.source,
                "score": round(float(score), 3),
                "start_line": chunk.start_line,
                "excerpt": excerpt,
                "chunk_id": chunk.chunk_id,
            }
        )
    return results


def read_indexed_doc(
    data_dir: Path,
    git: GitConfig,
    repo_slug: str,
    doc_path: str,
    *,
    max_chars: int = 12000,
) -> dict[str, Any]:
    """Read a doc from mirror or playbook roots."""
    rel = doc_path.strip().lstrip("/")
    if not rel or ".." in Path(rel).parts:
        raise ValueError("Invalid doc path")

    if rel.startswith("playbooks/"):
        inner = rel[len("playbooks/") :]
        for root in (playbooks_dir(data_dir), bundled_skills_dir()):
            candidate = root / inner
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                truncated = len(text) > max_chars
                if truncated:
                    text = text[:max_chars].rstrip() + "\n\n...(truncated)"
                return {"path": rel, "title": candidate.name, "content": text, "truncated": truncated}

    mirror = shared_mirror_path(data_dir, repo_slug)
    candidate = (mirror / rel).resolve()
    if mirror.resolve() not in candidate.parents and candidate != mirror.resolve():
        raise ValueError("Doc path escapes mirror root")
    if not candidate.is_file():
        raise FileNotFoundError(f"Document not found: {rel}")

    text = candidate.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars].rstrip() + "\n\n...(truncated)"
    return {"path": rel, "title": candidate.name, "content": text, "truncated": truncated}


def doc_index_status(data_dir: Path, config: AlfredConfig) -> dict[str, Any]:
    slug = resolve_main_repo(config.git)
    if not slug:
        return {"configured": False, "repo": "", "chunk_count": 0, "generated_at": None}
    index = load_doc_index(data_dir, slug)
    if not index:
        return {
            "configured": True,
            "repo": slug,
            "chunk_count": 0,
            "generated_at": None,
            "indexed": False,
        }
    return {
        "configured": True,
        "repo": slug,
        "chunk_count": int(index.get("chunk_count") or 0),
        "generated_at": index.get("generated_at"),
        "head_sha": index.get("head_sha"),
        "indexed": True,
    }
