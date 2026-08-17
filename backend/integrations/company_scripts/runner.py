"""Execute company script packages from `.alfred/scripts/`."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from backend.integrations.company_scripts.catalog import CompanyScriptStore
from backend.integrations.company_scripts.deps import (
    build_script_pythonpath,
    resolve_python_executable,
)
from backend.integrations.company_scripts.paths_helper import script_catalog_roots
from backend.integrations.company_scripts.manifest import build_command, normalize_script_ref
from backend.models.config import AlfredConfig


def _validate_args(script_args: list[Any], raw: dict[str, Any] | None) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("args must be a JSON object (string keys).")
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name or not name.replace("_", "").isalnum():
            raise ValueError(f"Invalid arg name: {key!r}")
        cleaned[name] = str(value)
    known = {arg.name for arg in script_args}
    if known:
        unknown = sorted(set(cleaned) - known)
        if unknown:
            raise ValueError(f"Unknown args for script: {', '.join(unknown)}")
        for arg in script_args:
            if arg.required and arg.name not in cleaned:
                raise ValueError(f"Missing required arg: {arg.name}")
    for arg in script_args:
        if arg.name not in cleaned and arg.default is not None:
            cleaned[arg.name] = arg.default
    return cleaned


def run_company_script(
    config: AlfredConfig,
    *,
    script_name: str,
    args: dict[str, Any] | None = None,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    if not config.scripts.enabled:
        raise ValueError("Company scripts are disabled. Set scripts.enabled: true in config.")

    store = CompanyScriptStore(data_dir, config=config)
    script = store.get(normalize_script_ref(script_name))
    if script is None:
        available = ", ".join(s.name for s in store.list_scripts()) or "(none)"
        raise ValueError(f"Unknown company script {script_name!r}. Available: {available}")

    validated = _validate_args(script.args, args)
    timeout = config.scripts.timeout_seconds
    args_json = json.dumps(validated, sort_keys=True)

    manifest_path = next(
        (script.package_dir / name for name in ("script.yaml", "alfred.script.yaml") if (script.package_dir / name).is_file()),
        None,
    )
    meta: dict[str, Any] = {}
    if manifest_path and manifest_path.is_file():
        from backend.integrations.company_scripts.manifest import load_manifest

        meta = load_manifest(manifest_path)
    else:
        for suffix in (".yaml", ".yml"):
            sidecar = script.entry.with_suffix(suffix)
            if sidecar.is_file():
                from backend.integrations.company_scripts.manifest import load_manifest

                meta = load_manifest(sidecar)
                break

    cmd = build_command(
        runtime=script.runtime,
        entry=script.entry,
        package_dir=script.package_dir,
        args_json=args_json,
        meta=meta,
        python_executable=resolve_python_executable(config.scripts, data_dir)
        if script.runtime == "python3"
        else None,
    )

    env = os.environ.copy()
    env["ALFRED_SCRIPT_ARGS"] = args_json
    env["ALFRED_DATA_DIR"] = str(store.directory.parent)
    env["ALFRED_SCRIPT_NAME"] = script.name
    env["ALFRED_SCRIPT_ENTRY"] = script.entry.relative_to(script.package_dir).as_posix()
    env["ALFRED_SCRIPTS_PYTHON"] = resolve_python_executable(config.scripts, data_dir)
    env["PYTHONPATH"] = build_script_pythonpath(
        script_catalog_roots(data_dir, config=config) + [script.package_dir],
        existing=env.get("PYTHONPATH", ""),
    )

    try:
        result = subprocess.run(
            cmd,
            cwd=str(script.package_dir),
            capture_output=True,
            text=True,
            timeout=max(5, min(timeout, 1800)),
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Script timed out after {timeout}s.") from exc
    except FileNotFoundError as exc:
        raise ValueError(f"Runtime executable not found for {script.runtime!r}.") from exc

    stdout = (result.stdout or "")[:12_000]
    stderr = (result.stderr or "")[:4000]
    payload: dict[str, Any] = {
        "script": script.name,
        "runtime": script.runtime,
        "entry": script.entry.relative_to(script.package_dir).as_posix(),
        "relative_path": script.relative_path,
        "args": validated,
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }

    parsed = _try_parse_json_stdout(stdout)
    if parsed is not None:
        payload["json"] = parsed

    return payload


def _try_parse_json_stdout(stdout: str) -> Any | None:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
