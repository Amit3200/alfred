"""Parse company script package manifests (`script.yaml`)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

MANIFEST_FILENAMES = ("script.yaml", "alfred.script.yaml")
SUPPORTED_RUNTIMES = frozenset({"python3", "bash", "sh", "node", "deno", "go", "custom"})
_LEGACY_SUFFIXES = {".py", ".sh", ".bash", ".js", ".mjs", ".ts", ".go"}
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_/-]*$")
_SAFE_PATH_PART = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def normalize_script_ref(name: str) -> str:
    return name.strip().replace("\\", "/").strip("/").replace("__", "/")


def script_aliases(canonical_name: str) -> set[str]:
    aliases = {canonical_name, canonical_name.replace("/", "__")}
    return {a for a in aliases if a}


def load_manifest(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def package_name_from_dir(scripts_root: Path, package_dir: Path, meta: dict[str, Any]) -> str:
    raw = str(meta.get("name") or "").strip()
    if raw:
        name = normalize_script_ref(raw)
    else:
        name = package_dir.relative_to(scripts_root).as_posix()
    if not _SAFE_NAME_RE.match(name.replace("/", "-")):
        raise ValueError(f"Invalid script name {name!r}")
    return name


def resolve_entry(package_dir: Path, meta: dict[str, Any]) -> Path:
    entry_raw = str(meta.get("entry") or "main.py").strip()
    if not entry_raw or ".." in Path(entry_raw).parts:
        raise ValueError(f"Invalid entry path {entry_raw!r}")
    entry = (package_dir / entry_raw).resolve()
    if package_dir.resolve() not in entry.parents and entry != package_dir.resolve():
        raise ValueError(f"Entry must stay inside package: {entry_raw!r}")
    if not entry.is_file():
        raise ValueError(f"Entry file not found: {entry_raw!r}")
    return entry


def runtime_from_meta(meta: dict[str, Any], entry: Path) -> str:
    runtime = str(meta.get("runtime") or "").strip().lower()
    if runtime:
        if runtime not in SUPPORTED_RUNTIMES:
            raise ValueError(f"Unsupported runtime {runtime!r}")
        return runtime
    suffix = entry.suffix.lower()
    if suffix == ".py":
        return "python3"
    if suffix in {".sh", ".bash"}:
        return "bash"
    if suffix in {".js", ".mjs"}:
        return "node"
    if suffix == ".ts":
        return "deno"
    if suffix == ".go":
        return "go"
    return "custom"


def build_command(
    *,
    runtime: str,
    entry: Path,
    package_dir: Path,
    args_json: str,
    meta: dict[str, Any],
) -> list[str]:
    if runtime == "custom":
        raw_cmd = meta.get("command")
        if not isinstance(raw_cmd, list) or not raw_cmd:
            raise ValueError("runtime custom requires a non-empty command list in script.yaml")
        cmd = [str(part) for part in raw_cmd]
        return [_expand_command_token(token, entry, package_dir, args_json) for token in cmd]

    entry_rel = entry.relative_to(package_dir).as_posix()
    if runtime == "python3":
        return ["python3", entry_rel, args_json]
    if runtime in {"bash", "sh"}:
        return ["bash", entry_rel, args_json]
    if runtime == "node":
        return ["node", entry_rel, args_json]
    if runtime == "deno":
        return ["deno", "run", entry_rel, args_json]
    if runtime == "go":
        return ["go", "run", entry_rel, args_json]
    raise ValueError(f"Unsupported runtime {runtime!r}")


def _expand_command_token(token: str, entry: Path, package_dir: Path, args_json: str) -> str:
    return (
        token.replace("{args_json}", args_json)
        .replace("{entry}", entry.relative_to(package_dir).as_posix())
        .replace("{package_dir}", str(package_dir))
    )


def is_manifest_file(path: Path) -> bool:
    return path.name in MANIFEST_FILENAMES


def is_legacy_script_file(path: Path) -> bool:
    return path.suffix.lower() in _LEGACY_SUFFIXES and not path.name.startswith("_")


def assert_safe_relative_path(relative: str) -> str:
    rel = relative.strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("Invalid path")
    parts = rel.split("/")
    for part in parts:
        if part in {".", ".."} or not _SAFE_PATH_PART.match(part):
            raise ValueError(f"Invalid path segment: {part!r}")
    return rel
