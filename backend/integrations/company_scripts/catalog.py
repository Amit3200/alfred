"""Discover company script packages under `.alfred/scripts/`."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.integrations.company_scripts.manifest import (
    MANIFEST_FILENAMES,
    is_legacy_script_file,
    is_manifest_file,
    load_manifest,
    normalize_script_ref,
    package_name_from_dir,
    resolve_entry,
    runtime_from_meta,
    script_aliases,
)
from backend.integrations.company_scripts.paths_helper import script_catalog_roots
from backend.models.config import AlfredConfig
from backend.paths import bundled_scripts_examples_dir, company_scripts_dir

logger = logging.getLogger(__name__)
_META_SUFFIX = ".yaml"


@dataclass
class ScriptArg:
    name: str
    description: str = ""
    required: bool = False
    default: str | None = None


@dataclass
class CompanyScript:
    name: str
    package_dir: Path
    entry: Path
    runtime: str
    description: str = ""
    args: list[ScriptArg] = field(default_factory=list)
    relative_path: str = ""
    kind: str = "package"
    aliases: set[str] = field(default_factory=set)
    file_count: int = 0

    def format_for_prompt(self) -> str:
        lines = [
            f"- **`{self.name}`** ({self.runtime}, entry `{self.entry.name}`) — "
            f"{self.description or 'No description.'}"
        ]
        if self.file_count > 1:
            lines.append(f"  Module: {self.file_count} file(s) under `{self.package_dir.name}/`")
        if self.args:
            arg_bits = []
            for arg in self.args:
                req = "required" if arg.required else "optional"
                default = f", default `{arg.default}`" if arg.default else ""
                desc = f" — {arg.description}" if arg.description else ""
                arg_bits.append(f"`{arg.name}` ({req}{default}){desc}")
            lines.append(f"  Args: {', '.join(arg_bits)}")
        else:
            lines.append("  Args: none (pass `{}` or omit `args`).")
        return "\n".join(lines)


class CompanyScriptStore:
    """Load script packages from remote Git repo and local `.alfred/scripts/`."""

    def __init__(self, data_dir: Path | None = None, *, config: AlfredConfig | None = None) -> None:
        self.data_dir = data_dir
        self.config = config
        self.directory = company_scripts_dir(data_dir)
        self.roots = script_catalog_roots(data_dir, config=config)
        self._scripts: list[CompanyScript] | None = None
        self._cache_mtime: float = 0.0

    def reload(self) -> None:
        self.roots = script_catalog_roots(self.data_dir, config=self.config)
        self._scripts = None
        self._cache_mtime = 0.0

    def list_scripts(self) -> list[CompanyScript]:
        mtime = max((self._tree_mtime(root) for root in self.roots), default=0.0)
        if self._scripts is None or mtime > self._cache_mtime:
            self._scripts = self._load_scripts()
            self._cache_mtime = mtime
        return list(self._scripts)

    def get(self, name: str) -> CompanyScript | None:
        key = normalize_script_ref(name)
        for script in self.list_scripts():
            if key in script.aliases:
                return script
        return None

    def format_catalog_for_prompt(self, *, script_names: list[str] | None = None) -> str:
        scripts = self.list_scripts()
        if script_names:
            allowed = {normalize_script_ref(n) for n in script_names if n.strip()}
            expanded = set()
            for item in allowed:
                expanded.update(script_aliases(item))
            scripts = [s for s in scripts if s.aliases & expanded]
        if not scripts:
            return ""
        lines = [
            "## Company scripts",
            "Prefer `run_company_script` — packages may come from scripts.remote.repo and/or `.alfred/scripts/`.",
            "",
        ]
        for script in sorted(scripts, key=lambda item: item.name):
            lines.append(script.format_for_prompt())
        lines.append("")
        lines.append(
            "Call `run_company_script` with `script` set to the package name "
            "(path like `checkout/daily_report` or legacy `daily_report`) and "
            "`args` as a JSON object."
        )
        return "\n".join(lines)

    def list_package_files(self, package_name: str) -> list[str]:
        script = self.get(package_name)
        if script is None:
            return []
        root = script.package_dir
        return sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        )

    def _load_scripts(self) -> list[CompanyScript]:
        by_name: dict[str, CompanyScript] = {}
        for root in self.roots:
            root.mkdir(parents=True, exist_ok=True)
            for script in self._load_scripts_from_root(root):
                by_name[script.name] = script
        scripts = list(by_name.values())
        logger.info("Indexed %d company script package(s) from %d root(s)", len(scripts), len(self.roots))
        return scripts

    def _load_scripts_from_root(self, root: Path) -> list[CompanyScript]:
        scripts: list[CompanyScript] = []
        package_dirs: set[Path] = set()

        for manifest_path in sorted(self._iter_manifests(root)):
            pkg_dir = manifest_path.parent.resolve()
            try:
                scripts.append(self._parse_package(root, pkg_dir, manifest_path))
                package_dirs.add(pkg_dir)
            except Exception:
                logger.exception("Failed to load script package %s", manifest_path)

        for path in sorted(root.rglob("*")):
            if not path.is_file() or not is_legacy_script_file(path):
                continue
            if any(path.is_relative_to(d) for d in package_dirs):
                continue
            if any(is_manifest_file(sibling) for sibling in path.parent.iterdir() if sibling.is_file()):
                continue
            try:
                scripts.append(self._parse_legacy(root, path))
            except Exception:
                logger.exception("Failed to load legacy script %s", path)
        return scripts

    @staticmethod
    def _iter_manifests(root: Path):
        seen_dirs: set[Path] = set()
        for path in sorted(root.rglob("*")):
            if path.is_file() and is_manifest_file(path):
                parent = path.parent.resolve()
                if parent not in seen_dirs:
                    seen_dirs.add(parent)
                    yield path

    def _parse_package(self, root: Path, package_dir: Path, manifest_path: Path) -> CompanyScript:
        meta = load_manifest(manifest_path)
        name = package_name_from_dir(root, package_dir, meta)
        entry = resolve_entry(package_dir, meta)
        runtime = runtime_from_meta(meta, entry)
        description = str(meta.get("description") or "").strip()
        args = _parse_args(meta.get("args"))
        file_count = sum(1 for p in package_dir.rglob("*") if p.is_file())
        return CompanyScript(
            name=name,
            package_dir=package_dir,
            entry=entry,
            runtime=runtime,
            description=description,
            args=args,
            relative_path=package_dir.relative_to(root).as_posix(),
            kind="package",
            aliases=script_aliases(name),
            file_count=file_count,
        )

    def _parse_legacy(self, root: Path, path: Path) -> CompanyScript:
        rel = path.relative_to(root).as_posix()
        name = path.stem if "/" not in rel else rel.rsplit(".", 1)[0].replace("/", "/")
        meta = self._load_legacy_metadata(path)
        description = str(meta.get("description") or "").strip() or _first_docstring_line(path)
        args = _parse_args(meta.get("args"))
        runtime = runtime_from_meta(meta, path) if meta.get("runtime") else runtime_from_meta({}, path)
        return CompanyScript(
            name=name,
            package_dir=path.parent,
            entry=path,
            runtime=runtime,
            description=description,
            args=args,
            relative_path=rel,
            kind="legacy",
            aliases=script_aliases(name),
            file_count=1,
        )

    @staticmethod
    def _load_legacy_metadata(script_path: Path) -> dict[str, Any]:
        for suffix in (".yaml", ".yml"):
            meta_path = script_path.with_suffix(suffix)
            if meta_path.is_file():
                return load_manifest(meta_path)
        return {}

    @staticmethod
    def _tree_mtime(directory: Path) -> float:
        if not directory.is_dir():
            return 0.0
        latest = 0.0
        for path in directory.rglob("*"):
            if path.is_file():
                try:
                    latest = max(latest, path.stat().st_mtime)
                except OSError:
                    continue
        return latest


def _first_docstring_line(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not text.lstrip().startswith(('"""', "'''")):
        return ""
    quote = '"""' if text.lstrip().startswith('"""') else "'''"
    start = text.find(quote) + 3
    end = text.find(quote, start)
    if end == -1:
        return ""
    block = text[start:end].strip().splitlines()
    return block[0].strip() if block else ""


def _parse_args(raw: Any) -> list[ScriptArg]:
    if not isinstance(raw, list):
        return []
    args: list[ScriptArg] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            args.append(ScriptArg(name=item.strip(), required=False))
            continue
        if not isinstance(item, dict):
            continue
        arg_name = str(item.get("name") or "").strip()
        if not arg_name:
            continue
        args.append(
            ScriptArg(
                name=arg_name,
                description=str(item.get("description") or "").strip(),
                required=bool(item.get("required")),
                default=str(item.get("default")).strip() if item.get("default") is not None else None,
            )
        )
    return args


def seed_example_scripts(data_dir: Path | None) -> None:
    """Copy bundled example packages when `.alfred/scripts/` is empty."""
    dest = company_scripts_dir(data_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.rglob("script.yaml")) or any(dest.rglob("alfred.script.yaml")):
        return
    if any(dest.rglob("*.py")):
        return
    examples = bundled_scripts_examples_dir()
    if not examples.is_dir():
        return
    for path in examples.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(examples)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            shutil.copy2(path, target)
