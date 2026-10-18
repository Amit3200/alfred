"""Actor identity for user-scoped artifact management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArtifactActor:
    """Stable key for ACL plus human-readable label for audit."""

    key: str
    label: str


def normalize_actor_key(raw: str) -> str:
    return raw.strip().lower()


def admin_actor(username: str) -> ArtifactActor:
    name = username.strip() or "admin"
    return ArtifactActor(key=f"admin:{normalize_actor_key(name)}", label=name)


def slack_actor(user_id: str, display_name: str = "") -> ArtifactActor:
    uid = user_id.strip()
    label = (display_name or uid).strip() or uid
    return ArtifactActor(key=f"slack:{uid}", label=label)


SHARED_ADMIN_OWNER_KEY = "admin:shared"


def scheduler_actor() -> ArtifactActor:
    """Company scheduled decks — visible to every admin login."""
    return ArtifactActor(key=SHARED_ADMIN_OWNER_KEY, label="Alfred scheduler")


def resolve_publish_actor(
    *,
    task: Any | None,
    uploaded_by: str = "",
    owner_key: str = "",
) -> tuple[ArtifactActor, str, str]:
    """Return (actor, source, slack_user_id) for artifact publish tracking."""
    if owner_key.strip() and uploaded_by.strip():
        key = owner_key.strip()
        source = "slack" if key.startswith("slack:") else "admin" if key.startswith("admin:") else "api"
        slack_uid = key.removeprefix("slack:") if key.startswith("slack:") else ""
        return ArtifactActor(key=key, label=uploaded_by.strip()), source, slack_uid

    if task is not None and getattr(task, "source", "") == "slack":
        user_id = str(getattr(task, "user_id", "") or "").strip()
        if user_id:
            names = (getattr(task, "metadata", None) or {}).get("slack_user_names") or {}
            label = str(names.get(user_id) or user_id)
            actor = slack_actor(user_id, label)
            return actor, "slack", user_id

    if task is not None and getattr(task, "source", "") == "scheduler":
        actor = scheduler_actor()
        return actor, "scheduler", ""

    if task is not None and getattr(task, "source", "") == "ui":
        name = uploaded_by.strip() or "admin"
        return admin_actor(name), "admin", ""

    name = uploaded_by.strip() or "admin"
    return admin_actor(name), "api", ""
