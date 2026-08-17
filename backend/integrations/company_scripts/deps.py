"""Python dependency setup for remote company script packages."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Literal

from backend.models.config import ScriptsConfig
from backend.paths import scripts_venv_dir

logger = logging.getLogger(__name__)

RequirementsMode = Literal["isolated", "alfred"]


def resolve_python_executable(config: ScriptsConfig, data_dir: Path | None) -> str:
    """Return the Python binary used to run python3 company scripts."""
    mode = config.remote.python_mode
    if mode == "alfred":
        return sys.executable
    venv_python = scripts_venv_python(data_dir)
    if venv_python is not None:
        return str(venv_python)
    return sys.executable


def scripts_venv_python(data_dir: Path | None) -> Path | None:
    candidate = scripts_venv_dir(data_dir) / "bin" / "python3"
    if candidate.is_file():
        return candidate
    candidate = scripts_venv_dir(data_dir) / "bin" / "python"
    return candidate if candidate.is_file() else None


def build_script_pythonpath(roots: list[Path], *, existing: str = "") -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in (existing or "").split(":"):
        if chunk and chunk not in seen:
            seen.add(chunk)
            parts.append(chunk)
    for root in roots:
        resolved = str(root.resolve())
        if resolved not in seen:
            seen.add(resolved)
            parts.append(resolved)
    return ":".join(parts)


def find_requirements_file(
    *,
    repo_root: Path,
    scripts_root: Path,
    configured: str,
) -> Path | None:
    candidates: list[Path] = []
    if configured.strip():
        configured_path = Path(configured.strip())
        if configured_path.is_absolute():
            candidates.append(configured_path)
        else:
            candidates.extend(
                [
                    scripts_root / configured_path,
                    repo_root / configured_path,
                ]
            )
    candidates.extend(
        [
            scripts_root / "requirements.txt",
            repo_root / "py" / "requirements.txt",
            repo_root / "requirements.txt",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def find_editable_package(repo_root: Path | None) -> Path | None:
    """Arsenal-style `pip install -e ./py` when pyproject.toml is present."""
    if repo_root is None:
        return None
    for candidate in (repo_root / "py" / "pyproject.toml", repo_root / "pyproject.toml"):
        if candidate.is_file():
            return candidate.parent.resolve()
    return None


def _deps_stamp(*, requirements_file: Path | None, editable_package: Path | None) -> str:
    parts: list[str] = []
    if editable_package is not None:
        pyproject = editable_package / "pyproject.toml"
        if pyproject.is_file():
            st = pyproject.stat()
            parts.append(f"e:{st.st_mtime_ns}:{st.st_size}")
    if requirements_file is not None and requirements_file.is_file():
        st = requirements_file.stat()
        parts.append(f"r:{st.st_mtime_ns}:{st.st_size}")
    return "|".join(parts)


def ensure_scripts_venv(
    config: ScriptsConfig,
    data_dir: Path | None,
    *,
    requirements_file: Path | None,
    editable_package: Path | None = None,
    force: bool = False,
) -> dict[str, str | bool | None]:
    """Create or refresh `.alfred/scripts-venv` when using isolated python_mode.

    Mirrors arsenal `make setup-py`: venv + pip upgrade + editable install when
    `py/pyproject.toml` exists, otherwise `pip install -r requirements.txt`.
    Reinstalls when ``force`` is true or the requirements/pyproject stamp changed.
    """
    if config.remote.python_mode == "alfred":
        return {
            "ok": True,
            "skipped": True,
            "message": "python_mode=alfred uses Alfred's interpreter (no scripts venv).",
            "python": sys.executable,
        }
    if requirements_file is None and editable_package is None:
        return {
            "ok": True,
            "skipped": True,
            "message": "No requirements.txt or pyproject.toml found — using system/alfred python until deps are added.",
            "python": resolve_python_executable(config, data_dir),
        }

    venv_dir = scripts_venv_dir(data_dir)
    python_bin = scripts_venv_python(data_dir)
    created_now = False
    if python_bin is None:
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            return {"ok": False, "message": f"Failed to create scripts venv: {detail}"}
        python_bin = scripts_venv_python(data_dir)
        created_now = True

    if python_bin is None:
        return {"ok": False, "message": "Scripts venv was created but python binary is missing."}

    stamp = _deps_stamp(requirements_file=requirements_file, editable_package=editable_package)
    stamp_path = venv_dir / ".alfred-deps-stamp"
    if not force and not created_now:
        current = stamp_path.read_text(encoding="utf-8").strip() if stamp_path.is_file() else None
        if current == stamp or current is None:
            if stamp and current is None:
                stamp_path.write_text(stamp, encoding="utf-8")
            return {
                "ok": True,
                "skipped": True,
                "message": "Scripts venv already installed (deps unchanged).",
                "python": str(python_bin),
                "requirements": str(requirements_file) if requirements_file else None,
                "editable": str(editable_package) if editable_package else None,
            }

    timeout = max(60, config.remote.install_timeout_seconds)
    try:
        subprocess.run(
            [str(python_bin), "-m", "pip", "install", "-U", "pip", "-q"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if editable_package is not None:
            subprocess.run(
                [str(python_bin), "-m", "pip", "install", "-e", str(editable_package), "-q"],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        if requirements_file is not None:
            subprocess.run(
                [str(python_bin), "-m", "pip", "install", "-r", str(requirements_file), "-q"],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()[:2000]
        logger.warning("Scripts requirements install failed: %s", detail)
        label = (
            editable_package.name
            if editable_package is not None and requirements_file is None
            else (requirements_file.name if requirements_file else "dependencies")
        )
        return {
            "ok": False,
            "message": f"pip install failed for {label}: {detail}",
            "python": str(python_bin),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "pip install timed out for scripts requirements."}

    parts: list[str] = []
    if editable_package is not None:
        parts.append(f"editable {editable_package.name}")
    if requirements_file is not None:
        parts.append(requirements_file.name)
    installed = " + ".join(parts) if parts else "dependencies"
    if stamp:
        stamp_path.write_text(stamp, encoding="utf-8")
    return {
        "ok": True,
        "skipped": False,
        "message": f"Installed {installed} (arsenal-style setup into scripts-venv)",
        "python": str(python_bin),
        "requirements": str(requirements_file) if requirements_file else None,
        "editable": str(editable_package) if editable_package else None,
    }
