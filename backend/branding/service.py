"""Branding service — config + logo storage."""

from __future__ import annotations

from pathlib import Path

from backend.branding.display import public_branding_snapshot
from backend.branding.store import LogoStore
from backend.config_manager import ConfigManager
from backend.models.config import AlfredConfig, BrandingConfig


class BrandingService:
    """High-level branding operations for API and CLI."""

    def __init__(self, manager: ConfigManager) -> None:
        self._manager = manager
        self._store = LogoStore(manager.data_dir)

    @property
    def store(self) -> LogoStore:
        return self._store

    def snapshot(self, config: AlfredConfig | None = None) -> dict[str, str | bool]:
        cfg = config or self._manager.load_config()
        existing = self._store.existing()
        logo_url = self.logo_url(existing[0] if existing else None)
        return public_branding_snapshot(
            cfg,
            logo_url=logo_url,
            has_logo=existing is not None,
        )

    def logo_path(self) -> Path | None:
        existing = self._store.existing()
        return existing[0] if existing else None

    def logo_url(self, path: Path | None = None) -> str:
        target = path
        if target is None:
            existing = self._store.existing()
            target = existing[0] if existing else None
        if target is None:
            return ""
        try:
            version = int(target.stat().st_mtime)
        except OSError:
            version = 0
        return f"/api/branding/logo?v={version}"

    def upload_logo(self, content: bytes, *, content_type: str = "") -> dict[str, str | bool]:
        ext = LogoStore.extension_for_content_type(content_type)
        if not ext and content.startswith(b"\x89PNG"):
            ext = "png"
        elif not ext and content[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif not ext and (
            content.startswith(b"<svg") or content.lstrip().startswith(b"<?xml")
        ):
            ext = "svg"
        if not ext:
            raise ValueError("Unsupported image type — use PNG, JPG, WebP, or SVG")

        logo_ext = self._store.save(content, extension=ext)
        config = self._manager.load_config()
        config.branding.logo_ext = logo_ext
        if not config.branding.setup_completed and config.branding.company_name.strip():
            config.branding.setup_completed = True
        self._manager.save_config(config)
        return self.snapshot(config)

    def remove_logo(self) -> dict[str, str | bool]:
        self._store.clear()
        config = self._manager.load_config()
        config.branding.logo_ext = ""
        self._manager.save_config(config)
        return self.snapshot(config)

    def update_profile(self, branding: BrandingConfig) -> dict[str, str | bool]:
        config = self._manager.load_config()
        config.branding.company_name = branding.company_name.strip()
        config.branding.tagline = branding.tagline.strip() or "Agent console"
        config.branding.setup_completed = branding.setup_completed
        self._manager.save_config(config)
        return self.snapshot(config)
