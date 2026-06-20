"""Ingress layer — normalize external events into Tasks."""

from backend.ingress.processor import TaskProcessor
from backend.ingress.sanitize import channel_allowed, sanitize_slack_mention

__all__ = ["TaskProcessor", "channel_allowed", "sanitize_slack_mention"]
