"""Extract and resolve documentation images from mirrored MD/MDX files."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

_IMG_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_IMG_HTML_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)


def normalize_doc_asset_path(raw: str, *, doc_path: str = "") -> str | None:
    """Map MDX/Markdown image refs to a mirror-relative asset path."""
    src = (raw or "").strip()
    if not src or src.startswith(("http://", "https://", "data:")):
        return None
    if src.startswith("/"):
        return src.lstrip("/")
    doc_dir = PurePosixPath(doc_path).parent
    if str(doc_dir) in {"", "."}:
        return src.lstrip("/")
    joined = (doc_dir / src).as_posix()
    return joined.lstrip("/")


def extract_doc_images(content: str, *, doc_path: str = "") -> list[dict[str, str]]:
    """Return unique image refs found in doc content."""
    seen: set[str] = set()
    images: list[dict[str, str]] = []

    def add(raw: str, alt: str = "") -> None:
        path = normalize_doc_asset_path(raw, doc_path=doc_path)
        if not path or path in seen:
            return
        seen.add(path)
        images.append({"path": path, "alt": alt or path.rsplit("/", 1)[-1]})

    for match in _IMG_MD_RE.finditer(content or ""):
        add(match.group(2), match.group(1))
    for match in _IMG_HTML_RE.finditer(content or ""):
        add(match.group(1))

    return images


def doc_asset_api_path(repo_slug: str, asset_path: str) -> str:
    repo = quote(repo_slug, safe="")
    path = quote(asset_path.lstrip("/"), safe="/")
    return f"/api/repo-context/knowledge/{repo}/assets/{path}"


def append_doc_image_gallery(
    answer: str,
    *,
    doc_content: str,
    doc_path: str,
    repo: str,
    max_images: int = 6,
) -> tuple[str, list[dict[str, str]]]:
    """Append markdown image gallery when the doc contains step screenshots."""
    images = extract_doc_images(doc_content, doc_path=doc_path)
    if not images:
        return answer, []

    gallery_lines = ["", "## Visual steps", ""]
    rendered: list[dict[str, str]] = []
    for item in images[:max_images]:
        api_path = doc_asset_api_path(repo, item["path"]) if repo else item["path"]
        alt = item.get("alt") or "Documentation screenshot"
        gallery_lines.append(f"![{alt}]({api_path})")
        gallery_lines.append("")
        rendered.append({**item, "url": api_path, "alt": alt})

    if any(api_path in answer for api_path in (img["url"] for img in rendered)):
        return answer, rendered
    return answer.rstrip() + "\n".join(gallery_lines), rendered


def build_doc_answer_payload(
    *,
    text: str,
    doc_path: str,
    repo: str,
    doc_content: str,
) -> dict[str, Any]:
    final_text, images = append_doc_image_gallery(
        text,
        doc_content=doc_content,
        doc_path=doc_path,
        repo=repo,
    )
    return {
        "text": final_text,
        "doc_path": doc_path,
        "repo": repo,
        "images": images,
    }
