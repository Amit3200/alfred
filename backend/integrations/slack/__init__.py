"""Slack ingress package.

Import submodules directly (e.g. ``backend.integrations.slack.listener``) to avoid
import cycles through ``slack_lists`` ↔ ``listener`` ↔ ``list_jira_sync``.
"""

__all__: list[str] = []
