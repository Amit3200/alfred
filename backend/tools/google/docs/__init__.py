"""Google Docs tools."""

from backend.tools.google.docs.register import register_doc_tools
from backend.tools.google.docs.schemas import DOC_TOOL_NAMES

__all__ = ["register_doc_tools", "DOC_TOOL_NAMES"]
