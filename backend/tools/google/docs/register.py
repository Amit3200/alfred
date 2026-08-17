"""Google Docs tool handlers."""

from __future__ import annotations

from typing import Any

from backend.integrations.google import docs as google_docs
from backend.integrations.google.credentials import google_libs_available
from backend.tools.google.docs.schemas import GOOGLE_APPEND_DOC, GOOGLE_CREATE_DOC, GOOGLE_READ_DOC
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def _lib_error() -> ToolResult:
    return ToolResult.error(
        "Google libraries not installed. Run: pip install 'alfred-agent[google]'"
    )


def register_doc_tools(
    registry: ToolRegistry,
    *,
    credentials_json: str,
    refresh_token: str,
) -> None:
    def read_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        document_id = str(args.get("document_id") or "").strip()
        if not document_id:
            return ToolResult.error("document_id is required.")
        try:
            data = google_docs.read_doc(
                document_id=document_id,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_doc", data={"action": "read", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def create_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        title = str(args.get("title") or "").strip()
        if not title:
            return ToolResult.error("title is required.")
        try:
            data = google_docs.create_doc(
                title=title,
                body_text=str(args.get("body_text") or ""),
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_doc", data={"action": "create", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def append_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        document_id = str(args.get("document_id") or "").strip()
        text = str(args.get("text") or "")
        if not document_id or not text:
            return ToolResult.error("document_id and text are required.")
        try:
            data = google_docs.append_doc(
                document_id=document_id,
                text=text,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_doc", data={"action": "append", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    registry.register(GOOGLE_READ_DOC, read_handler)
    registry.register(GOOGLE_CREATE_DOC, create_handler)
    registry.register(GOOGLE_APPEND_DOC, append_handler)
