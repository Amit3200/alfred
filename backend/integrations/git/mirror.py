"""Per-session repo mirrors — isolated workspaces with TTL cleanup."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend.integrations.git.api import resolve_repo_slug, split_repo_slug
from backend.models.config import GitConfig
from backend.paths import shared_repos_dir, workspace_repos_root

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"


@dataclass
class RepoMirrorState:
    repo: str
    path: Path
    head_sha: str | None
    last_pulled_at: str | None
    refreshed: bool


def workspace_dir_name(session_key: str) -> str:
    safe = re.sub(r"[^\w.-]+", "_", session_key.strip())
    return safe[:160] or "workspace"


class WorkspaceMirrorManager:
    """One git checkout copy per conversation session (Slack thread / UI chat)."""

    def __init__(self, git: GitConfig, data_dir: Path) -> None:
        self.git = git
        self.data_dir = data_dir
        self.workspaces_root = workspace_repos_root(data_dir)
        self.shared_root = shared_repos_dir(data_dir)

    def ensure_repo(
        self,
        session_key: str,
        repo: str,
        *,
        ref: str | None = None,
    ) -> RepoMirrorState:
        """Clone or refresh repo inside the session workspace."""
        self.cleanup_expired()
        slug = resolve_repo_slug(repo, self.git)
        self._assert_repo_allowed(slug)

        workspace_dir = self._workspace_dir(session_key)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._load_manifest(workspace_dir)
        manifest["session_key"] = session_key
        manifest["last_used_at"] = _now_iso()

        repo_dir = workspace_dir / _repo_dir_name(slug)
        entry = manifest.setdefault("repos", {}).get(slug, {})
        if not isinstance(entry, dict):
            entry = {}
        refreshed = False
        stored_ref = entry.get("ref")
        target_ref = ref or stored_ref

        if not repo_dir.is_dir() or not any(repo_dir.iterdir()):
            if self._try_seed_from_shared(slug, repo_dir):
                entry["cloned_at"] = _now_iso()
                entry["seeded"] = True
                refreshed = True
            else:
                self._clone(slug, repo_dir, ref=target_ref)
                entry["cloned_at"] = _now_iso()
                entry["seeded"] = False
                refreshed = True
        elif (repo_dir / ".git").exists():
            if ref:
                fallback_branch = _get_session_active_pr_head(self.data_dir, session_key) or stored_ref
                self._checkout_ref(repo_dir, ref, fallback_branch=fallback_branch)
                refreshed = True
            elif self._needs_refresh(entry):
                self._pull(repo_dir, ref=stored_ref or _current_branch(repo_dir))
                refreshed = True

        entry["last_pulled_at"] = _now_iso()
        entry["head_sha"] = _head_sha(repo_dir)
        if (repo_dir / ".git").exists():
            entry["ref"] = ref or stored_ref or _current_branch(repo_dir)
        elif ref:
            entry["ref"] = ref
        manifest["repos"][slug] = entry
        self._save_manifest(workspace_dir, manifest)

        return RepoMirrorState(
            repo=slug,
            path=repo_dir,
            head_sha=entry.get("head_sha"),
            last_pulled_at=entry.get("last_pulled_at"),
            refreshed=refreshed,
        )

    def sync_shared(self, repos: list[str] | None = None) -> list[dict[str, Any]]:
        """Admin warm-cache: clone/update shared mirrors used to seed workspaces."""
        targets = self._sync_targets(repos)
        results: list[dict[str, Any]] = []
        for repo in targets:
            slug = resolve_repo_slug(repo, self.git)
            self._assert_repo_allowed(slug)
            dest = self.shared_root / _repo_dir_name(slug)
            try:
                if dest.is_dir() and (dest / ".git").exists():
                    self._pull(dest)
                    action = "updated"
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    self._clone(slug, dest)
                    action = "cloned"
                results.append({"repo": slug, "ok": True, "action": action})
            except Exception as exc:
                logger.exception("Shared sync failed for %s", slug)
                results.append({"repo": slug, "ok": False, "error": str(exc)})
        return results

    def list_workspaces(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.workspaces_root.is_dir():
            return rows
        for path in sorted(self.workspaces_root.iterdir()):
            if not path.is_dir():
                continue
            rows.append(self._workspace_row(path))
        return rows

    def list_shared(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.shared_root.is_dir():
            return rows
        for path in sorted(self.shared_root.iterdir()):
            if not path.is_dir():
                continue
            slug = path.name.replace("__", "/", 1)
            rows.append(
                {
                    "id": path.name,
                    "repo": slug,
                    "size_bytes": _dir_size_bytes(path),
                    "head_sha": _head_sha(path) if (path / ".git").exists() else None,
                }
            )
        return rows

    def storage_summary(self) -> dict[str, Any]:
        workspaces = self.list_workspaces()
        shared = self.list_shared()
        workspace_bytes = sum(int(row.get("size_bytes") or 0) for row in workspaces)
        shared_bytes = sum(int(row.get("size_bytes") or 0) for row in shared)
        main_repo = ""
        if self.git.main_repo:
            try:
                main_repo = resolve_repo_slug(self.git.main_repo, self.git)
            except ValueError:
                main_repo = self.git.main_repo.strip()
        return {
            "workspaces_count": len(workspaces),
            "shared_count": len(shared),
            "workspaces_bytes": workspace_bytes,
            "shared_bytes": shared_bytes,
            "total_bytes": workspace_bytes + shared_bytes,
            "mirror_ttl_hours": self.git.mirror_ttl_hours,
            "mirror_max_workspaces": self.git.mirror_max_workspaces,
            "mirror_refresh_minutes": self.git.mirror_refresh_minutes,
            "main_repo": main_repo,
            "graphify_enabled": self.git.graphify_enabled,
        }

    def cleanup_all_workspaces(self) -> list[str]:
        if not self.workspaces_root.is_dir():
            return []
        removed: list[str] = []
        for path in sorted(self.workspaces_root.iterdir()):
            if not path.is_dir():
                continue
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
            logger.info("Removed mirror workspace %s", path.name)
        return removed

    def cleanup_shared(self) -> list[str]:
        if not self.shared_root.is_dir():
            return []
        removed: list[str] = []
        for path in sorted(self.shared_root.iterdir()):
            if not path.is_dir():
                continue
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
            logger.info("Removed shared mirror %s", path.name)
        return removed

    def drop_workspace_by_id(self, workspace_id: str) -> bool:
        safe = workspace_dir_name(workspace_id) if "/" in workspace_id or ":" in workspace_id else workspace_id
        path = self.workspaces_root / safe
        if not path.is_dir() or path.resolve().parent != self.workspaces_root.resolve():
            return False
        shutil.rmtree(path, ignore_errors=True)
        logger.info("Removed mirror workspace %s", safe)
        return True

    def drop_shared_by_id(self, shared_id: str) -> bool:
        path = self.shared_root / shared_id
        if not path.is_dir() or path.resolve().parent != self.shared_root.resolve():
            return False
        shutil.rmtree(path, ignore_errors=True)
        logger.info("Removed shared mirror %s", shared_id)
        return True

    def _workspace_row(self, path: Path) -> dict[str, Any]:
        manifest = self._load_manifest(path)
        repos_detail: list[dict[str, Any]] = []
        for slug, entry in (manifest.get("repos") or {}).items():
            if not isinstance(entry, dict):
                continue
            repos_detail.append(
                {
                    "slug": slug,
                    "ref": entry.get("ref"),
                    "head_sha": entry.get("head_sha"),
                    "last_pulled_at": entry.get("last_pulled_at"),
                }
            )
        return {
            "id": path.name,
            "session_key": manifest.get("session_key"),
            "last_used_at": manifest.get("last_used_at"),
            "repos": [item["slug"] for item in repos_detail],
            "repos_detail": repos_detail,
            "size_bytes": _dir_size_bytes(path),
        }

    def cleanup_expired(self) -> list[str]:
        """Remove workspace copies past TTL; enforce max workspace count (LRU)."""
        if not self.workspaces_root.is_dir():
            return []

        ttl = timedelta(hours=max(1, self.git.mirror_ttl_hours))
        now = datetime.now(timezone.utc)
        removed: list[str] = []

        entries: list[tuple[datetime, Path, dict[str, Any]]] = []
        for path in self.workspaces_root.iterdir():
            if not path.is_dir():
                continue
            manifest = self._load_manifest(path)
            last_used = _parse_iso(manifest.get("last_used_at")) or datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            )
            entries.append((last_used, path, manifest))

        for last_used, path, _manifest in entries:
            if now - last_used > ttl:
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path.name)
                logger.info("Removed expired mirror workspace %s", path.name)

        remaining = [
            item for item in entries if item[1].exists() and item[1].name not in removed
        ]
        max_ws = max(1, self.git.mirror_max_workspaces)
        if len(remaining) > max_ws:
            remaining.sort(key=lambda item: item[0])
            for _last_used, path, _manifest in remaining[: len(remaining) - max_ws]:
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path.name)
                logger.info("Removed LRU mirror workspace %s", path.name)

        return removed

    def drop_workspace(self, session_key: str) -> bool:
        path = self._workspace_dir(session_key)
        if not path.is_dir():
            return False
        shutil.rmtree(path, ignore_errors=True)
        return True

    def _workspace_dir(self, session_key: str) -> Path:
        return self.workspaces_root / workspace_dir_name(session_key)

    def _load_manifest(self, workspace_dir: Path) -> dict[str, Any]:
        path = workspace_dir / MANIFEST_NAME
        if not path.is_file():
            return {"repos": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"repos": {}}
        if not isinstance(data, dict):
            return {"repos": {}}
        data.setdefault("repos", {})
        return data

    def _save_manifest(self, workspace_dir: Path, manifest: dict[str, Any]) -> None:
        path = workspace_dir / MANIFEST_NAME
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _needs_refresh(self, entry: dict[str, Any]) -> bool:
        last = _parse_iso(entry.get("last_pulled_at"))
        if last is None:
            return True
        delta = timedelta(minutes=max(1, self.git.mirror_refresh_minutes))
        return datetime.now(timezone.utc) - last > delta

    def _assert_repo_allowed(self, repo: str) -> None:
        if not self.git.repos:
            return
        allowed = {item.lower() for item in self.git.repos}
        if repo.lower() in allowed:
            return
        main = (self.git.main_repo or "").strip()
        if main:
            try:
                if repo.lower() == resolve_repo_slug(main, self.git).lower():
                    return
            except ValueError:
                if "/" in main and repo.lower() == main.lower():
                    return
        raise ValueError(f"Repository {repo!r} is not in git.repos allowlist.")

    def _sync_targets(self, repos: list[str] | None) -> list[str]:
        """Repos to sync — main_repo first, then allowlist (deduped)."""
        ordered: list[str] = []
        seen: set[str] = set()

        def add(raw: str) -> None:
            try:
                slug = resolve_repo_slug(raw, self.git)
            except ValueError:
                return
            key = slug.lower()
            if key in seen:
                return
            seen.add(key)
            ordered.append(slug)

        if self.git.main_repo:
            add(self.git.main_repo)
        for item in repos or self.git.repos:
            add(item)
        return ordered

    def _clone_url(self, repo: str) -> str:
        owner, name = split_repo_slug(repo)
        token = quote(self.git.token, safe="")
        if self.git.provider == "gitlab":
            return f"https://oauth2:{token}@gitlab.com/{owner}/{name}.git"
        return f"https://x-access-token:{token}@github.com/{owner}/{name}.git"

    def _clone(self, repo: str, dest: Path, *, ref: str | None = None) -> None:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        depth = max(1, self.git.mirror_shallow_depth)
        cmd = [
            "git",
            "clone",
            "--depth",
            str(depth),
        ]
        if ref:
            cmd.extend(["--branch", ref, "--single-branch"])
        cmd.extend([self._clone_url(repo), str(dest)])
        try:
            _run_git(cmd)
        except RuntimeError:
            if not ref:
                raise
            # Ref may be a SHA or non-default branch name — clone default then checkout.
            cmd_fallback = [
                "git",
                "clone",
                "--depth",
                str(depth),
                self._clone_url(repo),
                str(dest),
            ]
            _run_git(cmd_fallback)
            self._checkout_ref(dest, ref)

    def _pull(self, repo_dir: Path, *, ref: str | None = None) -> None:
        depth = str(max(1, self.git.mirror_shallow_depth))
        branch = ref or _current_branch(repo_dir)
        if not _remote_branch_exists(repo_dir, branch):
            if _local_branch_exists(repo_dir, branch):
                logger.debug(
                    "Skipping remote pull for %s — ref %r exists locally but not on origin.",
                    repo_dir,
                    branch,
                )
                return
            logger.warning(
                "Skipping remote pull for %s — ref %r not found locally or on origin.",
                repo_dir,
                branch,
            )
            return
        try:
            _run_git(["git", "-C", str(repo_dir), "fetch", "origin", branch, "--depth", depth])
            _run_git(["git", "-C", str(repo_dir), "pull", "--ff-only", "origin", branch])
        except RuntimeError as exc:
            logger.warning("Fast-forward pull failed for %s ref=%s: %s. Attempting hard reset.", repo_dir, branch, exc)
            try:
                _run_git(["git", "-C", str(repo_dir), "fetch", "origin", branch, "--depth", depth])
                _run_git(["git", "-C", str(repo_dir), "reset", "--hard", f"origin/{branch}"])
            except Exception as reset_exc:
                logger.exception("Failed to force reset repo %s to origin/%s", repo_dir, branch)
                raise RuntimeError(
                    f"Git pull failed and subsequent force reset failed: {reset_exc}"
                ) from exc

    def _checkout_ref(self, repo_dir: Path, ref: str, fallback_branch: str | None = None) -> None:
        fetch_ref = ref
        is_sha = bool(re.match(r"^[0-9a-fA-F]{7,40}$", ref))
        
        # Git server APIs generally block fetching a commit SHA directly.
        # If we have a fallback branch name (like the active PR branch), we fetch it to download the target commit.
        if is_sha and fallback_branch and not re.match(r"^[0-9a-fA-F]{7,40}$", fallback_branch):
            fetch_ref = fallback_branch

        try:
            _run_git(["git", "-C", str(repo_dir), "fetch", "origin", fetch_ref, "--depth", "1"])
        except RuntimeError as fetch_exc:
            # If fetching direct ref failed (e.g. SHA fetch blocked) and we didn't try fallback branch yet, try it
            if fetch_ref == ref and fallback_branch and fetch_ref != fallback_branch:
                try:
                    _run_git(["git", "-C", str(repo_dir), "fetch", "origin", fallback_branch, "--depth", "1"])
                except Exception:
                    raise fetch_exc
            else:
                raise fetch_exc

        try:
            # If the target ref is a SHA, check it out directly. Otherwise, check out FETCH_HEAD.
            checkout_target = ref if is_sha else "FETCH_HEAD"
            _run_git(["git", "-C", str(repo_dir), "checkout", "--detach", checkout_target])
            _run_git(["git", "-C", str(repo_dir), "reset", "--hard", "FETCH_HEAD"])
        except RuntimeError as exc:
            logger.warning("Checkout of %s failed: %s. Attempting force checkout.", ref, exc)
            checkout_target = ref if is_sha else "FETCH_HEAD"
            _run_git(["git", "-C", str(repo_dir), "checkout", "-f", "--detach", checkout_target])
            _run_git(["git", "-C", str(repo_dir), "reset", "--hard", "FETCH_HEAD"])

    def _update_repo_ref(
        self,
        session_key: str,
        repo: str,
        *,
        ref: str,
        head_sha: str | None = None,
    ) -> None:
        """Persist active branch/ref on the session workspace manifest."""
        workspace_dir = self._workspace_dir(session_key)
        manifest = self._load_manifest(workspace_dir)
        entry = manifest.setdefault("repos", {}).get(repo, {})
        if not isinstance(entry, dict):
            entry = {}
        entry["ref"] = ref
        if head_sha:
            entry["head_sha"] = head_sha
        entry["last_pulled_at"] = _now_iso()
        manifest["repos"][repo] = entry
        manifest["last_used_at"] = _now_iso()
        self._save_manifest(workspace_dir, manifest)

    def _try_seed_from_shared(self, repo: str, dest: Path) -> bool:
        shared = self.shared_root / _repo_dir_name(repo)
        if not shared.is_dir() or not any(shared.iterdir()):
            return False
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(shared, dest, symlinks=True)
        return True


def _repo_dir_name(repo: str) -> str:
    return repo.replace("/", "__")


def _remote_branch_exists(repo_dir: Path, branch: str) -> bool:
    try:
        _run_git(["git", "-C", str(repo_dir), "rev-parse", "--verify", f"origin/{branch}"])
        return True
    except RuntimeError:
        return False


def _local_branch_exists(repo_dir: Path, branch: str) -> bool:
    try:
        _run_git(["git", "-C", str(repo_dir), "rev-parse", "--verify", branch])
        return True
    except RuntimeError:
        return False


def _dir_size_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except OSError:
        return 0
    return total


def _run_git(cmd: list[str], *, timeout: int = 300) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git command failed").strip()
        raise RuntimeError(detail[:500])
    return (result.stdout or "").strip()


def _head_sha(repo_dir: Path) -> str | None:
    try:
        return _run_git(["git", "-C", str(repo_dir), "rev-parse", "HEAD"])
    except RuntimeError:
        return None


def _current_branch(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return "main"
    try:
        branch = _run_git(["git", "-C", str(repo_dir), "branch", "--show-current"])
        if branch:
            return branch
    except RuntimeError:
        pass
    return _default_branch(repo_dir)


def _default_branch(repo_dir: Path) -> str:
    try:
        ref = _run_git(["git", "-C", str(repo_dir), "symbolic-ref", "refs/remotes/origin/HEAD"])
        return ref.rsplit("/", 1)[-1]
    except RuntimeError:
        return "main"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _get_session_active_pr_head(data_dir: Path, session_key: str) -> str | None:
    try:
        import sqlite3
        from backend.paths import db_path
        db = db_path(data_dir)
        if not db.is_file():
            return None
        with sqlite3.connect(db) as conn:
            row = conn.execute("SELECT payload FROM conversation_sessions WHERE key = ?;", (session_key,)).fetchone()
            if row:
                d = json.loads(row[0])
                active = d.get("metadata", {}).get("active_pr")
                if isinstance(active, dict) and active.get("head"):
                    return str(active["head"])
    except Exception:
        pass
    return None
