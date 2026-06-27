"""Public and admin branding API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.api.deps import get_manager, require_admin
from backend.branding.service import BrandingService
from backend.branding.store import LogoStore
from backend.config_manager import ConfigManager
from backend.models.config import BrandingConfig

public_router = APIRouter(tags=["branding"])
admin_router = APIRouter(prefix="/config/branding", tags=["branding"])


class BrandingProfileBody(BaseModel):
    company_name: str = ""
    tagline: str = "Agent console"
    setup_completed: bool = False


@public_router.get("/branding")
def get_public_branding(manager: ConfigManager = Depends(get_manager)) -> dict:
    """Public branding snapshot for login page and unauthenticated views."""
    if not manager.is_initialized():
        return {
            "company_name": "",
            "tagline": "Agent console",
            "display_title": "Alfred",
            "setup_completed": False,
            "has_logo": False,
            "logo_url": "",
        }
    return BrandingService(manager).snapshot()


@public_router.get("/branding/logo")
def get_logo(manager: ConfigManager = Depends(get_manager)) -> FileResponse:
    service = BrandingService(manager)
    path = service.logo_path()
    if path is None:
        raise HTTPException(status_code=404, detail="Logo not configured")
    ext = path.suffix.lstrip(".")
    return FileResponse(
        path,
        media_type=LogoStore.media_type_for_extension(ext),
        filename=f"logo{path.suffix}",
    )


@admin_router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    content = await file.read()
    service = BrandingService(manager)
    try:
        return service.upload_logo(content, content_type=file.content_type or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.delete("/logo")
def delete_logo(manager: ConfigManager = Depends(require_admin)) -> dict:
    return BrandingService(manager).remove_logo()


@admin_router.put("")
def update_branding_profile(
    body: BrandingProfileBody,
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    service = BrandingService(manager)
    branding = BrandingConfig(
        company_name=body.company_name.strip(),
        tagline=body.tagline.strip() or "Agent console",
        setup_completed=body.setup_completed,
        logo_ext=manager.load_config().branding.logo_ext,
    )
    snapshot = service.update_profile(branding)
    return {"branding": snapshot}
