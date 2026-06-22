"""Pydantic models for Alfred configuration."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    admin_token: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None


class SlackConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    signing_secret: str = ""
    app_token: str = ""
    allowed_channels: list[str] = Field(default_factory=lambda: ["*"])
    loading_messages: list[str] = Field(
        default_factory=list,
        description=(
            "Optional workspace-specific thinking lines for Slack Assistant status. "
            "Use custom emoji shortcodes from your workspace, e.g. "
            "':this_is_fine: Everything is fine. Checking prod…'. "
            "Each line must be under 51 characters after emoji shortcodes are stripped. "
            "Mixed randomly with built-in defaults (up to 10 per request)."
        ),
    )


class GitHubAppConfig(BaseModel):
    """GitHub App ingress (webhooks + OAuth callback). Uses git.token for API calls."""

    enabled: bool = False
    client_id: str = ""
    app_id: str = ""
    bot_login: str = "alfred"
    allowed_repos: list[str] = Field(default_factory=list)
    callback_base_url: str = ""
    webhook_secret: str = ""
    client_secret: str = ""


class GitConfig(BaseModel):
    enabled: bool = False
    provider: Literal["github", "gitlab"] = "github"
    token: str = ""
    default_org: str = ""
    repos: list[str] = Field(default_factory=list)
    main_repo: str = Field(
        default="",
        description="Primary repository for default code context and investigation.",
    )
    graphify_enabled: bool = Field(
        default=False,
        description="Build Graphify knowledge graphs on sync and enable query_graph tool.",
    )
    graphify_extract_timeout_minutes: int = Field(
        default=120,
        ge=15,
        le=360,
        description="Max minutes to wait for graphify extract (large repos with doc/image files need more).",
    )
    # Repo mirror — per-conversation workspaces under .alfred/repos/workspaces/
    mirror_ttl_hours: int = 24
    mirror_refresh_minutes: int = 30
    mirror_max_workspaces: int = 32
    mirror_shallow_depth: int = 1


class AWSConfig(BaseModel):
    enabled: bool = False
    profile: str = "default"
    region: str = "us-east-1"
    access_key_id: str = ""
    secret_access_key: str = ""
    allowed_services: list[str] = Field(
        default_factory=lambda: ["cloudwatch", "athena", "ecs", "s3"]
    )
    athena_database: str = Field(
        default="",
        description="Default Glue/Athena database for athena_query.",
    )
    athena_workgroup: str = Field(
        default="primary",
        description="Athena workgroup name.",
    )
    athena_output_location: str = Field(
        default="",
        description="S3 prefix for Athena query results, e.g. s3://bucket/athena/.",
    )
    log_group_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map service short names to CloudWatch log groups, "
            "e.g. 'checkout-api': '/ecs/checkout-api'."
        ),
    )
    grade_events_database: str = Field(
        default="",
        description="Glue/Athena database for grade_events. Falls back to athena_database.",
    )
    grade_events_table: str = Field(
        default="grade_events",
        description="Athena table name for FlexyPe checkout event dumps.",
    )
    grade_events_s3_location: str = Field(
        default="",
        description="S3 location of grade_events data (documentation / validation).",
    )


class GoogleConfig(BaseModel):
    enabled: bool = False
    oauth_redirect_base_url: str = Field(
        default="",
        description=(
            "Public Alfred URL for Google OAuth callback, e.g. https://alfred.example.com. "
            "Add {base}/api/config/google/oauth/callback as an authorized redirect URI in GCP."
        ),
    )
    credentials_json: str = Field(
        default="",
        description="OAuth client or service account JSON — stored encrypted, not in config.yaml.",
    )
    oauth_refresh_token: str = Field(
        default="",
        description="OAuth refresh token after Connect Google — stored encrypted.",
    )


class JiraConfig(BaseModel):
    enabled: bool = False
    base_url: str = Field(
        default="",
        description="JIRA Cloud site URL, e.g. https://yourorg.atlassian.net",
    )
    email: str = Field(
        default="",
        description="Atlassian account email for API token auth.",
    )
    api_token: str = ""
    default_project: str = Field(
        default="",
        description="Default project key for searches, e.g. ENG.",
    )
    allowed_projects: list[str] = Field(
        default_factory=list,
        description="If set, only these project keys may be read or updated.",
    )
    assignee_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map Slack display names or user IDs to JIRA assignee emails/accountIds, "
            "e.g. 'Om Sinkar': 'om@flexype.io'."
        ),
    )


class AIProviderConfig(BaseModel):
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class LLMRouteConfig(BaseModel):
    provider: str = Field(
        default="",
        description="Provider name; empty uses default_provider or investigation fallback.",
    )
    model: str = Field(
        default="",
        description="Model override; empty uses the provider's default model from ai.providers.",
    )


def _coerce_llm_route(value: Any) -> Any:
    """Accept legacy ``provider: kimi`` strings or ``{provider, model}`` objects."""
    if value is None:
        return {"provider": "", "model": ""}
    if isinstance(value, str):
        return {"provider": value, "model": ""}
    if isinstance(value, LLMRouteConfig):
        return value
    if isinstance(value, dict):
        return value
    return {"provider": str(value), "model": ""}


CoercedLLMRoute = Annotated[LLMRouteConfig, BeforeValidator(_coerce_llm_route)]


class AIRoutingConfig(BaseModel):
    skill_matching: CoercedLLMRoute = Field(
        default_factory=lambda: LLMRouteConfig(provider="ollama")
    )
    investigation: CoercedLLMRoute = Field(
        default_factory=lambda: LLMRouteConfig(provider="anthropic")
    )
    workflow_execution: CoercedLLMRoute = Field(
        default_factory=lambda: LLMRouteConfig(provider="anthropic")
    )
    basic_chat: CoercedLLMRoute = Field(default_factory=LLMRouteConfig)
    pr_review: CoercedLLMRoute = Field(default_factory=LLMRouteConfig)


class AIConfig(BaseModel):
    default_provider: str = "ollama"
    routing: AIRoutingConfig = Field(default_factory=AIRoutingConfig)
    providers: dict[str, AIProviderConfig] = Field(default_factory=dict)


class SkillsConfig(BaseModel):
    directory: str = "skills"
    custom_directory: str = "skills/custom"
    disabled: list[str] = Field(default_factory=list)


class ModelPricingConfig(BaseModel):
    """USD per 1M tokens — used for approximate cost estimates in Usage."""

    input_per_million: float = Field(
        default=0.0,
        ge=0.0,
        description="USD per 1M input (prompt) tokens.",
    )
    output_per_million: float = Field(
        default=0.0,
        ge=0.0,
        description="USD per 1M output (completion) tokens.",
    )


class ObservabilityConfig(BaseModel):
    """Usage tracking and display — optional manual Slack user aliases."""

    user_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Map Slack user IDs (or internal keys) to display names, e.g. U0522NX5GG0: amit",
    )
    model_pricing: dict[str, ModelPricingConfig] = Field(
        default_factory=dict,
        description="Override token rates by model name (USD per 1M input/output tokens).",
    )
    provider_pricing: dict[str, ModelPricingConfig] = Field(
        default_factory=dict,
        description="Fallback token rates by provider when model is unknown.",
    )


class AlfredConfig(BaseModel):
    """Non-secret configuration persisted to config.yaml."""

    initialized: bool = False
    server: ServerConfig = Field(default_factory=ServerConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    github: GitHubAppConfig = Field(default_factory=GitHubAppConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    jira: JiraConfig = Field(default_factory=JiraConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


class AlfredSecrets(BaseModel):
    """Sensitive values stored encrypted in secrets.enc."""

    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""
    git_token: str = ""
    github_webhook_secret: str = ""
    github_client_secret: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    jira_api_token: str = ""
    google_credentials_json: str = ""
    google_oauth_refresh_token: str = ""
    ai_api_keys: dict[str, str] = Field(default_factory=dict)
    server_admin_token: str = ""
    server_admin_username: str = ""
    server_admin_password: str = ""


def default_ai_providers() -> dict[str, AIProviderConfig]:
    return {
        "ollama": AIProviderConfig(
            enabled=True,
            base_url="http://localhost:11434/v1",
            model="llama3",
        ),
        "openai": AIProviderConfig(
            enabled=False,
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        ),
        "anthropic": AIProviderConfig(
            enabled=False,
            model="claude-sonnet-4-20250514",
        ),
        "gemini": AIProviderConfig(
            enabled=False,
            model="gemini-2.0-flash",
        ),
        "kimi": AIProviderConfig(
            enabled=False,
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.6",
        ),
    }


def default_config() -> AlfredConfig:
    config = AlfredConfig()
    config.ai.providers = default_ai_providers()
    return config
