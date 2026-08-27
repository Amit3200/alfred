"""Deterministic entity extraction for routing and tool planning."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.jira.api import extract_issue_key
from backend.integrations.slack.sanitize import extract_slack_user_ids

_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_ISSUE_KEY_SPACE_RE = re.compile(r"\b([A-Z]{2,10})\s+(\d{1,6})\b")
_FALSE_PROJECT_KEYS = frozenset(
    {
        "HTTP",
        "HTTPS",
        "ERROR",
        "CODE",
        "JSON",
        "HTML",
        "OK",
        "ID",
        "PR",
        "FY",
        "UTC",
        "GMT",
        "EST",
        "PST",
        "ISO",
        "CVE",
    }
)
_SHEET_ID_RE = re.compile(
    r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",
    re.I,
)
_DOC_ID_RE = re.compile(
    r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)",
    re.I,
)
_GITHUB_PR_RE = re.compile(
    r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)",
    re.I,
)


@dataclass(frozen=True)
class EntityBag:
    issue_keys: tuple[str, ...] = ()
    spreadsheet_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    slack_user_ids: tuple[str, ...] = ()
    github_prs: tuple[tuple[str, int], ...] = ()  # (repo, number)
    raw: dict[str, Any] = field(default_factory=dict)


def extract_entities(*texts: str) -> EntityBag:
    combined = "\n".join(t for t in texts if (t or "").strip())
    if not combined.strip():
        return EntityBag()

    issue_keys: list[str] = []
    seen_keys: set[str] = set()
    for match in _ISSUE_KEY_RE.finditer(combined):
        key = match.group(1).upper()
        if key not in seen_keys:
            seen_keys.add(key)
            issue_keys.append(key)
    for match in _ISSUE_KEY_SPACE_RE.finditer(combined):
        project = match.group(1).upper()
        if project in _FALSE_PROJECT_KEYS:
            continue
        key = f"{project}-{match.group(2)}"
        if key not in seen_keys:
            seen_keys.add(key)
            issue_keys.append(key)
    if not issue_keys:
        if key := extract_issue_key(combined):
            issue_keys.append(key.upper())

    sheet_ids = _unique(_SHEET_ID_RE.findall(combined))
    doc_ids = _unique(_DOC_ID_RE.findall(combined))
    user_ids = tuple(extract_slack_user_ids(combined))

    prs: list[tuple[str, int]] = []
    for repo, number in _GITHUB_PR_RE.findall(combined):
        prs.append((repo, int(number)))

    return EntityBag(
        issue_keys=tuple(issue_keys),
        spreadsheet_ids=tuple(sheet_ids),
        document_ids=tuple(doc_ids),
        slack_user_ids=user_ids,
        github_prs=tuple(prs),
        raw={
            "issue_keys": issue_keys,
            "spreadsheet_ids": sheet_ids,
            "document_ids": doc_ids,
        },
    )


def _unique(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)
