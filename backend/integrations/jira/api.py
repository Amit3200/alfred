"""JIRA Cloud REST API client."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

from backend.models.config import AlfredConfig, JiraConfig

_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


@dataclass
class JiraIssueSummary:
    key: str
    summary: str
    status: str
    issue_type: str
    assignee: str
    url: str
    priority: str = ""

    def format_line(self) -> str:
        assignee = f" · {self.assignee}" if self.assignee else ""
        return (
            f"{self.key} [{self.status}] {self.summary} "
            f"({self.issue_type}{assignee})\n  {self.url}"
        )


def extract_issue_key(text: str) -> str | None:
    if match := _ISSUE_KEY_RE.search(text or ""):
        return match.group(1)
    return None


def normalize_base_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise ValueError("jira.base_url is not configured.")
    if not url.startswith("http"):
        url = f"https://{url}"
    return url


class JiraApiClient:
    """Read/write JIRA Cloud issues via REST API v3."""

    def __init__(self, config: JiraConfig, *, api_token: str) -> None:
        if not config.enabled:
            raise RuntimeError("JIRA integration is disabled.")
        token = (api_token or "").strip()
        email = (config.email or "").strip()
        if not token:
            raise RuntimeError("JIRA API token is not configured.")
        if not email:
            raise RuntimeError("JIRA email is not configured.")
        self.config = config
        self.base_url = normalize_base_url(config.base_url)
        self.session = requests.Session()
        self.session.auth = (email, token)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    @classmethod
    def from_alfred_config(cls, config: AlfredConfig) -> JiraApiClient:
        return cls(config.jira, api_token=config.jira.api_token)

    def _url(self, path: str) -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self.session.request(method, self._url(path), timeout=30, **kwargs)
        if resp.status_code >= 400:
            detail = resp.text.strip()
            try:
                payload = resp.json()
                messages = payload.get("errorMessages") or []
                errors = payload.get("errors") or {}
                if messages:
                    detail = "; ".join(str(m) for m in messages)
                elif errors:
                    detail = "; ".join(f"{k}: {v}" for k, v in errors.items())
            except Exception:
                pass
            raise RuntimeError(f"JIRA API {resp.status_code}: {detail or resp.reason}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def ping(self) -> dict[str, Any]:
        return self._request("GET", "/rest/api/3/myself")

    def list_projects(self) -> list[dict[str, Any]]:
        """List JIRA projects visible to the API token user."""
        projects: list[dict[str, Any]] = []
        start_at = 0
        while True:
            payload = self._request(
                "GET",
                "/rest/api/3/project/search",
                params={"startAt": start_at, "maxResults": 50},
            )
            values = payload.get("values") or []
            for item in values:
                key = str(item.get("key") or "").strip().upper()
                name = str(item.get("name") or "").strip()
                if not key:
                    continue
                projects.append(
                    {
                        "key": key,
                        "name": name,
                        "id": str(item.get("id") or ""),
                        "project_type": str(item.get("projectTypeKey") or ""),
                    }
                )
            if payload.get("isLast") or not values:
                break
            start_at += len(values)
        projects.sort(key=lambda p: p["key"])
        return projects

    def token_account_id(self) -> str | None:
        """Account ID for the configured API token user (default reporter fallback)."""
        cached = getattr(self, "_token_account_id", None)
        if cached is not None:
            return cached or None
        try:
            account_id = str(self.ping().get("accountId") or "").strip()
        except Exception:
            account_id = ""
        self._token_account_id = account_id
        return account_id or None

    def resolve_account_id(self, identifier: str) -> str | None:
        """Resolve a display name, email, or accountId to a JIRA accountId."""
        needle = (identifier or "").strip()
        if not needle:
            return None
        if re.fullmatch(r"\d{6}:[0-9a-f-]{36}", needle, re.I):
            return needle

        mapped = self.config.assignee_map.get(needle) or self.config.assignee_map.get(needle.lower())
        if mapped:
            needle = mapped.strip()

        try:
            users = self.search_users(needle, max_results=10)
        except RuntimeError:
            return None
        if not users:
            return None

        if "@" in needle:
            for user in users:
                if str(user.get("emailAddress") or "").lower() == needle.lower():
                    return str(user.get("accountId") or "") or None

        lower = needle.lower()
        for user in users:
            display = str(user.get("displayName") or "").lower()
            if display == lower or lower in display:
                return str(user.get("accountId") or "") or None
        account_id = str(users[0].get("accountId") or "").strip()
        return account_id or None

    def search_users(self, query: str, *, max_results: int = 10) -> list[dict[str, Any]]:
        needle = (query or "").strip()
        if not needle:
            return []
        data = self._request(
            "GET",
            "/rest/api/3/user/search",
            params={"query": needle, "maxResults": max(1, min(int(max_results), 50))},
        )
        return data if isinstance(data, list) else []

    def _issue_allowed(self, issue_key: str) -> None:
        key = issue_key.strip().upper()
        project = key.split("-", 1)[0]
        self._project_allowed(project)

    def _project_allowed(self, project: str) -> None:
        allowed = [p.strip().upper() for p in self.config.allowed_projects if p.strip()]
        if not allowed:
            return
        if project.upper() not in allowed:
            raise ValueError(
                f"Project {project} is outside allowed projects: "
                f"{', '.join(self.config.allowed_projects)}."
            )

    def search_issues(
        self,
        *,
        jql: str | None = None,
        project: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        max_results: int = 25,
    ) -> list[JiraIssueSummary]:
        query = (jql or "").strip()
        if not query:
            parts: list[str] = []
            proj = (project or self.config.default_project or "").strip()
            if proj:
                parts.append(f'project = "{proj}"')
            if status:
                parts.append(f'status = "{status.strip()}"')
            if assignee:
                parts.append(f'assignee = "{assignee.strip()}"')
            query = " AND ".join(parts) if parts else "ORDER BY updated DESC"
            if parts:
                query = f"{query} ORDER BY updated DESC"
        data = self._request(
            "POST",
            "/rest/api/3/search/jql",
            json={
                "jql": query,
                "maxResults": max(1, min(int(max_results or 25), 100)),
                "fields": ["summary", "status", "assignee", "issuetype", "priority"],
            },
        )
        issues = data.get("issues") or []
        return [self._summary_from_issue(item) for item in issues]

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        data = self._request(
            "GET",
            f"/rest/api/3/issue/{key}",
            params={
                "fields": ",".join(
                    [
                        "summary",
                        "description",
                        "status",
                        "assignee",
                        "issuetype",
                        "priority",
                        "labels",
                        "comment",
                        "issuelinks",
                        "fixVersions",
                        "components",
                        "created",
                        "updated",
                    ]
                )
            },
        )
        fields = data.get("fields") or {}
        description = _plain_text_from_adf(fields.get("description"))
        remote_links = self.list_remote_links(key)
        return {
            "key": key,
            "summary": fields.get("summary") or "",
            "status": _status_name(fields.get("status")),
            "issue_type": _issue_type_name(fields.get("issuetype")),
            "assignee": _user_name(fields.get("assignee")),
            "priority": _priority_name(fields.get("priority")),
            "labels": [str(label) for label in fields.get("labels") or []],
            "description": description,
            "url": f"{self.base_url}/browse/{key}",
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "comment_count": int((fields.get("comment") or {}).get("total") or 0),
            "links": [_issue_link_dict(link) for link in fields.get("issuelinks") or []],
            "remote_links": remote_links,
        }

    def list_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        data = self._request("GET", f"/rest/api/3/issue/{key}/transitions")
        transitions = []
        for item in data.get("transitions") or []:
            to_status = item.get("to") or {}
            transitions.append(
                {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "to_status": str(to_status.get("name") or ""),
                }
            )
        return transitions

    def transition_issue(self, issue_key: str, *, transition: str) -> dict[str, Any]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        target = transition.strip()
        if not target:
            raise ValueError("transition is required (transition name or target status).")
        transitions = self.list_transitions(key)
        match = _pick_transition(transitions, target)
        if not match:
            options = ", ".join(
                f"{t['name']}→{t['to_status']}" for t in transitions if t.get("name")
            )
            raise ValueError(
                f"No transition matched {target!r} for {key}. Available: {options or 'none'}."
            )
        self._request(
            "POST",
            f"/rest/api/3/issue/{key}/transitions",
            json={"transition": {"id": match["id"]}},
        )
        updated = self.get_issue(key)
        return {
            "key": key,
            "transition": match["name"],
            "status": updated.get("status"),
            "url": updated.get("url"),
        }

    def add_comment(self, issue_key: str, comment: str) -> dict[str, Any]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        body = (comment or "").strip()
        if not body:
            raise ValueError("comment is required.")
        self._request(
            "POST",
            f"/rest/api/3/issue/{key}/comment",
            json={"body": _adf_paragraph(body)},
        )
        return {"key": key, "comment_added": True, "url": f"{self.base_url}/browse/{key}"}

    def update_issue(
        self,
        issue_key: str,
        *,
        summary: str | None = None,
        description: str | None = None,
        append_description: bool = True,
    ) -> dict[str, Any]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        fields: dict[str, Any] = {}
        if summary and summary.strip():
            fields["summary"] = summary.strip()
        if description is not None:
            text = description.strip()
            if text and append_description:
                current = self.get_issue(key)
                existing = (current.get("description") or "").strip()
                if existing:
                    text = f"{existing}\n\n{text}"
            if text:
                fields["description"] = _adf_paragraph(text)
        if not fields:
            raise ValueError("At least one of summary or description is required.")
        self._request("PUT", f"/rest/api/3/issue/{key}", json={"fields": fields})
        updated = self.get_issue(key)
        return {
            "key": key,
            "url": updated.get("url"),
            "summary": updated.get("summary"),
            "updated_fields": list(fields.keys()),
        }

    def assign_issue(self, issue_key: str, *, assignee: str) -> dict[str, Any]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        needle = (assignee or "").strip()
        if not needle:
            raise ValueError("assignee is required (name, email, or account ID).")
        account_id = self.resolve_account_id(needle)
        if not account_id:
            raise ValueError(f"Could not resolve JIRA assignee for {needle!r}.")
        self._request(
            "PUT",
            f"/rest/api/3/issue/{key}/assignee",
            json={"accountId": account_id},
        )
        updated = self.get_issue(key)
        return {
            "key": key,
            "assignee": updated.get("assignee"),
            "url": updated.get("url"),
            "action": "assign",
        }

    def create_issue(
        self,
        *,
        project: str,
        summary: str,
        issue_type: str,
        priority: str | None = None,
        description: str | None = None,
        reporter: str | None = None,
        assignee: str | None = None,
        resilient: bool = True,
    ) -> dict[str, Any]:
        project_key = project.strip().upper()
        self._project_allowed(project_key)
        title = summary.strip()
        kind = issue_type.strip()
        if not title:
            raise ValueError("summary is required.")
        if not kind:
            raise ValueError("issue_type is required.")

        base_fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": title,
            "issuetype": {"name": kind},
        }
        if priority and priority.strip():
            base_fields["priority"] = {"name": priority.strip()}
        if description and description.strip():
            base_fields["description"] = _adf_paragraph(description.strip())

        if not resilient:
            fields = dict(base_fields)
            self._apply_user_fields(fields, reporter=reporter, assignee=assignee)
            return self._finalize_create(fields, project_key=project_key, title=title, kind=kind)

        last_error = "JIRA create failed."
        reporter_candidates: list[str | None] = []
        preferred = self.resolve_account_id(reporter) if reporter else None
        token = self.token_account_id()
        if preferred:
            reporter_candidates.append(preferred)
        if token and token not in reporter_candidates:
            reporter_candidates.append(token)
        reporter_candidates.append(None)

        assignee_id = self.resolve_account_id(assignee) if assignee else None

        for drop_priority in (False, True):
            for reporter_id in reporter_candidates:
                fields = dict(base_fields)
                if drop_priority:
                    fields.pop("priority", None)
                if reporter_id:
                    fields["reporter"] = {"accountId": reporter_id}
                if assignee_id:
                    fields["assignee"] = {"accountId": assignee_id}
                try:
                    return self._finalize_create(
                        fields,
                        project_key=project_key,
                        title=title,
                        kind=kind,
                    )
                except RuntimeError as exc:
                    last_error = str(exc)
                    if assignee_id and "assignee" in fields:
                        fields.pop("assignee", None)
                        try:
                            return self._finalize_create(
                                fields,
                                project_key=project_key,
                                title=title,
                                kind=kind,
                            )
                        except RuntimeError as retry_exc:
                            last_error = str(retry_exc)
                    continue

        raise RuntimeError(last_error)

    def _apply_user_fields(
        self,
        fields: dict[str, Any],
        *,
        reporter: str | None,
        assignee: str | None,
    ) -> None:
        reporter_id = self.resolve_account_id(reporter) if reporter else None
        assignee_id = self.resolve_account_id(assignee) if assignee else None
        if reporter_id:
            fields["reporter"] = {"accountId": reporter_id}
        if assignee_id:
            fields["assignee"] = {"accountId": assignee_id}

    def _finalize_create(
        self,
        fields: dict[str, Any],
        *,
        project_key: str,
        title: str,
        kind: str,
    ) -> dict[str, Any]:
        data = self._request("POST", "/rest/api/3/issue", json={"fields": fields})
        key = str(data.get("key") or "")
        return {
            "key": key,
            "url": f"{self.base_url}/browse/{key}" if key else "",
            "summary": title,
            "issue_type": kind,
            "project": project_key,
        }

    def link_remote(self, issue_key: str, *, url: str, title: str | None = None) -> dict[str, Any]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        link_url = (url or "").strip()
        if not link_url:
            raise ValueError("url is required.")
        payload = {
            "object": {
                "url": link_url,
                "title": (title or link_url).strip() or link_url,
            }
        }
        data = self._request("POST", f"/rest/api/3/issue/{key}/remotelink", json=payload)
        return {
            "key": key,
            "url": link_url,
            "title": payload["object"]["title"],
            "remote_link_id": data.get("id"),
            "issue_url": f"{self.base_url}/browse/{key}",
        }

    def list_remote_links(self, issue_key: str) -> list[dict[str, Any]]:
        key = issue_key.strip().upper()
        self._issue_allowed(key)
        data = self._request("GET", f"/rest/api/3/issue/{key}/remotelink")
        links = []
        for item in data if isinstance(data, list) else []:
            obj = item.get("object") or {}
            links.append(
                {
                    "id": item.get("id"),
                    "url": obj.get("url") or "",
                    "title": obj.get("title") or obj.get("url") or "",
                }
            )
        return links

    def _summary_from_issue(self, issue: dict[str, Any]) -> JiraIssueSummary:
        fields = issue.get("fields") or {}
        key = str(issue.get("key") or "")
        return JiraIssueSummary(
            key=key,
            summary=str(fields.get("summary") or ""),
            status=_status_name(fields.get("status")),
            issue_type=_issue_type_name(fields.get("issuetype")),
            assignee=_user_name(fields.get("assignee")),
            priority=_priority_name(fields.get("priority")),
            url=f"{self.base_url}/browse/{key}",
        )


def _status_name(value: Any) -> str:
    return str((value or {}).get("name") or "")


def _issue_type_name(value: Any) -> str:
    return str((value or {}).get("name") or "")


def _priority_name(value: Any) -> str:
    return str((value or {}).get("name") or "")


def _user_name(value: Any) -> str:
    if not value:
        return ""
    return str(value.get("displayName") or value.get("emailAddress") or "")


def _issue_link_dict(link: dict[str, Any]) -> dict[str, str]:
    link_type = (link.get("type") or {}).get("name") or "relates to"
    inward = link.get("inwardIssue") or {}
    outward = link.get("outwardIssue") or {}
    target = outward or inward
    return {
        "relationship": str(link_type),
        "key": str(target.get("key") or ""),
        "summary": str(((target.get("fields") or {}).get("summary")) or ""),
    }


def _pick_transition(transitions: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    needle = target.strip().lower()
    for item in transitions:
        if str(item.get("name") or "").lower() == needle:
            return item
        if str(item.get("to_status") or "").lower() == needle:
            return item
    for item in transitions:
        name = str(item.get("name") or "").lower()
        status = str(item.get("to_status") or "").lower()
        if needle in name or needle in status:
            return item
    return None


def _adf_paragraph(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _plain_text_from_adf(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value)
    chunks: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                chunks.append(str(node.get("text") or ""))
            for child in node.get("content") or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return "".join(chunks).strip()
