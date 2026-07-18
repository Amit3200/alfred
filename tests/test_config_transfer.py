"""Tests for config export/import bundles."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import yaml

from backend.config_manager import ConfigManager
from backend.config_transfer import (
    ConfigImportError,
    build_export_zip,
    collect_export_files,
    import_config_zip,
    is_allowed_arcname,
)
from backend.models.config import default_config


def test_is_allowed_arcname():
    assert is_allowed_arcname("config.yaml")
    assert is_allowed_arcname("playbooks/foo.md")
    assert is_allowed_arcname("branding/logo.png")
    assert not is_allowed_arcname("../secrets.enc")
    assert not is_allowed_arcname("alfred.db")
    assert not is_allowed_arcname("playbooks/../../etc/passwd")


def test_export_includes_branding(tmp_path: Path):
    data_dir = tmp_path / ".alfred"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text("initialized: true\n", encoding="utf-8")
    branding = data_dir / "branding"
    branding.mkdir()
    (branding / "logo.png").write_bytes(b"\x89PNG")

    names = {arc for _, arc in collect_export_files(data_dir)}
    assert "config.yaml" in names
    assert "branding/logo.png" in names


def test_import_restores_config_and_branding(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    config = default_config()
    config.initialized = True
    config.branding.company_name = "Acme Corp"
    config.branding.setup_completed = True
    (source / "config.yaml").write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    branding = source / "branding"
    branding.mkdir()
    (branding / "logo.png").write_bytes(b"\x89PNG")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("config.yaml", (source / "config.yaml").read_text(encoding="utf-8"))
        zf.write(branding / "logo.png", "branding/logo.png")

    dest = tmp_path / "dest"
    dest.mkdir()
    imported = import_config_zip(dest, buf.getvalue())
    assert "config.yaml" in imported
    assert "branding/logo.png" in imported
    assert (dest / "branding" / "logo.png").exists()

    manager = ConfigManager(dest)
    loaded = manager.load_config()
    assert loaded.branding.company_name == "Acme Corp"


def test_import_rejects_unsupported_files(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("alfred.db", b"bad")
    with pytest.raises(ConfigImportError, match="Unsupported"):
        import_config_zip(tmp_path, buf.getvalue())


def test_build_export_zip_roundtrip(tmp_path: Path):
    data_dir = tmp_path / ".alfred"
    data_dir.mkdir()
    manager = ConfigManager(data_dir)
    manager.init(company_name="Acme Corp")

    zip_path = tmp_path / "export.zip"
    count = build_export_zip(data_dir, zip_path)
    assert count >= 1
    assert zip_path.exists()

    target = tmp_path / "target"
    target.mkdir()
    imported = import_config_zip(target, zip_path.read_bytes())
    assert "config.yaml" in imported
