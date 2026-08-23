"""Generic inbound connector platform — webhooks in, Slack/JIRA out."""

from backend.integrations.platform.registry import get_connector, list_connector_ids
from backend.integrations.platform.webhook import process_connector_webhook

__all__ = ["get_connector", "list_connector_ids", "process_connector_webhook"]
