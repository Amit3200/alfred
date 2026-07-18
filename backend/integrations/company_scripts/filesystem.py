"""Shared read/write helpers for `.alfred/scripts/` (admin API + agent tools)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.integrations.company_scripts.catalog import CompanyScript, CompanyScriptStore
from backend.integrations.company_scripts.manifest import assert_safe_relative_path, is_manifest_file
from backend.paths import company_scripts_dir

MAX_SCRIPT_FILE_BYTES = 512 * 1024
EDITABLE_SUFFIXES = {
    ".py",
    ".yaml",
    ".yml",
    ".sh",
    ".bash",
    ".js",
    ".mjs",
    ".ts",
    ".go",
    ".sql",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".ini",
    ".cfg",
}


class ScriptFilesystemError(ValueError):
    """Invalid path or content for company script files."""


def scripts_root(data_dir: Path | None) -> Path:
    root = company_scripts_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def invalidate_script_store(data_dir: Path | None) -> None:
    CompanyScriptStore(data_dir).reload()


def iso_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def resolve_script_path(
    root: Path,
    relative: str,
    *,
    must_exist: bool = False,
) -> Path:
    safe = assert_safe_relative_path(relative)
    path = (root / safe).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise ScriptFilesystemError("Invalid path")
    if must_exist and not path.exists():
        raise ScriptFilesystemError(f"Path {relative!r} not found")
    suffix = path.suffix.lower()
    if path.is_file() and suffix and suffix not in EDITABLE_SUFFIXES:
        raise ScriptFilesystemError(f"Unsupported file type: {suffix}")
    return path


def default_package_files(runtime: str, entry: str, description: str) -> dict[str, str]:
    manifest = (
        f"name: placeholder\n"
        f"description: {description}\n"
        f"entry: {entry}\n"
        f"runtime: {runtime}\n"
        "args: []\n"
    )
    if runtime == "python3" or entry.endswith(".py"):
        main = (
            "#!/usr/bin/env python3\n"
            '"""Company script entry point — invoked by Alfred run_company_script."""\n\n'
            "import json\n"
            "import os\n"
            "import sys\n\n\n"
            "def main() -> int:\n"
            '    raw = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("ALFRED_SCRIPT_ARGS", "{}")\n'
            "    args = json.loads(raw or \"{}\")\n"
            "    print(json.dumps({\"ok\": True, \"args\": args}))\n"
            "    return 0\n\n\n"
            'if __name__ == "__main__":\n'
            "    raise SystemExit(main())\n"
        )
        return {"script.yaml": manifest, entry: main}
    if runtime in {"bash", "sh"} or entry.endswith(".sh"):
        main = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'ARGS="${1:-${ALFRED_SCRIPT_ARGS:-{}}}"\n'
            'echo "Received args: $ARGS"\n'
        )
        return {"script.yaml": manifest, entry or "main.sh": main}
    return {"script.yaml": manifest, entry: "# Add your script\n"}


def package_row(store: CompanyScriptStore, script: CompanyScript) -> dict[str, Any]:
    return {
        "name": script.name,
        "description": script.description,
        "runtime": script.runtime,
        "entry": script.entry.relative_to(script.package_dir).as_posix(),
        "relative_path": script.relative_path,
        "kind": script.kind,
        "file_count": script.file_count,
        "files": store.list_package_files(script.name),
        "args": [
            {
                "name": arg.name,
                "description": arg.description,
                "required": arg.required,
                "default": arg.default,
            }
            for arg in script.args
        ],
    }


def read_script_file(data_dir: Path | None, relative_path: str) -> dict[str, Any]:
    root = scripts_root(data_dir)
    path = resolve_script_path(root, relative_path, must_exist=True)
    if not path.is_file():
        raise ScriptFilesystemError("File not found")
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "content": path.read_text(encoding="utf-8"),
        "size_bytes": path.stat().st_size,
        "updated_at": iso_mtime(path),
        "is_manifest": is_manifest_file(path),
    }


def write_script_file(
    data_dir: Path | None,
    relative_path: str,
    content: str,
    *,
    create_if_missing: bool = False,
    allow_overwrite: bool = True,
) -> dict[str, Any]:
    root = scripts_root(data_dir)
    rel = assert_safe_relative_path(relative_path)
    path = resolve_script_path(root, rel)
    if path.exists() and not path.is_file():
        raise ScriptFilesystemError(f"Path {rel!r} is not a file")
    if path.exists() and not allow_overwrite:
        raise ScriptFilesystemError(f"File {rel!r} already exists")
    if not path.exists():
        if not create_if_missing:
            raise ScriptFilesystemError(f"File {rel!r} not found — set create_if_missing=true to create it")
        path.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_SCRIPT_FILE_BYTES:
        raise ScriptFilesystemError("File exceeds 512 KB limit")
    created = not path.exists()
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    invalidate_script_store(data_dir)
    return {
        "ok": True,
        "relative_path": path.relative_to(root).as_posix(),
        "created": created,
        "updated_at": iso_mtime(path),
        "is_manifest": is_manifest_file(path),
    }


def create_script_package(
    data_dir: Path | None,
    *,
    package_path: str,
    runtime: str = "python3",
    description: str = "Company script package",
    entry: str = "main.py",
) -> dict[str, Any]:
    root = scripts_root(data_dir)
    package_rel = assert_safe_relative_path(package_path)
    package_dir = resolve_script_path(root, package_rel)
    if package_dir.exists():
        raise ScriptFilesystemError(f"Package path {package_rel!r} already exists")
    package_dir.mkdir(parents=True, exist_ok=True)
    files = default_package_files(runtime, entry, description)
    manifest = files.pop("script.yaml")
    manifest = manifest.replace("name: placeholder", f"name: {package_rel}")
    (package_dir / "script.yaml").write_text(manifest, encoding="utf-8")
    for rel, file_content in files.items():
        target = package_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            file_content if file_content.endswith("\n") else file_content + "\n",
            encoding="utf-8",
        )
    invalidate_script_store(data_dir)
    store = CompanyScriptStore(data_dir)
    script = store.get(package_rel)
    if script is None:
        raise ScriptFilesystemError("Package created but failed to index")
    return {"ok": True, "package": package_row(store, script)}
