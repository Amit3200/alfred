"""Tool validation and execution errors."""

from __future__ import annotations


class ToolError(Exception):
    """Base class for tool-layer errors."""


class ToolValidationError(ToolError):
    """Raised when tool arguments fail validation before execution."""


class ToolExecutionError(ToolError):
    """Raised when a tool integration call fails unexpectedly."""
