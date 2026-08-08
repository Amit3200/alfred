"""LLM-assisted routing for Slack List board ops when regex direct handlers miss."""

from __future__ import annotations

from backend.routing.slack_board_agent import seed_slack_board_agent_plan

__all__ = ["seed_slack_board_agent_plan"]
