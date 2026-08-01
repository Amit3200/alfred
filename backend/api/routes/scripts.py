"""Admin API for company script packages (`.alfred/scripts/`)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.integrations.company_scripts.catalog import CompanyScriptStore
from backend.integrations.company_scripts.filesystem import (
    ScriptFilesystemError,
    create_script_package,
    invalidate_script_store,
    iso_mtime,
    package_row,
    read_script_file,
    resolve_script_path,
    scripts_root,
    write_script_file,
)
from backend.integrations.company_scripts.sync import load_scripts_sync_state, sync_scripts_repository
from backend.paths import bundled_scripts_examples_dir

router = APIRouter(prefix="/scripts", tags=["scripts"])


class ScriptFileWriteBody(BaseModel):
    content: str = Field(..., min_length=0)


class ScriptFileCreateBody(BaseModel):
    relative_path: str = Field(..., min_length=1)
    content: str = Field(default="")


class ScriptPackageCreateBody(BaseModel):
    package_path: str = Field(..., min_length=1)
    runtime: str = Field(default="python3")
    description: str = Field(default="Company script package")
    entry: str = Field(default="main.py")


def _http_error(exc: ScriptFilesystemError, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=str(exc))


def _resolve_path(root: Path, relative: str, *, must_exist: bool = False) -> Path:
    try:
        return resolve_script_path(root, relative, must_exist=must_exist)
    except ScriptFilesystemError as exc:
        raise _http_error(exc, status_code=404 if must_exist else 400) from exc


@router.get("")
def list_scripts(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    root = scripts_root(manager.data_dir)
    store = CompanyScriptStore(manager.data_dir, config=config)
    packages = [package_row(store, script) for script in store.list_scripts()]
    remote = config.scripts.remote
    return {
        "directory": str(root),
        "packages": packages,
        "example_available": bundled_scripts_examples_dir().is_dir(),
        "remote": {
            "repo": remote.repo,
            "branch": remote.branch,
            "path": remote.path,
            "python_mode": remote.python_mode,
            "synced": load_scripts_sync_state(manager.data_dir),
        },
    }


@router.post("/sync")
def sync_scripts(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    result = sync_scripts_repository(config, manager.data_dir)
    if not result.get("ok") and not result.get("skipped"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Scripts sync failed")
    return result


@router.get("/example")
def get_example_package(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    example_root = bundled_scripts_examples_dir() / "daily_error_summary"
    if not example_root.is_dir():
        raise HTTPException(status_code=404, detail="Example script package not found")
    files = {
        path.relative_to(example_root).as_posix(): path.read_text(encoding="utf-8")
        for path in example_root.rglob("*")
        if path.is_file()
    }
    return {"package_path": "daily_error_summary", "files": files}


@router.get("/files/{relative_path:path}")
def get_script_file(
    relative_path: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return read_script_file(manager.data_dir, relative_path)
    except ScriptFilesystemError as exc:
        raise _http_error(exc, status_code=404) from exc


@router.post("/packages")
def create_script_package_route(
    body: ScriptPackageCreateBody,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return create_script_package(
            manager.data_dir,
            package_path=body.package_path,
            runtime=body.runtime,
            description=body.description,
            entry=body.entry,
        )
    except ScriptFilesystemError as exc:
        status = 409 if "already exists" in str(exc) else 400
        raise _http_error(exc, status_code=status) from exc


@router.post("/files/{relative_path:path}")
def create_script_file(
    relative_path: str,
    body: ScriptFileCreateBody,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    rel = body.relative_path or relative_path
    try:
        return write_script_file(
            manager.data_dir,
            rel,
            body.content,
            create_if_missing=True,
            allow_overwrite=False,
        )
    except ScriptFilesystemError as exc:
        status = 409 if "already exists" in str(exc) else 400
        raise _http_error(exc, status_code=status) from exc


@router.put("/files/{relative_path:path}")
def save_script_file(
    relative_path: str,
    body: ScriptFileWriteBody,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return write_script_file(
            manager.data_dir,
            relative_path,
            body.content,
            create_if_missing=False,
        )
    except ScriptFilesystemError as exc:
        raise _http_error(exc, status_code=404 if "not found" in str(exc) else 400) from exc


@router.delete("/files/{relative_path:path}")
def delete_script_path(
    relative_path: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = scripts_root(manager.data_dir)
    path = _resolve_path(root, relative_path, must_exist=True)
    rel = path.relative_to(root).as_posix()
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    invalidate_script_store(manager.data_dir)
    return {"ok": True, "removed": rel}


@router.delete("/packages/{package_name:path}")
def delete_script_package(
    package_name: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    root = scripts_root(manager.data_dir)
    store = CompanyScriptStore(manager.data_dir, config=manager.load_merged()[0])
    script = store.get(package_name)
    if script is None:
        raise HTTPException(status_code=404, detail=f"Script package {package_name!r} not found")
    rel = script.package_dir.relative_to(root).as_posix()
    shutil.rmtree(script.package_dir)
    invalidate_script_store(manager.data_dir)
    return {"ok": True, "removed": rel}
