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
        if target.is_file() and target.suffix.lower() in {".md", ".markdown", ".txt"}:
            try:
                add_file(spec, target.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
        elif target.is_dir():
            for path in sorted(target.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in {".md", ".markdown", ".txt"}:
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
) -> dict[str, Any]:
    """Index markdown docs from mirror + playbooks; write doc_index.json."""
    rk = config or RepoKnowledgeConfig()
    slug = resolve_main_repo(git) if not repo else repo
    if not slug:
        raise ValueError("main_repo is not configured")

    mirror = shared_mirror_path(data_dir, slug)
    if not mirror.is_dir():
        raise FileNotFoundError(f"Shared mirror for {slug!r} is missing")

    chunks = _collect_mirror_docs(mirror, doc_paths=list(rk.doc_paths), repo_slug=slug)
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
) -> list[dict[str, Any]]:
    """BM25 search over indexed doc chunks."""
    index = load_doc_index(data_dir, repo_slug)
    if not index:
        return []

    chunks = [
        DocChunk.from_dict(item)
        for item in index.get("chunks") or []
        if isinstance(item, dict)
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
