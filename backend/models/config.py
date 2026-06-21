"""Pydantic models for Alfred configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    admin_token: str | None = None


class SlackConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    signing_secret: str = ""
    app_token: str = ""
    allowed_channels: list[str] = Field(default_factory=lambda: ["*"])


class GitConfig(BaseModel):
    enabled: bool = False
    provider: Literal["github", "gitlab"] = "github"
    token: str = ""
    default_org: str = ""
    repos: list[str] = Field(default_factory=list)
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
        default_factory=lambda: ["cloudwatch", "ecs", "s3"]
    )


class AIProviderConfig(BaseModel):
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class AIRoutingConfig(BaseModel):
    skill_matching: str = "ollama"
    investigation: str = "anthropic"
    workflow_execution: str = "anthropic"


class AIConfig(BaseModel):
    default_provider: str = "ollama"
    routing: AIRoutingConfig = Field(default_factory=AIRoutingConfig)
    providers: dict[str, AIProviderConfig] = Field(default_factory=dict)


class SkillsConfig(BaseModel):
    directory: str = "skills"
    custom_directory: str = "skills/custom"
    disabled: list[str] = Field(default_factory=list)


class AlfredConfig(BaseModel):
    """Non-secret configuration persisted to config.yaml."""

    initialized: bool = False
    server: ServerConfig = Field(default_factory=ServerConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)


class AlfredSecrets(BaseModel):
    """Sensitive values stored encrypted in secrets.enc."""

    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""
    git_token: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    ai_api_keys: dict[str, str] = Field(default_factory=dict)
    server_admin_token: str = ""


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
