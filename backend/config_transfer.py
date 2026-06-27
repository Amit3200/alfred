"""Export and import Alfred configuration bundles (.zip)."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

MAX_IMPORT_BYTES = 50 * 1024 * 1024
ALLOWED_ROOT_FILES = frozenset({"config.yaml", "secrets.enc", ".key"})
ALLOWED_PREFIXES = ("playbooks/", "branding/")


class ConfigImportError(ValueError):
    """Raised when an import archive is invalid or unsafe."""


def normalize_arcname(name: str) -> str:
    return Path(name).as_posix().lstrip("/")


def is_allowed_arcname(name: str) -> bool:
    arcname = normalize_arcname(name)
    if not arcname or arcname.endswith("/"):
        return False
    parts = arcname.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    if arcname in ALLOWED_ROOT_FILES:
        return True
    return any(arcname.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def collect_export_files(data_dir: Path) -> list[tuple[Path, str]]:
    """Return ``(absolute_path, zip_arcname)`` pairs for export."""
    files: list[tuple[Path, str]] = []

    for fname in sorted(ALLOWED_ROOT_FILES):
        fpath = data_dir / fname
        if fpath.is_file():
            files.append((fpath, fname))

    for subdir in ("playbooks", "branding"):
        root = data_dir / subdir
        if not root.is_dir():
            continue
        for fpath in sorted(root.rglob("*")):
            if fpath.is_file():
                rel = fpath.relative_to(data_dir).as_posix()
                files.append((fpath, rel))

    return files


def build_export_zip(data_dir: Path, dest: Path) -> int:
    files = collect_export_files(data_dir)
    if not files:
        raise ConfigImportError("No configuration files found to export")
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath, arcname in files:
            zf.write(fpath, arcname)
    return len(files)


def import_config_zip(data_dir: Path, content: bytes) -> list[str]:
    """Validate and extract an Alfred config zip into *data_dir*."""
    if not content:
        raise ConfigImportError("Import file is empty")
    if len(content) > MAX_IMPORT_BYTES:
        raise ConfigImportError("Import file exceeds 50 MB limit")

    data_dir = data_dir.resolve()
    imported: list[str] = []

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            members = [info for info in zf.infolist() if not info.is_dir()]
            if not members:
                raise ConfigImportError("Zip archive contains no files")

            for info in members:
                arcname = normalize_arcname(info.filename)
                if not is_allowed_arcname(arcname):
                    raise ConfigImportError(f"Unsupported file in archive: {arcname}")
                dest = (data_dir / arcname).resolve()
                if data_dir not in dest.parents and dest != data_dir:
                    raise ConfigImportError(f"Unsafe path in archive: {arcname}")

            for info in members:
                arcname = normalize_arcname(info.filename)
                dest = data_dir / arcname
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
                imported.append(arcname)
    except zipfile.BadZipFile as exc:
        raise ConfigImportError("File is not a valid zip archive") from exc

    if "config.yaml" not in imported and "secrets.enc" not in imported:
        raise ConfigImportError("Archive must include config.yaml or secrets.enc")

    return sorted(imported)
