"""Google Docs tool schemas."""

from __future__ import annotations

from backend.ai.base import ToolSchema

GOOGLE_READ_DOC = ToolSchema(
    name="google_read_doc",
    description="Read plain text from an EXISTING Google Doc. Args: document_id (from URL).",
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "Document ID from the Google Docs URL."},
        },
        "required": ["document_id"],
    },
)

GOOGLE_CREATE_DOC = ToolSchema(
    name="google_create_doc",
    description="Create a NEW Google Doc. Args: title, optional body_text (plain text).",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body_text": {"type": "string", "description": "Optional initial plain text body."},
        },
        "required": ["title"],
    },
)

GOOGLE_APPEND_DOC = ToolSchema(
    name="google_append_doc",
    description="Append plain text to an EXISTING Google Doc. Args: document_id, text.",
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["document_id", "text"],
    },
)

DOC_TOOL_NAMES = frozenset(
    {
        "google_read_doc",
        "google_create_doc",
        "google_append_doc",
    }
)
