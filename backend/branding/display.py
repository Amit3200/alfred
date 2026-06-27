"""Format branded titles for UI and prompts."""

from __future__ import annotations

from backend.models.config import AlfredConfig, BrandingConfig


def branding_display_title(branding: BrandingConfig) -> str:
    """Primary product title, e.g. ``Alfred × Acme Corp``."""
    company = (branding.company_name or "").strip()
    if not company:
        return "Alfred"
    return f"Alfred × {company}"


def branding_tagline(branding: BrandingConfig) -> str:
    tagline = (branding.tagline or "").strip()
    return tagline or "Agent console"


def branding_identity_line(branding: BrandingConfig) -> str:
    """One-line identity for system prompts."""
    company = (branding.company_name or "").strip()
    if not company:
        return "You are Alfred — the company's AI assistant."
    return f"You are Alfred — the AI assistant for {company} (branded as Alfred × {company})."


def public_branding_snapshot(
    config: AlfredConfig,
    *,
    logo_url: str | None = None,
    has_logo: bool = False,
) -> dict[str, str | bool]:
    branding = config.branding
    return {
        "company_name": branding.company_name,
        "tagline": branding_tagline(branding),
        "display_title": branding_display_title(branding),
        "setup_completed": branding.setup_completed,
        "has_logo": has_logo,
        "logo_url": logo_url or "",
    }
