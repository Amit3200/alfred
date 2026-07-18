"""GitHub and GitLab REST API client for read-only PR/repo operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

import requests

from backend.models.config import AlfredConfig, GitConfig

Provider = Literal["github", "gitlab"]


@dataclass
class PullRequestSummary:
    number: int
    title: str
    state: str
    repo: str
    author: str
    url: str
    draft: bool = False

    def format_line(self) -> str:
        draft = " (draft)" if self.draft else ""
        return f"#{self.number} [{self.state}] {self.title}{draft} — {self.repo} by {self.author}\n  {self.url}"


def split_repo_slug(repo: str) -> tuple[str, str]:
    slug = repo.strip().strip("/")
    if "/" not in slug:
        raise ValueError(f"Invalid repo slug {repo!r} — expected owner/name")
    owner, name = slug.split("/", 1)
    return owner, name


def resolve_repo_slug(repo: str, git: GitConfig) -> str:
    """Expand short repo names (e.g. adhocs) to owner/name using config."""
    slug = repo.strip().strip("/")
    if "/" in slug:
        return slug

    short = slug.lower()
    for configured in git.repos:
        if configured.lower().endswith(f"/{short}") or configured.lower() == short:
            return configured

    if git.default_org:
        candidate = f"{git.default_org}/{slug}"
        if not git.repos or any(r.lower() == candidate.lower() for r in git.repos):
            return candidate
        # default_org + short name is still the best guess when repos list is empty
        if not git.repos:
            return candidate
        return candidate

    matches = [r for r in git.repos if r.lower().endswith(f"/{short}")]
    if len(matches) == 1:
        return matches[0]

    if git.main_repo:
        main = git.main_repo.strip().strip("/")
        if "/" in main:
            short_main = main.rsplit("/", 1)[-1].lower()
            if slug.lower() == short_main:
                return main

    raise ValueError(
        f"Invalid repo slug {repo!r} — expected owner/name. "
        f"Set git.default_org or git.main_repo in config, or use a full GitHub URL."
    )


class GitApiClient:
    """Provider-agnostic git API wrapper."""

    def __init__(self, config: GitConfig) -> None:
        if not config.enabled:
            raise RuntimeError("Git integration is disabled in config")
        if not config.token:
            raise RuntimeError("Git token is not configured")
        self.config = config
        if config.provider == "github":
            self._impl: _GitHubClient | _GitLabClient = _GitHubClient(config)
        else:
            self._impl = _GitLabClient(config)

    @classmethod
    def from_alfred_config(cls, config: AlfredConfig) -> "GitApiClient":
        return cls(config.git)

    def current_user_login(self) -> str:
        return self._impl.current_user_login()

    def list_my_prs(self, *, state: str = "open") -> list[PullRequestSummary]:
        return self._impl.list_my_prs(state=state)

    def list_prs(self, repo: str, *, state: str = "open") -> list[PullRequestSummary]:
        return self._impl.list_prs(repo, state=state)

    def get_pr(self, repo: str, number: int) -> dict[str, Any]:
        return self._impl.get_pr(repo, number)

    def get_pr_files(self, repo: str, number: int) -> list[dict[str, Any]]:
        return self._impl.get_pr_files(repo, number)

    def list_repos(self) -> list[str]:
        configured = list(self.config.repos)
        if configured:
            return configured
        return self._impl.list_accessible_repos()

    def list_org_members(self, org: str | None = None) -> list[dict[str, Any]]:
        org = (org or self.config.default_org or "").strip().strip("/")
        if not org:
            raise ValueError("GitHub org is required — set git.default_org in config.")
        if self.config.provider != "github":
            raise RuntimeError("Org member listing is only supported for GitHub.")
        return self._impl.list_org_members(org)

    def list_available_repos(self) -> dict[str, Any]:
        """Merge configured allowlist with remote org/user repos for admin UI."""
        configured = [r.strip() for r in self.config.repos if r.strip()]
        remote: list[str] = []
        source = "configured"
        error: str | None = None

        if self.config.token:
            try:
                remote = self._impl.list_accessible_repos()
                source = "org" if self.config.default_org else "user"
            except Exception as exc:
                error = str(exc)
        elif self.config.default_org:
            error = "Git token is not configured — add it under Secrets."

        merged: list[str] = []
        seen: set[str] = set()
        for repo in [*configured, *remote]:
            key = repo.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(repo)

        return {
            "repos": sorted(merged, key=str.lower),
            "configured": configured,
            "remote": remote,
            "source": source,
            "org": self.config.default_org or None,
            "error": error,
        }

    def create_issue_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        return self._impl.create_issue_comment(repo, number, body)

    def create_issue_comment_reaction(
        self, repo: str, comment_id: int, content: str
    ) -> dict[str, Any]:
        return self._impl.create_issue_comment_reaction(repo, comment_id, content)

    def create_pull_request(
        self,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = False,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._impl.create_pull_request(
            repo,
            title=title,
            head=head,
            base=base,
            body=body,
            draft=draft,
            labels=labels,
        )


class _GitHubClient:
    API = "https://api.github.com"

    def __init__(self, config: GitConfig) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        url = path if path.startswith("http") else f"{self.API}{path}"
        resp = self._session.request(method, url, params=params, json=json, timeout=30)
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise RuntimeError(f"GitHub API error {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def _get(self, path: str, *, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, *, json: dict | None = None) -> Any:
        return self._request("POST", path, json=json)

    def current_user_login(self) -> str:
        data = self._get("/user")
        login = data.get("login")
        if not login:
            raise RuntimeError("GitHub /user did not return login")
        return str(login)

    def list_org_members(self, org: str) -> list[dict[str, Any]]:
        org = org.strip().strip("/")
        members: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._get(
                f"/orgs/{quote(org, safe='')}/members",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(batch, list) or not batch:
                break
            members.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return members

    def list_my_prs(self, *, state: str = "open") -> list[PullRequestSummary]:
        login = self.current_user_login()
        query_state = "open" if state == "open" else "closed" if state == "closed" else "all"
        q = f"is:pr author:{login} is:{query_state}" if query_state != "all" else f"is:pr author:{login}"
        data = self._get("/search/issues", params={"q": q, "sort": "updated", "per_page": 30})
        items = data.get("items") or []
        results: list[PullRequestSummary] = []
        for item in items:
            repo_full = (item.get("repository_url") or "").rstrip("/").split("/")[-2:]
            repo = "/".join(repo_full) if len(repo_full) == 2 else "unknown/unknown"
            results.append(
                PullRequestSummary(
                    number=int(item.get("number", 0)),
                    title=str(item.get("title") or ""),
                    state=str(item.get("state") or ""),
                    repo=repo,
                    author=login,
                    url=str(item.get("html_url") or ""),
                    draft=bool(item.get("draft", False)),
                )
            )
        return results

    def list_prs(self, repo: str, *, state: str = "open") -> list[PullRequestSummary]:
        owner, name = split_repo_slug(repo)
        api_state = "open" if state == "open" else "closed" if state == "closed" else "all"
        data = self._get(f"/repos/{owner}/{name}/pulls", params={"state": api_state, "per_page": 30})
        results: list[PullRequestSummary] = []
        for item in data:
            user = item.get("user") or {}
            results.append(
                PullRequestSummary(
                    number=int(item.get("number", 0)),
                    title=str(item.get("title") or ""),
                    state=str(item.get("state") or ""),
                    repo=f"{owner}/{name}",
                    author=str(user.get("login") or ""),
                    url=str(item.get("html_url") or ""),
                    draft=bool(item.get("draft", False)),
                )
            )
        return results

    def get_pr(self, repo: str, number: int) -> dict[str, Any]:
        owner, name = split_repo_slug(repo)
        data = self._get(f"/repos/{owner}/{name}/pulls/{number}")
        user = data.get("user") or {}
        return {
            "number": data.get("number"),
            "title": data.get("title"),
            "state": data.get("state"),
            "repo": f"{owner}/{name}",
            "author": user.get("login"),
            "url": data.get("html_url"),
            "body": (data.get("body") or "")[:2000],
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "merged": data.get("merged"),
            "draft": data.get("draft"),
            "head": (data.get("head") or {}).get("ref"),
            "base": (data.get("base") or {}).get("ref"),
        }

    def get_pr_files(self, repo: str, number: int) -> list[dict[str, Any]]:
        owner, name = split_repo_slug(repo)
        data = self._get(f"/repos/{owner}/{name}/pulls/{number}/files", params={"per_page": 100})
        results: list[dict[str, Any]] = []
        for item in data:
            results.append(
                {
                    "filename": str(item.get("filename") or ""),
                    "status": str(item.get("status") or ""),
                    "additions": int(item.get("additions") or 0),
                    "deletions": int(item.get("deletions") or 0),
                    "changes": int(item.get("changes") or 0),
                    "patch": str(item.get("patch") or ""),
                    "previous_filename": item.get("previous_filename"),
                }
            )
        return results

    def list_accessible_repos(self) -> list[str]:
        if self.config.default_org:
            data = self._get(f"/orgs/{self.config.default_org}/repos", params={"per_page": 100})
            return [str(item.get("full_name")) for item in data if item.get("full_name")]
        data = self._get("/user/repos", params={"per_page": 100, "sort": "updated"})
        return [str(item.get("full_name")) for item in data if item.get("full_name")]

    def create_issue_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        owner, name = split_repo_slug(repo)
        return self._post(
            f"/repos/{owner}/{name}/issues/{number}/comments",
            json={"body": body},
        )

    def create_issue_comment_reaction(
        self, repo: str, comment_id: int, content: str
    ) -> dict[str, Any]:
        owner, name = split_repo_slug(repo)
        return self._post(
            f"/repos/{owner}/{name}/issues/comments/{comment_id}/reactions",
            json={"content": content},
        )

    def _apply_issue_labels(self, repo: str, issue_number: int, labels: list[str]) -> None:
        if not labels:
            return
        owner, name = split_repo_slug(repo)
        self._post(
            f"/repos/{owner}/{name}/issues/{issue_number}/labels",
            json={"labels": labels},
        )

    def create_pull_request(
        self,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = False,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        owner, name = split_repo_slug(repo)
        payload: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
        }
        if draft:
            payload["draft"] = True
        data = self._post(f"/repos/{owner}/{name}/pulls", json=payload)
        pr_number = data.get("number")
        applied_labels: list[str] = []
        if pr_number and labels:
            self._apply_issue_labels(repo, int(pr_number), labels)
            applied_labels = list(labels)
        return {
            "number": pr_number,
            "title": data.get("title"),
            "state": data.get("state"),
            "repo": f"{owner}/{name}",
            "url": data.get("html_url"),
            "head": (data.get("head") or {}).get("ref"),
            "base": (data.get("base") or {}).get("ref"),
            "draft": data.get("draft", False),
            "labels": applied_labels,
        }


class _GitLabClient:
    API = "https://gitlab.com/api/v4"

    def __init__(self, config: GitConfig) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({"PRIVATE-TOKEN": config.token})

    def _get(self, path: str, *, params: dict | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.API}{path}"
        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise RuntimeError(f"GitLab API error {resp.status_code}: {detail}")
        return resp.json()

    def _post(self, path: str, *, json: dict | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.API}{path}"
        resp = self._session.post(url, json=json, timeout=30)
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise RuntimeError(f"GitLab API error {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def current_user_login(self) -> str:
        data = self._get("/user")
        login = data.get("username") or data.get("name")
        if not login:
            raise RuntimeError("GitLab /user did not return username")
        return str(login)

    def list_my_prs(self, *, state: str = "opened") -> list[PullRequestSummary]:
        api_state = "opened" if state in ("open", "opened") else "closed" if state == "closed" else "all"
        params: dict[str, Any] = {"scope": "created_by_me", "per_page": 30}
        if api_state != "all":
            params["state"] = api_state
        data = self._get("/merge_requests", params=params)
        results: list[PullRequestSummary] = []
        for item in data:
            references = item.get("references") or {}
            full = str(references.get("full") or "")
            repo = full.split("!")[0] if "!" in full else str(item.get("web_url", "")).split("/-/")[0].split("gitlab.com/")[-1]
            author = (item.get("author") or {}).get("username") or ""
            results.append(
                PullRequestSummary(
                    number=int(item.get("iid", 0)),
                    title=str(item.get("title") or ""),
                    state=str(item.get("state") or ""),
                    repo=repo.replace("/", "/") if repo else "unknown/unknown",
                    author=str(author),
                    url=str(item.get("web_url") or ""),
                    draft=bool(item.get("draft", False)),
                )
            )
        return results

    def list_prs(self, repo: str, *, state: str = "open") -> list[PullRequestSummary]:
        project = quote(repo, safe="")
        api_state = "opened" if state in ("open", "opened") else "closed" if state == "closed" else "all"
        params: dict[str, Any] = {"per_page": 30}
        if api_state != "all":
            params["state"] = api_state
        data = self._get(f"/projects/{project}/merge_requests", params=params)
        results: list[PullRequestSummary] = []
        for item in data:
            author = (item.get("author") or {}).get("username") or ""
            results.append(
                PullRequestSummary(
                    number=int(item.get("iid", 0)),
                    title=str(item.get("title") or ""),
                    state=str(item.get("state") or ""),
                    repo=repo,
                    author=str(author),
                    url=str(item.get("web_url") or ""),
                    draft=bool(item.get("draft", False)),
                )
            )
        return results

    def get_pr(self, repo: str, number: int) -> dict[str, Any]:
        project = quote(repo, safe="")
        data = self._get(f"/projects/{project}/merge_requests/{number}")
        author = (data.get("author") or {}).get("username") or ""
        return {
            "number": data.get("iid"),
            "title": data.get("title"),
            "state": data.get("state"),
            "repo": repo,
            "author": author,
            "url": data.get("web_url"),
            "body": (data.get("description") or "")[:2000],
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "merged": data.get("state") == "merged",
            "draft": data.get("draft"),
            "head": (data.get("source_branch")),
            "base": (data.get("target_branch")),
        }

    def get_pr_files(self, repo: str, number: int) -> list[dict[str, Any]]:
        project = quote(repo, safe="")
        data = self._get(f"/projects/{project}/merge_requests/{number}/changes")
        results: list[dict[str, Any]] = []
        for item in data.get("changes") or []:
            old_path = str(item.get("old_path") or "")
            new_path = str(item.get("new_path") or "")
            if old_path and new_path and old_path != new_path:
                status = "renamed"
            elif new_path and not old_path:
                status = "added"
            elif old_path and not new_path:
                status = "removed"
            else:
                status = "modified"
            results.append(
                {
                    "filename": new_path or old_path,
                    "status": status,
                    "additions": 0,
                    "deletions": 0,
                    "changes": 0,
                    "patch": str(item.get("diff") or ""),
                    "previous_filename": old_path if old_path != new_path else None,
                }
            )
        return results

    def list_accessible_repos(self) -> list[str]:
        if self.config.default_org:
            group = quote(self.config.default_org, safe="")
            data = self._get(f"/groups/{group}/projects", params={"per_page": 100})
            return [str(item.get("path_with_namespace")) for item in data if item.get("path_with_namespace")]
        data = self._get("/projects", params={"membership": True, "per_page": 100})
        return [str(item.get("path_with_namespace")) for item in data if item.get("path_with_namespace")]

    def create_issue_comment(self, repo: str, number: int, body: str) -> dict[str, Any]:
        project = quote(repo, safe="")
        return self._post(
            f"/projects/{project}/merge_requests/{number}/notes",
            json={"body": body},
        )

    def create_issue_comment_reaction(
        self, repo: str, comment_id: int, content: str
    ) -> dict[str, Any]:
        raise RuntimeError("Issue comment reactions are not supported for GitLab yet")

    def create_pull_request(
        self,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = False,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        project = quote(repo, safe="")
        payload: dict[str, Any] = {
            "title": title,
            "source_branch": head,
            "target_branch": base,
            "description": body,
        }
        if draft:
            payload["draft"] = True
        if labels:
            payload["labels"] = ",".join(labels)
        data = self._post(f"/projects/{project}/merge_requests", json=payload)
        return {
            "number": data.get("iid"),
            "title": data.get("title"),
            "state": data.get("state"),
            "repo": repo,
            "url": data.get("web_url"),
            "head": data.get("source_branch"),
            "base": data.get("target_branch"),
            "draft": bool(data.get("draft")),
            "labels": list(labels or []),
        }
