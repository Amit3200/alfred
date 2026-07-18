"""Connection health checks for configured integrations."""

from __future__ import annotations
from backend.integrations.slack.listener import slack_listener_ready
from backend.integrations.git.mirror import WorkspaceMirrorManager
from backend.paths import get_data_dir
from backend.integrations.aws.session import aws_call, aws_client
from backend.integrations.jira.api import JiraApiClient
from backend.integrations.google.credentials import (
            build_google_credentials,
            credentials_json_type,
            google_libs_available,
            refresh_if_needed,
        )
from backend.observability.context import (
        InteractionContext,
        bind_interaction_context,
        reset_interaction_context,
    )


from pathlib import Path

import requests

from backend.ai.registry import LLMRouter
from backend.models.config import AlfredConfig


def check_slack(config: AlfredConfig) -> dict:
    if not config.slack.enabled:
        return {"ok": False, "skipped": True, "message": "Slack disabled"}
    token = (config.slack.bot_token or "").strip()
    if not token:
        return {"ok": False, "message": "Slack bot token not configured"}
    if not token.startswith("xoxb-"):
        return {
            "ok": False,
            "message": "Bot token must start with xoxb-. Copy it from Slack → Your app → OAuth & Permissions → Bot User OAuth Token.",
        }
    try:
        resp = requests.get(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            error = data.get("error", "unknown")
            hints = {
                "invalid_auth": "Token rejected by Slack — generate a new Bot User OAuth Token (xoxb-) and re-save it in Secrets.",
                "token_revoked": "This token was revoked. Install/reinstall the app to your workspace and paste the new xoxb- token.",
            }
            return {
                "ok": False,
                "message": hints.get(error, error),
            }
        pass

        ingress_ready, ingress_message = slack_listener_ready(config)
        return {
            "ok": True,
            "message": f"Connected as {data.get('user')} in {data.get('team')}",
            "team": data.get("team"),
            "ingress_ready": ingress_ready,
            "ingress_message": ingress_message,
        }
    except requests.RequestException as exc:
        return {"ok": False, "message": str(exc)}


def check_git(config: AlfredConfig, *, data_dir: Path | None = None) -> dict:
    if not config.git.enabled:
        return {"ok": False, "skipped": True, "message": "Git disabled"}
    if not config.git.token:
        return {"ok": False, "message": "Git token not configured"}
    try:
        if config.git.provider == "github":
            url = "https://api.github.com/user"
            headers = {
                "Authorization": f"Bearer {config.git.token}",
                "Accept": "application/vnd.github+json",
            }
        else:
            url = "https://gitlab.com/api/v4/user"
            headers = {"PRIVATE-TOKEN": config.git.token}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"ok": False, "message": f"HTTP {resp.status_code}"}
        user = resp.json()
        login = user.get("login") or user.get("username") or user.get("name")
        message = f"Authenticated as {login}"
        mirror_info = check_git_mirrors(config, data_dir=data_dir)
        if mirror_info.get("mirror_message"):
            message = f"{message} · {mirror_info['mirror_message']}"
        result: dict = {"ok": True, "message": message}
        if mirror_info.get("mirrors"):
            result["mirrors"] = mirror_info["mirrors"]
        return result
    except requests.RequestException as exc:
        return {"ok": False, "message": str(exc)}


def check_git_mirrors(config: AlfredConfig, *, data_dir: Path | None = None) -> dict:
    """Local mirror storage summary for admin health."""
    if not config.git.enabled:
        return {}
    try:
        pass
        pass

        root = get_data_dir(data_dir)
        manager = WorkspaceMirrorManager(config.git, root)
        summary = manager.storage_summary()
        configured = len(config.git.repos) if config.git.repos else None
        synced = int(summary.get("shared_count") or 0)
        if configured is not None:
            mirror_message = f"Shared mirrors: {synced}/{configured} repos"
        else:
            mirror_message = f"Shared mirrors: {synced} cached"
        return {
            "mirrors": summary,
            "mirror_message": mirror_message,
        }
    except Exception as exc:
        return {"mirror_message": f"Mirror check failed: {exc}"}


def check_aws(config: AlfredConfig) -> dict:
    if not config.aws.enabled:
        return {"ok": False, "skipped": True, "message": "AWS disabled"}
    try:
        pass

        sts = aws_client(config, "sts", check_allowed=False)
        identity = aws_call(
            config,
            "sts",
            "GetCallerIdentity",
            lambda: sts.get_caller_identity(),
        )
        return {
            "ok": True,
            "message": f"Account {identity.get('Account')}",
            "arn": identity.get("Arn"),
        }
    except RuntimeError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def check_jira(config: AlfredConfig) -> dict:
    if not config.jira.enabled:
        return {"ok": False, "skipped": True, "message": "JIRA disabled"}
    if not config.jira.api_token:
        return {"ok": False, "message": "JIRA API token not configured"}
    if not config.jira.email:
        return {"ok": False, "message": "JIRA email not configured"}
    if not config.jira.base_url:
        return {"ok": False, "message": "JIRA base URL not configured"}
    try:
        pass

        client = JiraApiClient.from_alfred_config(config)
        user = client.ping()
        display = user.get("displayName") or user.get("emailAddress") or user.get("accountId")
        site = config.jira.base_url.rstrip("/")
        return {"ok": True, "message": f"Connected as {display} · {site}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def check_google(config: AlfredConfig) -> dict:
    if not config.google.enabled:
        return {"ok": False, "skipped": True, "message": "Google Workspace disabled"}
    raw = (config.google.credentials_json or "").strip()
    if not raw:
        return {"ok": False, "message": "Google credentials JSON not configured (Secrets)"}
    try:
        pass






        if not google_libs_available():
            return {
                "ok": False,
                "message": "Install Google libraries: pip install 'alfred-agent[google]'",
            }
        cred_type = credentials_json_type(raw)
        refresh = (config.google.oauth_refresh_token or "").strip()
        if cred_type == "oauth_client" and not refresh:
            return {
                "ok": False,
                "message": "OAuth client saved — click Connect Google in Integrations to authorize.",
            }
        creds = build_google_credentials(credentials_json=raw, refresh_token=refresh)
        refresh_if_needed(creds)
        if cred_type == "service_account":
            email = creds.service_account_email
            return {"ok": True, "message": f"Service account {email}"}
        return {"ok": True, "message": "OAuth connected for Sheets and Docs"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def check_web_search(config: AlfredConfig, *, live: bool = False) -> dict:
    if not config.web_search.enabled:
        return {"ok": False, "skipped": True, "message": "Web search disabled"}
    if config.web_search.provider == "tavily" and not (config.web_search.api_key or "").strip():
        return {"ok": False, "message": "Tavily API key not configured (Secrets)"}
    try:
        from backend.integrations.web.search import WebSearchClient

        client = WebSearchClient.from_config(config.web_search)
        meta = client.ping(live=live)
        provider = meta.get("provider") or config.web_search.provider
        if live:
            count = meta.get("result_count", 0)
            suffix = " (cached)" if meta.get("cached") else ""
            return {"ok": True, "message": f"{provider} live search OK ({count} sample result(s){suffix})"}
        message = str(meta.get("message") or f"{provider} ready")
        return {"ok": True, "message": message}
    except RuntimeError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def check_ai(config: AlfredConfig, provider: str | None = None, *, data_dir=None) -> dict:
    pass





    router = LLMRouter.from_config(config, data_dir=data_dir)
    name = provider or config.ai.default_provider
    token = bind_interaction_context(
        InteractionContext(source="ui", user_label="health-check", call_kind="health_check")
    )
    try:
        result = router.ping(name)
        message = result.get("message") or result.get("reply", "")
        return {"ok": result["ok"], "message": message, **result}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "provider": name}
    finally:
        reset_interaction_context(token)


def run_all_checks(config: AlfredConfig, *, data_dir: Path | None = None) -> dict:
    return {
        "slack": check_slack(config),
        "git": check_git(config, data_dir=data_dir),
        "aws": check_aws(config),
        "jira": check_jira(config),
        "google": check_google(config),
        "web_search": check_web_search(config),
        "ai": check_ai(config, data_dir=data_dir),
    }


INTEGRATION_HEALTH_CHECKS = frozenset(
    {"slack", "git", "aws", "jira", "google", "web_search"},
)


def run_integration_check(
    name: str,
    config: AlfredConfig,
    *,
    data_dir: Path | None = None,
) -> dict:
    """Run a single integration health check (Integrations → Test connection)."""
    if name == "slack":
        return check_slack(config)
    if name == "git":
        return check_git(config, data_dir=data_dir)
    if name == "aws":
        return check_aws(config)
    if name == "jira":
        return check_jira(config)
    if name == "google":
        return check_google(config)
    if name == "web_search":
        return check_web_search(config, live=True)
    raise ValueError(f"Unknown integration: {name}")
