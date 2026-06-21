"""Fetch and cache public web pages referenced by domain playbooks."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import requests

if TYPE_CHECKING:
    from backend.ingress.playbooks import Playbook

logger = logging.getLogger(__name__)

DEFAULT_TTL_MINUTES = 60
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_URL_TEXT_CHARS = 8000
MAX_TOTAL_DYNAMIC_CHARS = 12_000
REQUEST_TIMEOUT_SECONDS = 12
USER_AGENT = "AlfredPlaybookFetcher/1.0 (+local-first assistant)"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        raw = " ".join(self._chunks)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def playbook_url_cache_dir(data_dir: Path) -> Path:
    path = data_dir / "cache" / "playbook_urls"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_fetch_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"https"}:
        raise ValueError(f"Only https URLs are allowed: {url!r}")
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {url!r}")
    host = parsed.hostname or ""
    lowered = host.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"} or lowered.endswith(".local"):
        raise ValueError(f"Local URLs are not allowed: {url!r}")
    if lowered.startswith("127.") or lowered.startswith("10."):
        raise ValueError(f"Private URLs are not allowed: {url!r}")
    if lowered.startswith("192.168.") or lowered.startswith("169.254."):
        raise ValueError(f"Private URLs are not allowed: {url!r}")
    if lowered.startswith("172."):
        parts = lowered.split(".")
        if len(parts) > 1 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            raise ValueError(f"Private URLs are not allowed: {url!r}")
    return parsed.geturl()


def html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text()


def _cache_path(data_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return playbook_url_cache_dir(data_dir) / f"{digest}.json"


def _load_cache(path: Path, *, ttl: timedelta) -> str | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(str(payload.get("fetched_at")))
        if datetime.now(timezone.utc) - fetched_at > ttl:
            return None
        text = str(payload.get("text") or "").strip()
        return text or None
    except Exception:
        return None


def _save_cache(path: Path, *, url: str, text: str) -> None:
    payload = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "text": text,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fetch_url_text(
    url: str,
    *,
    data_dir: Path,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> tuple[str | None, str | None]:
    """Return extracted page text and optional status note."""
    try:
        normalized = validate_fetch_url(url)
    except ValueError as exc:
        return None, str(exc)

    cache_file = _cache_path(data_dir, normalized)
    ttl = timedelta(minutes=max(1, ttl_minutes))
    cached = _load_cache(cache_file, ttl=ttl)
    if cached is not None:
        logger.debug("Playbook URL cache hit: %s", normalized)
        return cached[:MAX_URL_TEXT_CHARS], f"cached snapshot of {normalized}"

    try:
        response = requests.get(
            normalized,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Playbook URL fetch failed for %s: %s", normalized, exc)
        stale = _load_cache(cache_file, ttl=timedelta(days=3650))
        if stale:
            return stale[:MAX_URL_TEXT_CHARS], f"stale cached snapshot of {normalized} (live fetch failed)"
        return None, f"fetch failed for {normalized}: {exc}"

    raw = response.content[:MAX_RESPONSE_BYTES]
    content_type = (response.headers.get("content-type") or "").lower()
    charset = response.encoding or "utf-8"
    try:
        body = raw.decode(charset, errors="replace")
    except LookupError:
        body = raw.decode("utf-8", errors="replace")

    if "html" in content_type or "<html" in body.lower():
        text = html_to_text(body)
    else:
        text = body.strip()

    if not text:
        return None, f"no readable text at {normalized}"

    clipped = text[:MAX_URL_TEXT_CHARS]
    _save_cache(cache_file, url=normalized, text=clipped)
    return clipped, f"live snapshot of {normalized}"


def format_playbook_dynamic_context(
    playbooks: list[Playbook],
    *,
    data_dir: Path | None,
) -> str:
    """Fetch configured playbook URLs and format prompt appendix."""
    if not playbooks or data_dir is None:
        return ""

    sections: list[str] = []
    remaining = MAX_TOTAL_DYNAMIC_CHARS

    for playbook in playbooks:
        if not playbook.fetch_urls or remaining <= 0:
            continue
        for url in playbook.fetch_urls:
            if remaining <= 0:
                break
            text, note = fetch_url_text(
                url,
                data_dir=data_dir,
                ttl_minutes=playbook.fetch_ttl_minutes,
            )
            if not text:
                if note:
                    sections.append(f"### Live source: {url}\n({note})")
                continue
            clipped = text[:remaining]
            remaining -= len(clipped)
            header = f"### Live source: {url}"
            if note:
                header += f"\n_{note}_"
            sections.extend([header, clipped, ""])

    if not sections:
        return ""

    intro = (
        "## Live web sources\n"
        "The following text was fetched from configured playbook URLs. "
        "Prefer this for current marketing copy and public product claims; "
        "do not treat it as private or authoritative over Slack/tool data."
    )
    return "\n".join([intro, "", *sections]).strip()
