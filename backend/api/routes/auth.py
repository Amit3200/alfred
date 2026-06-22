"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_manager
from backend.config_manager import ConfigManager

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, manager: ConfigManager = Depends(get_manager)) -> dict:
    config, secrets = manager.load_merged()
    
    expected_user = (secrets.server_admin_username or config.server.admin_username or "admin").strip()
    expected_pass = (secrets.server_admin_password or config.server.admin_password or "").strip()
    expected_token = (secrets.server_admin_token or config.server.admin_token or "").strip()
    
    if body.username.strip() == expected_user and body.password.strip() == expected_pass:
        return {"token": expected_token}
        
    raise HTTPException(status_code=401, detail="Invalid username or password")
