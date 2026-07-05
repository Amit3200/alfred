"""Ollama local setup API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.api.deps import get_manager
from backend.integrations.ollama import service as ollama

router = APIRouter(prefix="/ollama", tags=["ollama"])


class PullRequest(BaseModel):
    model: str | None = None


@router.get("/status")
def ollama_status(request: Request) -> dict:
    manager = get_manager(request)
    config, _ = manager.load_merged()
    provider = config.ai.providers.get("ollama")
    base_url = provider.base_url if provider else None
    model = provider.model if provider else None
    return ollama.get_status(base_url=base_url, model=model)


@router.post("/install")
def ollama_install() -> dict:
    return ollama.install_ollama()


@router.post("/start")
def ollama_start() -> dict:
    return ollama.start_ollama()


@router.post("/pull")
def ollama_pull(body: PullRequest) -> dict:
    return ollama.pull_model(body.model)


@router.post("/setup")
def ollama_setup(body: PullRequest) -> dict:
    return ollama.setup_local(body.model)
