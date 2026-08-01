"""Tools for curated company scripts in `.alfred/scripts/`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.company_scripts.catalog import CompanyScriptStore
from backend.integrations.company_scripts.filesystem import (
    ScriptFilesystemError,
    create_script_package,
    read_script_file,
    write_script_file,
)
from backend.integrations.company_scripts.runner import run_company_script
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

LIST_COMPANY_SCRIPTS = ToolSchema(
    name="list_company_scripts",
    description=(
        "List scripts installed under .alfred/scripts/ (nested folders supported). "
        "Each package has a script.yaml manifest, entry point, and optional helper files. "
        "Use before run_company_script when unsure which script or args apply."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)

READ_COMPANY_SCRIPT_FILE = ToolSchema(
    name="read_company_script_file",
    description=(
        "Read a file from `.alfred/scripts/` before editing. "
        "Path is relative to the scripts root (e.g. `checkout/daily_report/main.py`)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "relative_path": {
                "type": "string",
                "description": "File path under `.alfred/scripts/` (e.g. ops/report/script.yaml).",
            },
        },
        "required": ["relative_path"],
    },
)

WRITE_COMPANY_SCRIPT_FILE = ToolSchema(
    name="write_company_script_file",
    description=(
        "Create or update a file under `.alfred/scripts/`. "
        "Use for manifest (`script.yaml`), entry points, and helper modules. "
        "Prefer `create_company_script_package` first when starting a new package."
    ),
    parameters={
        "type": "object",
        "properties": {
            "relative_path": {
                "type": "string",
                "description": "File path under `.alfred/scripts/` (e.g. ops/report/lib/helpers.py).",
            },
            "content": {
                "type": "string",
                "description": "Full file contents to write.",
            },
            "create_if_missing": {
                "type": "boolean",
                "description": "Create the file when it does not exist (default true).",
            },
        },
        "required": ["relative_path", "content"],
    },
)

CREATE_COMPANY_SCRIPT_PACKAGE = ToolSchema(
    name="create_company_script_package",
    description=(
        "Scaffold a new script package folder with `script.yaml` and a starter entry file. "
        "Then refine files with `write_company_script_file` and reference the package name in "
        "playbooks (`scripts:`) or schedules (`run_company_script`)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "package_path": {
                "type": "string",
                "description": "Nested package path (e.g. checkout/daily_report).",
            },
            "runtime": {
                "type": "string",
                "description": "python3 | bash | sh | node | deno | go | custom",
            },
            "description": {
                "type": "string",
                "description": "Human-readable summary for the catalog.",
            },
            "entry": {
                "type": "string",
                "description": "Entry filename relative to the package (default main.py).",
            },
        },
        "required": ["package_path"],
    },
)

RUN_COMPANY_SCRIPT = ToolSchema(
    name="run_company_script",
    description=(
        "Run a curated company script from .alfred/scripts/. "
        "Scripts encode domain queries and formatting — prefer them over ad-hoc SQL when listed "
        "in the active playbook."
    ),
    parameters={
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "Script name from list_company_scripts (e.g. checkout/daily_report or daily_error_summary).",
            },
            "args": {
                "type": "object",
                "description": "Arguments object matching the script metadata (JSON keys).",
            },
        },
        "required": ["script"],
    },
)


def register_company_script_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path | None,
) -> None:
    if not config.scripts.enabled:
        return

    def list_handler(_args: dict[str, Any]) -> ToolResult:
        store = CompanyScriptStore(data_dir, config=config)
        scripts = store.list_scripts()
        return ToolResult(
            kind="company_script_list",
            data={
                "scripts": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "relative_path": s.relative_path,
                        "runtime": s.runtime,
                        "entry": s.entry.relative_to(s.package_dir).as_posix(),
                        "package_dir": s.relative_path,
                        "files": store.list_package_files(s.name),
                        "args": [
                            {
                                "name": a.name,
                                "description": a.description,
                                "required": a.required,
                                "default": a.default,
                            }
                            for a in s.args
                        ],
                    }
                    for s in scripts
                ]
            },
        )

    def read_handler(args: dict[str, Any]) -> ToolResult:
        relative_path = str(args.get("relative_path") or "").strip()
        if not relative_path:
            return ToolResult.error("relative_path is required.")
        try:
            data = read_script_file(data_dir, relative_path)
            return ToolResult(kind="company_script_file", data=data)
        except ScriptFilesystemError as exc:
            return ToolResult.error(str(exc))

    def write_handler(args: dict[str, Any]) -> ToolResult:
        relative_path = str(args.get("relative_path") or "").strip()
        content = args.get("content")
        if not relative_path:
            return ToolResult.error("relative_path is required.")
        if not isinstance(content, str):
            return ToolResult.error("content is required.")
        create_if_missing = bool(args.get("create_if_missing", True))
        try:
            data = write_script_file(
                data_dir,
                relative_path,
                content,
                create_if_missing=create_if_missing,
            )
            return ToolResult(kind="company_script_write", data=data)
        except ScriptFilesystemError as exc:
            return ToolResult.error(str(exc))

    def create_package_handler(args: dict[str, Any]) -> ToolResult:
        package_path = str(args.get("package_path") or "").strip()
        if not package_path:
            return ToolResult.error("package_path is required.")
        try:
            data = create_script_package(
                data_dir,
                package_path=package_path,
                runtime=str(args.get("runtime") or "python3").strip(),
                description=str(args.get("description") or "Company script package").strip(),
                entry=str(args.get("entry") or "main.py").strip(),
            )
            return ToolResult(kind="company_script_package", data=data)
        except ScriptFilesystemError as exc:
            return ToolResult.error(str(exc))

    def run_handler(args: dict[str, Any]) -> ToolResult:
        script = str(args.get("script") or "").strip()
        if not script:
            return ToolResult.error("script is required.")
        raw_args = args.get("args")
        script_args = raw_args if isinstance(raw_args, dict) else None
        try:
            data = run_company_script(
                config,
                script_name=script,
                args=script_args,
                data_dir=data_dir,
            )
            return ToolResult(kind="company_script_run", data=data)
        except (ValueError, RuntimeError) as exc:
            return ToolResult.error(str(exc))

    registry.register(LIST_COMPANY_SCRIPTS, list_handler)
    registry.register(READ_COMPANY_SCRIPT_FILE, read_handler)
    registry.register(WRITE_COMPANY_SCRIPT_FILE, write_handler)
    registry.register(CREATE_COMPANY_SCRIPT_PACKAGE, create_package_handler)
    registry.register(RUN_COMPANY_SCRIPT, run_handler)
