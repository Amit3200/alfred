"""Logo file storage under ``.alfred/branding/``."""

from __future__ import annotations

from pathlib import Path

from backend.paths import branding_dir

MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


class LogoStore:
    """Read/write company logo files for a deployment."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._root = branding_dir(data_dir)

    @property
    def root(self) -> Path:
        return self._root

    def existing(self) -> tuple[Path, str] | None:
        """Return ``(path, extension_without_dot)`` when a logo file exists."""
        for ext in ALLOWED_EXTENSIONS:
            path = self._root / f"logo{ext}"
            if path.is_file() and path.stat().st_size > 0:
                return path, ext.lstrip(".")
        return None

    def save(self, content: bytes, *, extension: str) -> str:
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported logo type {ext!r}")
        if len(content) > MAX_LOGO_BYTES:
            raise ValueError("Logo must be 2 MB or smaller")
        if not content:
            raise ValueError("Logo file is empty")

        self._root.mkdir(parents=True, exist_ok=True)
        self.clear()
        dest = self._root / f"logo{ext}"
        dest.write_bytes(content)
        return ext.lstrip(".")

    def clear(self) -> None:
        if not self._root.is_dir():
            return
        for ext in ALLOWED_EXTENSIONS:
            path = self._root / f"logo{ext}"
            if path.is_file():
                path.unlink()

    @staticmethod
    def extension_for_content_type(content_type: str) -> str | None:
        normalized = (content_type or "").split(";", 1)[0].strip().lower()
        for ext, mime in CONTENT_TYPES.items():
            if mime == normalized:
                return ext.lstrip(".")
        return None

    @staticmethod
    def media_type_for_extension(ext: str) -> str:
        dotted = ext if ext.startswith(".") else f".{ext}"
        return CONTENT_TYPES.get(dotted.lower(), "application/octet-stream")
