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


class ArtifactsConfig(BaseModel):
    """HTML presentation artifact hosting."""

    public_base_url: str = Field(
        default="",
        description=(
            "Public base URL for share links in Slack (e.g. https://alfred.company.com). "
            "When empty, replies use relative paths like /artifacts/s/{slug}."
        ),
    )


class SlackListJiraSyncConfig(BaseModel):
    """Auto-create JIRA bugs when Slack List workflow posts eligible tickets."""

    enabled: bool = Field(
        default=False,
        description="Listen for Slack List workflow messages and create JIRA issues automatically.",
    )
    list_id: str = Field(
        default="",
        description="Slack List ID (e.g. F0A5AS3HF9S). Empty = any list record in allowed channels.",
    )
    jira_project: str = Field(
        default="TS",
        description="JIRA project key for auto-created issues (API key, not board name).",
    )
    issue_type: str = Field(default="Bug", description="JIRA issue type name.")
    eligible_statuses: list[str] = Field(
        default_factory=lambda: ["Not picked"],
        description="Create JIRA only when Slack List Status matches one of these labels.",
    )
    channel_ids: list[str] = Field(
        default_factory=list,
        description="Slack channel IDs to watch. Empty = use slack.allowed_channels.",
    )
    announce_in_thread: bool = Field(
        default=True,
        description="Post JIRA link in the Slack thread after creation.",
    )
    auto_approve_jira_create: bool = Field(
        default=True,
        description=(
            "When enabled with list_jira_sync, skip yes/proceed for jira_create_issue "
            "in watched Slack channels (agent @alfred path)."
        ),
    )


class SlackBoardColumnMap(BaseModel):
    title: str = Field(default="Name", description="List column for issue title.")
    status: str = Field(default="Status", description="Kanban status column label.")
    severity: str = Field(default="Severity", description="Priority/severity select column.")
    assignee: str = Field(default="Assignee", description="User assignee column.")
    merchant: str = Field(default="Merchant Name", description="Merchant name column.")
    merchant_domain: str = Field(default="Merchant Domain", description="Merchant domain column.")
    details: str = Field(default="Ticket Details", description="Long text / details column.")
    display_id: str = Field(
        default="",
        description="Optional column for Alfred display ids (TS-123). Leave empty to skip.",
    )


class SlackBoardProfile(BaseModel):
    name: str = Field(default="bugs-tracker", description="Registry key for this board.")
    list_id: str = Field(default="", description="Slack List id (F… from list URL).")
    channel_ids: list[str] = Field(
        default_factory=list,
        description="Slack channel ids bound to this board. Empty = any allowed channel.",
    )
    display_id_prefix: str = Field(default="TS", description="Prefix for generated ticket ids.")
    default_status: str = Field(default="Not picked", description="Status for new tasks.")
    auto_approve_writes: bool = Field(
        default=False,
        description="Skip yes/proceed for Slack List writes and jira_create_issue in bound channels.",
    )
    columns: SlackBoardColumnMap = Field(default_factory=SlackBoardColumnMap)


class SlackBoardWorkflowsConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="Enable Slack List board management via @alfred.",
    )
    boards: list[SlackBoardProfile] = Field(default_factory=list)


class SlackConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    signing_secret: str = ""
    app_token: str = ""
    allowed_channels: list[str] = Field(default_factory=lambda: ["*"])
    list_jira_sync: SlackListJiraSyncConfig = Field(default_factory=SlackListJiraSyncConfig)
    board_workflows: SlackBoardWorkflowsConfig = Field(default_factory=SlackBoardWorkflowsConfig)
    ticket_create_disambiguation: bool = Field(
        default=True,
        description=(
            "When JIRA and a Slack List board are both available in a channel, "
            "ask the user to choose (Slack buttons) before creating a generic ticket/task."
        ),
    )
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
    thread_relevance_enabled: bool = Field(
        default=True,
        description="Rank long Slack threads and keep the most relevant messages for context.",
    )
    thread_relevance_top_n: int = Field(
        default=15,
        ge=5,
        le=50,
        description="Maximum thread messages to keep after relevancy ranking.",
    )
    thread_fetch_limit: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Maximum thread replies to fetch before ranking.",
    )
    user_cache_refresh_hours: float = Field(
        default=1.0,
        ge=0.25,
        le=168.0,
        description="Hours between automatic Slack users.list cache refreshes. Use Integrations → Sync for urgent refresh.",
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


class GitRepoProfile(BaseModel):
    """Per-repository role and knowledge-base flags (mirrors, doc index, Graphify)."""

    repo: str = Field(
        default="",
        description="Repository slug, e.g. Acme/docs or docs (expanded with default_org).",
    )
    role: Literal["code", "docs", "scripts"] = Field(
        default="code",
        description="docs = support knowledge base; scripts = scheduled metrics/automation repo.",
    )
    doc_index: bool | None = Field(
        default=None,
        description="Build BM25 doc index on sync. Default: true for role=docs, false otherwise.",
    )
    graphify: bool | None = Field(
        default=None,
        description="Build Graphify graph on sync. Default: true for role=docs when graphify_enabled.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional labels for knowledge UI and routing (e.g. handbook, playbook, runbook).",
    )
    docs_public_base_url: str = Field(
        default="",
        description=(
            "Public docs site for this repo, e.g. https://docs.example.com. "
            "Indexed paths are mapped by stripping .md/.mdx (platforms/hydrogen.mdx → /platforms/hydrogen)."
        ),
    )


class GitConfig(BaseModel):
    enabled: bool = False
    provider: Literal["github", "gitlab"] = "github"
    token: str = ""
    default_org: str = ""
    repos: list[str] = Field(default_factory=list)
    repo_profiles: list[GitRepoProfile] = Field(
        default_factory=list,
        description=(
            "Optional per-repo roles and knowledge flags. Repos listed here are auto-included in mirrors."
        ),
    )
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
    # Phase 1 write flow (opt-in) — session-scoped branches + PR creation
    write_enabled: bool = Field(
        default=False,
        description="Enable git write tools (branch, commit, push, create PR) in isolated workspaces.",
    )
    default_base_branch: str = Field(
        default="",
        description="Base branch for write flow (e.g. dev or main). Empty uses origin/HEAD from the mirror.",
    )
    protected_branches: list[str] = Field(
        default_factory=lambda: ["main", "master", "production", "prod"],
        description="Branches that must never be committed to or pushed.",
    )
    write_allowed_prefixes: list[str] = Field(
        default_factory=list,
        description=(
            "If set, only these repo-relative path prefixes may be written (Phase 1). "
            "Empty allows any path not blocked."
        ),
    )
    write_blocked_prefixes: list[str] = Field(
        default_factory=lambda: [
            ".github/",
            ".gitlab/",
            "infra/",
            "terraform/",
            "Dockerfile",
            "docker-compose",
            ".env",
            "secrets/",
            "pyproject.toml",
            "package.json",
            "package-lock.json",
            "requirements.txt",
        ],
        description="Repo paths Alfred must not modify in Phase 1.",
    )
    debug_script_prefix: str = Field(
        default="scripts/alfred_debug/",
        description="Directory for read-only debug scripts Alfred may create and run.",
    )
    write_max_file_bytes: int = Field(
        default=256_000,
        ge=1024,
        le=2_000_000,
        description="Max bytes per write_file / debug script content.",
    )
    script_timeout_seconds: int = Field(
        default=120,
        ge=5,
        le=600,
        description="Timeout for run_debug_script.",
    )


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


class WebSearchConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="Enable web_search tool for external docs, errors, and release notes.",
    )
    provider: Literal["duckduckgo", "tavily"] = Field(
        default="duckduckgo",
        description="Search provider — DuckDuckGo needs no API key; Tavily uses web_search_api_key in Secrets.",
    )
    max_results: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Default max results per search.",
    )
    api_key: str = Field(default="", description="Provider API key (Tavily) — stored encrypted.")


class ScriptsRemoteConfig(BaseModel):
    """Pull curated script packages from a Git repo (e.g. Acme/scripts)."""

    repo: str = Field(
        default="",
        description="GitHub/GitLab slug, e.g. Acme/scripts. Requires git.token in Secrets.",
    )
    branch: str = Field(default="main", description="Branch to clone/pull.")
    path: str = Field(
        default="scripts",
        description="Directory inside the repo containing script packages (each with script.yaml).",
    )
    playbooks_path: str = Field(
        default="",
        description="Optional: sync playbooks/*.md from this repo subpath into .alfred/playbooks/.",
    )
    overwrite_local_playbooks: bool = Field(
        default=False,
        description="When syncing playbooks, overwrite existing local playbook files.",
    )
    requirements_file: str = Field(
        default="",
        description="Optional requirements path (relative to scripts path or repo root). Default: requirements.txt",
    )
    python_mode: Literal["isolated", "alfred"] = Field(
        default="isolated",
        description=(
            "isolated = install requirements.txt into .alfred/scripts-venv; "
            "alfred = run scripts with Alfred's Python (only use deps already in Alfred)."
        ),
    )
    install_timeout_seconds: int = Field(default=300, ge=30, le=900)
    sync_on_startup: bool = Field(default=True, description="Pull scripts repo when Alfred starts.")
    sync_on_git_sync: bool = Field(
        default=True,
        description="Also pull when running `alfred git sync` or POST /api/git/mirrors/sync.",
    )


class ScriptsConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Enable run_company_script tools for company script packages.",
    )
    timeout_seconds: int = Field(
        default=120,
        ge=5,
        le=1800,
        description="Max seconds for company script execution (Athena jobs may need 10–30 min).",
    )
    remote: ScriptsRemoteConfig = Field(default_factory=ScriptsRemoteConfig)


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
            "e.g. 'Alice Smith': 'alice@example.com'."
        ),
    )
    channel_projects: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Slack channel ID → JIRA project key for create/search in that channel, "
            "e.g. C0123ABC: TS for #tech-support."
        ),
    )
    project_aliases: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Board/display name or phrase → JIRA project key, "
            "e.g. 'tech-support': TS, 'TECH-SUPPORT': TS, 'engineering': TECH."
        ),
    )
    project_issue_types: dict[str, str] = Field(
        default_factory=dict,
        description="Optional project key → default issue type for creates, e.g. TS: Task.",
    )


class PeriskopeConfig(BaseModel):
    """WhatsApp inbox via Periskope — feeds Slack Lists / JIRA through the connector platform."""

    enabled: bool = False
    base_url: str = Field(
        default="https://api.periskope.app/v1",
        description="Periskope API base URL.",
    )
    org_phone: str = Field(
        default="",
        description="Connected WhatsApp number for the x-phone header, e.g. 919876543210.",
    )
    allowed_chat_ids: list[str] = Field(
        default_factory=list,
        description="If set, only these WhatsApp chat_ids (@g.us / @c.us) are pulled or replicated.",
    )
    slack_channel_id: str = Field(
        default="",
        description=(
            "Slack channel where Periskope tickets and tasks land. "
            "Alfred uses the Slack List bound to this channel."
        ),
    )
    summary_channel_id: str = Field(
        default="",
        description="Optional Slack channel for daily group summaries. Empty uses slack_channel_id.",
    )
    summary_timezone: str = Field(default="Asia/Kolkata")
    replicate_tickets: bool = True
    replicate_tasks: bool = True
    ticket_create_target: Literal["slack_board", "jira", "both"] = Field(
        default="slack_board",
        description="Where new Periskope tickets/tasks are created in Alfred.",
    )
    slack_board_key: str = Field(
        default="",
        description="Optional Slack List board key. Empty uses the board bound to slack_channel_id.",
    )
    jira_project: str = Field(
        default="",
        description="JIRA project key when ticket_create_target includes jira.",
    )
    ticket_summary_prompt: str = Field(
        default="",
        description=(
            "Extra instructions for summarizing WhatsApp tickets onto Slack/JIRA. "
            "Empty uses Alfred's default problem + action-item prompt. "
            "Channel persona from Slack boards is always prepended."
        ),
    )
    sync_on_update: bool = True
    api_token: str = ""
    webhook_secret: str = ""


class ConnectorsConfig(BaseModel):
    """Inbound connectors that normalize into Slack Lists, JIRA, and summaries."""

    periskope: PeriskopeConfig = Field(default_factory=PeriskopeConfig)


class RepoKnowledgeConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Enable on-demand repo doc search (search_repo_docs) instead of wholesale context injection.",
    )
    doc_paths: list[str] = Field(
        default_factory=lambda: ["docs", "runbooks", "README.md"],
        description="Paths under the shared mirror to index (files or directories).",
    )
    index_on_sync: bool = Field(
        default=True,
        description="Rebuild doc BM25 index when main repo mirror syncs.",
    )
    inject_overview: bool = Field(
        default=False,
        description="When false, skip injecting full overview/layout into every prompt (use doc tools instead).",
    )
    max_search_results: int = Field(default=8, ge=1, le=20)
    max_read_chars: int = Field(default=12000, ge=1000, le=50000)


class RoutingConfig(BaseModel):
    planner_strategy: Literal["llm_first", "rules_first"] = Field(
        default="llm_first",
        description=(
            "llm_first: LLM tool planner decides intent/tools; rules only for entity-direct fast paths. "
            "rules_first: legacy phrase rules before LLM fallback."
        ),
    )
    tool_planner_enabled: bool = Field(
        default=True,
        description="Enable rule/LLM tool planning before agent execution.",
    )
    tool_planner_llm_fallback: bool = Field(
        default=True,
        description="Use LLM tool planner when rule-based plan confidence is low.",
    )
    tool_planner_min_confidence: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to accept a tool plan.",
    )
    langgraph_enabled: bool = Field(
        default=True,
        description="Route tool execution through LangGraph orchestration (plan → validate → execute → ground).",
    )
    langgraph_checkpoint: bool = Field(
        default=True,
        description="Persist LangGraph state to SQLite for pause/resume across confirmations.",
    )
    plan_first_routing: bool = Field(
        default=True,
        description="Resolve skill from tool plan + skill policy before keyword/BM25 router.",
    )
    skill_router_fallback: bool = Field(
        default=True,
        description="When plan-first misses, fall back to SkillRouter (keyword → BM25 → LLM).",
    )
    phrase_routing_enabled: bool = Field(
        default=False,
        description=(
            "When false, investigation routing skips keyword/heuristic/BM25 tiers "
            "(plan-first + plan templates + optional LLM fallback only)."
        ),
    )
    plan_template_min_confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to accept a matched plan template.",
    )
    classifier_enabled: bool = Field(
        default=True,
        description=(
            "Hierarchical prompt router (tool parent → capability). "
            "When the model is unavailable, deterministic rules are the fallback."
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
    agentic_routing: bool = Field(
        default=True,
        description=(
            "When true, use the skill_matching LLM route if keyword, heuristic, and BM25 "
            "do not match a skill."
        ),
    )
    bm25_routing: bool = Field(
        default=True,
        description="Use BM25 over skill name/description/triggers before LLM skill matching.",
    )
    bm25_min_score: float = Field(
        default=-1.0,
        ge=-10.0,
        description="Minimum BM25 score required to accept a skill match (scores can be negative on short queries).",
    )
    bm25_min_gap: float = Field(
        default=0.5,
        ge=0.0,
        description="Minimum score gap between top-1 and top-2 BM25 candidates.",
    )


class BrandingConfig(BaseModel):
    company_name: str = Field(
        default="",
        description="Company name shown as “Alfred × {company}” in the admin UI.",
    )
    tagline: str = Field(
        default="Agent console",
        description="Subtitle under the product title in the admin UI.",
    )
    logo_ext: str = Field(
        default="",
        description="Logo file extension when uploaded (png, jpg, webp, svg).",
    )
    slide_accent: str = Field(
        default="",
        description="Company slide accent (ink mode). Overrides default when set in branding config.",
    )
    slide_accent_paper: str = Field(
        default="",
        description="Company slide accent in paper/light mode. Overrides default when set.",
    )
    slide_accent_secondary: str = Field(
        default="",
        description="Optional secondary highlight for slides. Empty uses #a5b4fc.",
    )
    setup_completed: bool = Field(
        default=False,
        description="True after company branding has been configured in admin or init.",
    )


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
    slack_user_preload_hours: float = Field(
        default=1.0,
        ge=0.25,
        le=168.0,
        description="Hours before observability dashboards refresh Slack user names from the API.",
    )
    model_pricing: dict[str, ModelPricingConfig] = Field(
        default_factory=dict,
        description="Override token rates by model name (USD per 1M input/output tokens).",
    )
    provider_pricing: dict[str, ModelPricingConfig] = Field(
        default_factory=dict,
        description="Fallback token rates by provider when model is unknown.",
    )


class OrchestratorConfig(BaseModel):
    agent_runner: Literal["react", "hermes"] = "react"
    self_improvement: bool = True
    self_improvement_requires_review: bool = Field(
        default=True,
        description="Queue self-learned playbooks for admin approval instead of auto-writing.",
    )


class GovernanceConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Enable write policies, confirmation UX, and audit logging.",
    )
    require_confirmation: bool = Field(
        default=True,
        description="Require explicit user confirmation before publish/write tools (push, PR, JIRA, Google, schedules).",
    )
    require_confirmation_sources: list[str] = Field(
        default_factory=lambda: ["slack", "ui"],
        description="Task sources that require confirmation. CLI is excluded by default.",
    )
    confirmation_phrases: list[str] = Field(
        default_factory=list,
        description="Phrases that grant write approval in-thread. Empty uses built-in defaults (yes, proceed, etc.).",
    )
    approval_ttl_minutes: int = Field(
        default=30,
        ge=5,
        le=240,
        description="Minutes write approval remains valid after user confirms.",
    )
    audit_enabled: bool = Field(default=True, description="Persist audit log entries for write tools.")
    write_allowed_sources: list[str] = Field(
        default_factory=lambda: ["slack", "ui", "cli", "scheduler"],
        description="Sources allowed to invoke write tools.",
    )
    write_allowed_channels: list[str] = Field(
        default_factory=list,
        description="If set, only these Slack channel IDs may use write tools. Empty = use slack.allowed_channels.",
    )
    write_blocked_channels: list[str] = Field(
        default_factory=list,
        description="Slack channel IDs where write tools are always blocked.",
    )
    write_allowed_users: list[str] = Field(
        default_factory=list,
        description="If set, only these Slack user IDs may invoke write tools.",
    )
    auto_approve_tools: list[str] = Field(
        default_factory=list,
        description=(
            "Write tools that skip yes/proceed confirmation (still audited). "
            "Example: jira_create_issue for trusted Slack ticket flows."
        ),
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
    connectors: ConnectorsConfig = Field(default_factory=ConnectorsConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    scripts: ScriptsConfig = Field(default_factory=ScriptsConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    branding: BrandingConfig = Field(default_factory=BrandingConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    repo_knowledge: RepoKnowledgeConfig = Field(default_factory=RepoKnowledgeConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)


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
    web_search_api_key: str = ""
    connectors: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Per-connector secrets, e.g. {periskope: {api_token, webhook_secret}}.",
    )
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
