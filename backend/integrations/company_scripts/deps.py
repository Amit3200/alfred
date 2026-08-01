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
            repo_root / "requirements.txt",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def ensure_scripts_venv(
    config: ScriptsConfig,
    data_dir: Path | None,
    *,
    requirements_file: Path | None,
) -> dict[str, str | bool | None]:
    """Create or refresh `.alfred/scripts-venv` when using isolated python_mode."""
    if config.remote.python_mode == "alfred":
        return {
            "ok": True,
            "skipped": True,
            "message": "python_mode=alfred uses Alfred's interpreter (no scripts venv).",
            "python": sys.executable,
        }
    if requirements_file is None:
        return {
            "ok": True,
            "skipped": True,
            "message": "No requirements.txt found — using system/alfred python until deps are added.",
            "python": resolve_python_executable(config, data_dir),
        }

    venv_dir = scripts_venv_dir(data_dir)
    python_bin = scripts_venv_python(data_dir)
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

    if python_bin is None:
        return {"ok": False, "message": "Scripts venv was created but python binary is missing."}

    try:
        subprocess.run(
            [str(python_bin), "-m", "pip", "install", "-r", str(requirements_file), "-q"],
            check=True,
            capture_output=True,
            text=True,
            timeout=max(60, config.remote.install_timeout_seconds),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()[:2000]
        logger.warning("Scripts requirements install failed: %s", detail)
        return {
            "ok": False,
            "message": f"pip install failed for {requirements_file.name}: {detail}",
            "python": str(python_bin),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "pip install timed out for scripts requirements."}

    return {
        "ok": True,
        "skipped": False,
        "message": f"Installed requirements from {requirements_file.name}",
        "python": str(python_bin),
        "requirements": str(requirements_file),
    }
