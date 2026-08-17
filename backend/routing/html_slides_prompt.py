"""Prompt addendum for html_slides skill on Slack."""

from __future__ import annotations

from backend.models.task import Task
from backend.routing.html_slides_delivery import html_slides_system_addendum


def slack_html_slides_addendum(task: Task) -> str:
    return html_slides_system_addendum(task)
