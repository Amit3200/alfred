"""Tests for repo path sandbox."""

import pytest

from backend.integrations.git.sandbox import PathSandboxError, resolve_repo_path


def test_resolve_repo_path_allows_relative(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "src" / "main.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')", encoding="utf-8")
    resolved = resolve_repo_path(repo, "src/main.py")
    assert resolved == file_path.resolve()


def test_resolve_repo_path_rejects_traversal(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(PathSandboxError):
        resolve_repo_path(repo, "../outside")
