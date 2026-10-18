"""Google Docs FunctionTool wrappers."""

from __future__ import annotations

from typing import Any

from backend.integrations.google import docs as google_docs
from backend.integrations.google.credentials import google_libs_available
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.google.docs.schemas import GOOGLE_APPEND_DOC, GOOGLE_CREATE_DOC, GOOGLE_READ_DOC
from backend.tools.result import ToolResult


def _lib_error() -> ToolResult:
    return ToolResult.error(
        "Google libraries not installed. Run: pip install 'alfred-agent[google]'"
    )


def _creds(ctx: ToolContext) -> tuple[str, str]:
    return str(ctx.get("credentials_json") or ""), str(ctx.get("refresh_token") or "")


def google_read_doc(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not google_libs_available():
        return _lib_error()
    document_id = str(args.get("document_id") or "").strip()
    if not document_id:
        return ToolResult.error("document_id is required.")
    credentials_json, refresh_token = _creds(ctx)
    try:
        data = google_docs.read_doc(
            document_id=document_id,
            credentials_json=credentials_json,
            refresh_token=refresh_token,
        )
        return ToolResult(kind="google_doc", data={"action": "read", **data})
    except Exception as exc:
        return ToolResult.error(str(exc))


def google_create_doc(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not google_libs_available():
        return _lib_error()
    title = str(args.get("title") or "").strip()
    if not title:
        return ToolResult.error("title is required.")
    credentials_json, refresh_token = _creds(ctx)
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


def google_append_doc(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not google_libs_available():
        return _lib_error()
    document_id = str(args.get("document_id") or "").strip()
    text = str(args.get("text") or "")
    if not document_id or not text:
        return ToolResult.error("document_id and text are required.")
    credentials_json, refresh_token = _creds(ctx)
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


def doc_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="google_read_doc",
            capability="google.read.doc",
            operation="read",
            domain="google_doc",
            schema=GOOGLE_READ_DOC,
            run_fn=google_read_doc,
            consumes=("document_id",),
        ),
        FunctionTool(
            name="google_create_doc",
            capability="google.write.doc",
            operation="create",
            domain="google_doc",
            schema=GOOGLE_CREATE_DOC,
            run_fn=google_create_doc,
            produces=("document_id",),
        ),
        FunctionTool(
            name="google_append_doc",
            capability="google.write.doc",
            operation="append",
            domain="google_doc",
            schema=GOOGLE_APPEND_DOC,
            run_fn=google_append_doc,
            consumes=("document_id",),
        ),
    ]
