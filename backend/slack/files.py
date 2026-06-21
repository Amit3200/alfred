"""Upload file attachments to Slack threads."""

from __future__ import annotations

import logging
from typing import Any

from backend.ingress.file_exports import SlackFileAttachment

logger = logging.getLogger(__name__)


def upload_slack_files(
    client: Any,
    *,
    channel: str,
    thread_ts: str | None,
    files: list[SlackFileAttachment],
    initial_comment: str | None = None,
) -> None:
    if not files:
        return
    for index, attachment in enumerate(files):
        comment = initial_comment if index == 0 and initial_comment else None
        _upload_one(
            client,
            channel=channel,
            thread_ts=thread_ts,
            attachment=attachment,
            initial_comment=comment,
        )


def _upload_one(
    client: Any,
    *,
    channel: str,
    thread_ts: str | None,
    attachment: SlackFileAttachment,
    initial_comment: str | None,
) -> None:
    kwargs: dict[str, Any] = {
        "channel": channel,
        "filename": attachment.filename,
        "title": attachment.title or attachment.filename,
        "file": attachment.content,
    }
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    if initial_comment:
        kwargs["initial_comment"] = initial_comment

    try:
        if hasattr(client, "files_upload_v2"):
            response = client.files_upload_v2(**kwargs)
        else:
            response = client.files_upload(**kwargs)
    except Exception as exc:
        logger.warning("Slack file upload failed for %s: %s", attachment.filename, exc)
        raise RuntimeError(
            f"Could not upload `{attachment.filename}`. "
            "Add Bot scope `files:write`, reinstall the Slack app, and restart Alfred."
        ) from exc

    if not response.get("ok"):
        error = response.get("error", "unknown")
        logger.warning("Slack file upload error for %s: %s", attachment.filename, error)
        raise RuntimeError(
            f"Could not upload `{attachment.filename}` ({error}). "
            "Confirm the bot has `files:write` and is invited to this channel."
        )
