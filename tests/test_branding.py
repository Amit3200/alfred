"""Tests for company branding SDK."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.branding.display import branding_display_title, branding_identity_line
from backend.branding.service import BrandingService
from backend.branding.store import LogoStore
from backend.config_manager import ConfigManager
from backend.models.config import BrandingConfig


def test_branding_display_title_with_company():
    branding = BrandingConfig(company_name="Acme Corp")
    assert branding_display_title(branding) == "Alfred × Acme Corp"


def test_branding_identity_line_with_company():
    branding = BrandingConfig(company_name="Acme Corp")
    line = branding_identity_line(branding)
    assert "Acme Corp" in line
    assert "Alfred × Acme Corp" in line


def test_logo_store_save_and_clear(tmp_path: Path):
    store = LogoStore(tmp_path)
    store.save(b"\x89PNG\r\n\x1a\n", extension="png")
    existing = store.existing()
    assert existing is not None
    assert existing[0].name == "logo.png"
    store.clear()
    assert store.existing() is None


def test_branding_service_upload_and_snapshot(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    manager.init(company_name="Flexype")
    service = BrandingService(manager)
    snapshot = service.upload_logo(b"\x89PNG\r\n\x1a\n", content_type="image/png")
    assert snapshot["has_logo"] is True
    assert snapshot["display_title"] == "Alfred × Flexype"
    assert snapshot["logo_url"].startswith("/api/branding/logo?v=")


def test_logo_rejects_large_file(tmp_path: Path):
    store = LogoStore(tmp_path)
    with pytest.raises(ValueError, match="2 MB"):
        store.save(b"x" * (2 * 1024 * 1024 + 1), extension="png")
