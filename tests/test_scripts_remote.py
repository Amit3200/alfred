"""Tests for remote company scripts repo sync and dependencies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from backend.integrations.company_scripts.catalog import CompanyScriptStore
from backend.integrations.company_scripts.deps import find_requirements_file
from backend.integrations.company_scripts.paths_helper import script_catalog_roots
from backend.models.config import AlfredConfig, ScriptsConfig, ScriptsRemoteConfig


def test_find_requirements_file_prefers_scripts_root(tmp_path: Path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "requirements.txt").write_text("requests>=2.31\n", encoding="utf-8")
    (repo / "requirements.txt").write_text("other\n", encoding="utf-8")
    found = find_requirements_file(repo_root=repo, scripts_root=scripts, configured="")
    assert found == scripts / "requirements.txt"


def test_script_catalog_roots_local_and_remote(tmp_path: Path):
    local = tmp_path / "scripts"
    local.mkdir()
    remote = tmp_path / "remote" / "scripts"
    remote.mkdir(parents=True)
    pkg = remote / "remote_pkg"
    pkg.mkdir()
    (pkg / "script.yaml").write_text(
        "name: remote_pkg\nentry: main.py\nruntime: python3\n",
        encoding="utf-8",
    )
    (pkg / "main.py").write_text("print('remote')\n", encoding="utf-8")

    config = AlfredConfig(
        scripts=ScriptsConfig(
            remote=ScriptsRemoteConfig(repo="FlexyPe/alfred_scripts", path="scripts"),
        )
    )

    with patch(
        "backend.integrations.company_scripts.paths_helper.remote_scripts_root",
        return_value=remote,
    ):
        roots = script_catalog_roots(tmp_path, config=config)
        assert roots == [remote, local]
        store = CompanyScriptStore(tmp_path, config=config)
        names = {s.name for s in store.list_scripts()}
        assert "remote_pkg" in names


def test_local_script_overrides_remote_name(tmp_path: Path):
    remote = tmp_path / "remote" / "scripts"
    remote.mkdir(parents=True)
    remote_pkg = remote / "shared_name"
    remote_pkg.mkdir()
    (remote_pkg / "script.yaml").write_text(
        "name: shared_name\ndescription: remote\nentry: main.py\nruntime: python3\n",
        encoding="utf-8",
    )
    (remote_pkg / "main.py").write_text("print('remote')\n", encoding="utf-8")

    local = tmp_path / "scripts" / "shared_name"
    local.mkdir(parents=True)
    (local / "script.yaml").write_text(
        "name: shared_name\ndescription: local\nentry: main.py\nruntime: python3\n",
        encoding="utf-8",
    )
    (local / "main.py").write_text("print('local')\n", encoding="utf-8")

    config = AlfredConfig(scripts=ScriptsConfig(remote=ScriptsRemoteConfig(repo="Org/repo")))
    with patch(
        "backend.integrations.company_scripts.paths_helper.remote_scripts_root",
        return_value=remote,
    ):
        store = CompanyScriptStore(tmp_path, config=config)
        script = store.get("shared_name")
        assert script is not None
        assert script.description == "local"


@patch("backend.integrations.company_scripts.sync.WorkspaceMirrorManager")
def test_sync_scripts_repository_requires_git_token(mock_mirror_cls, tmp_path: Path):
    from backend.integrations.company_scripts.sync import sync_scripts_repository

    config = AlfredConfig(
        scripts=ScriptsConfig(remote=ScriptsRemoteConfig(repo="FlexyPe/alfred_scripts")),
    )
    config.git.enabled = True
    config.git.token = ""
    result = sync_scripts_repository(config, tmp_path)
    assert not result.get("ok")
    assert "Git token" in result.get("message", "")
    mock_mirror_cls.assert_not_called()
