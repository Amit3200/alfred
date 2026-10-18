"""Tests for remote company scripts repo sync and dependencies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from backend.integrations.company_scripts.catalog import CompanyScriptStore
from backend.integrations.company_scripts.deps import find_editable_package, find_requirements_file
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


def test_find_editable_package_prefers_py_pyproject(tmp_path: Path):
    repo = tmp_path / "arsenal"
    py_dir = repo / "py"
    py_dir.mkdir(parents=True)
    (py_dir / "pyproject.toml").write_text("[project]\nname='acme-scripts'\n", encoding="utf-8")
    assert find_editable_package(repo) == py_dir.resolve()


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
            remote=ScriptsRemoteConfig(repo="Acme/scripts", path="scripts"),
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
        scripts=ScriptsConfig(remote=ScriptsRemoteConfig(repo="Acme/scripts")),
    )
    config.git.enabled = True
    config.git.token = ""
    result = sync_scripts_repository(config, tmp_path)
    assert not result.get("ok")
    assert "Git token" in result.get("message", "")
    mock_mirror_cls.assert_not_called()


@patch("backend.integrations.company_scripts.sync.ensure_scripts_venv")
@patch("backend.integrations.company_scripts.sync.WorkspaceMirrorManager")
def test_sync_passes_scripts_config_to_venv(mock_mirror_cls, mock_venv, tmp_path: Path):
    from backend.integrations.company_scripts.sync import sync_scripts_repository
    from backend.integrations.git.mirror import _repo_dir_name
    from backend.models.config import GitConfig

    dest = tmp_path / "repos" / "shared" / _repo_dir_name("Acme/scripts")
    dest.mkdir(parents=True)
    (dest / ".git").mkdir()
    scripts = dest / "scripts"
    scripts.mkdir()
    (scripts / "requirements.txt").write_text("requests>=2.31\n", encoding="utf-8")

    mock_mirror = mock_mirror_cls.return_value
    mock_mirror.shared_root = tmp_path / "repos" / "shared"
    mock_venv.return_value = {"ok": True, "skipped": False, "message": "ok", "python": "py"}

    config = AlfredConfig(
        git=GitConfig(enabled=True, token="ghp_test", provider="github"),
        scripts=ScriptsConfig(
            remote=ScriptsRemoteConfig(repo="Acme/scripts", path="scripts"),
        ),
    )
    result = sync_scripts_repository(config, tmp_path)
    assert result.get("ok") is True
    mock_venv.assert_called_once()
    passed_config = mock_venv.call_args.args[0]
    assert isinstance(passed_config, ScriptsConfig)
    assert passed_config.remote.python_mode == "isolated"
    assert mock_venv.call_args.kwargs.get("editable_package") is None


@patch("backend.integrations.company_scripts.sync.ensure_scripts_venv")
def test_setup_scripts_dependencies_skips_git_when_cloned(mock_venv, tmp_path: Path):
    from backend.integrations.company_scripts.sync import setup_scripts_dependencies
    from backend.integrations.git.mirror import _repo_dir_name
    from backend.models.config import GitConfig

    dest = tmp_path / "repos" / "shared" / _repo_dir_name("Acme/scripts")
    dest.mkdir(parents=True)
    (dest / "output").mkdir()
    (dest / "py").mkdir()
    (dest / "py" / "pyproject.toml").write_text("[project]\nname='acme-scripts'\n", encoding="utf-8")
    mock_venv.return_value = {
        "ok": True,
        "skipped": False,
        "message": "Installed editable py",
        "python": "py",
        "editable": str(dest / "py"),
    }
    config = AlfredConfig(
        git=GitConfig(enabled=True, token="ghp_test", provider="github"),
        scripts=ScriptsConfig(
            remote=ScriptsRemoteConfig(repo="Acme/scripts", path="output"),
        ),
    )
    result = setup_scripts_dependencies(config, tmp_path, pull=False)
    assert result.get("ok") is True
    mock_venv.assert_called_once()
    assert mock_venv.call_args.kwargs.get("editable_package") == (dest / "py").resolve()
    assert mock_venv.call_args.kwargs.get("force") is True


def test_ensure_scripts_venv_skips_when_stamp_matches(tmp_path: Path, monkeypatch):
    from backend.integrations.company_scripts.deps import _deps_stamp, ensure_scripts_venv

    req = tmp_path / "requirements.txt"
    req.write_text("requests>=2.31\n", encoding="utf-8")
    venv = tmp_path / "scripts-venv"
    venv.mkdir()
    python = venv / "bin" / "python3"
    python.parent.mkdir()
    python.write_text("", encoding="utf-8")
    stamp = _deps_stamp(requirements_file=req, editable_package=None)
    (venv / ".alfred-deps-stamp").write_text(stamp, encoding="utf-8")

    monkeypatch.setattr(
        "backend.integrations.company_scripts.deps.scripts_venv_dir",
        lambda _data_dir: venv,
    )
    monkeypatch.setattr(
        "backend.integrations.company_scripts.deps.scripts_venv_python",
        lambda _data_dir: python,
    )

    def _fail_run(*_args, **_kwargs):
        raise AssertionError("pip should not run when deps stamp matches")

    monkeypatch.setattr("backend.integrations.company_scripts.deps.subprocess.run", _fail_run)
    config = ScriptsConfig()
    result = ensure_scripts_venv(config, tmp_path, requirements_file=req)
    assert result.get("ok") is True
    assert result.get("skipped") is True