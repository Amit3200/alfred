import type { HealthCheck } from "../health";

export type LLMRouteConfig = {
  provider: string;
  model: string;
};

export type AIProviderConfig = {
  enabled: boolean;
  api_key: string;
  base_url: string;
  model: string;
};

export type AlfredConfig = {
  initialized: boolean;
  server: { host: string; port: number; admin_token: string };
  slack: {
    enabled: boolean;
    bot_token: string;
    signing_secret: string;
    app_token: string;
    allowed_channels: string[];
    thread_relevance_enabled?: boolean;
    thread_relevance_top_n?: number;
    thread_fetch_limit?: number;
  };
  git: {
    enabled: boolean;
    provider: "github" | "gitlab";
    token: string;
    default_org: string;
    repos: string[];
    main_repo?: string;
    graphify_enabled?: boolean;
    mirror_ttl_hours?: number;
    mirror_refresh_minutes?: number;
    mirror_max_workspaces?: number;
    mirror_shallow_depth?: number;
    write_enabled?: boolean;
  };
  github: {
    enabled: boolean;
    client_id: string;
    app_id: string;
    bot_login: string;
    allowed_repos: string[];
    callback_base_url: string;
  };
  aws: {
    enabled: boolean;
    profile: string;
    region: string;
    access_key_id: string;
    secret_access_key: string;
    allowed_services: string[];
    athena_database: string;
    athena_workgroup: string;
    athena_output_location: string;
    log_group_map: Record<string, string>;
  };
  jira: {
    enabled: boolean;
    base_url: string;
    email: string;
    api_token: string;
    default_project: string;
    allowed_projects: string[];
  };
  google: {
    enabled: boolean;
    oauth_redirect_base_url: string;
  };
  web_search?: {
    enabled: boolean;
    provider: "duckduckgo" | "tavily";
    max_results: number;
  };
  ai: {
    default_provider: string;
    routing: {
      skill_matching: LLMRouteConfig;
      investigation: LLMRouteConfig;
      workflow_execution: LLMRouteConfig;
      basic_chat: LLMRouteConfig;
      pr_review: LLMRouteConfig;
    };
    providers: Record<string, AIProviderConfig>;
  };
  skills: {
    directory: string;
    custom_directory: string;
    disabled: string[];
    agentic_routing: boolean;
    bm25_routing?: boolean;
    bm25_min_score?: number;
    bm25_min_gap?: number;
  };
  branding: {
    company_name: string;
    tagline: string;
    logo_ext: string;
    setup_completed: boolean;
  };
  orchestrator: {
    agent_runner: "react" | "hermes";
    self_improvement: boolean;
    self_improvement_requires_review?: boolean;
  };
  governance?: {
    enabled: boolean;
    require_confirmation: boolean;
    require_confirmation_sources: string[];
    confirmation_phrases: string[];
    approval_ttl_minutes: number;
    audit_enabled: boolean;
    write_allowed_sources: string[];
    write_allowed_channels: string[];
    write_blocked_channels: string[];
    write_allowed_users: string[];
  };
  _secrets_configured?: {
    slack_bot_token: boolean;
    slack_bot_token_valid?: boolean;
    slack_bot_token_hint?: string | null;
    slack_signing_secret: boolean;
    slack_app_token: boolean;
    git_token: boolean;
    github_webhook_secret: boolean;
    github_client_secret: boolean;
    aws_access_key_id: boolean;
    aws_secret_access_key: boolean;
    jira_api_token: boolean;
    google_credentials_json: boolean;
    google_oauth_refresh_token: boolean;
    google_credentials_type?: string | null;
    google_oauth_connected?: boolean;
    web_search_api_key?: boolean;
    server_admin_token: boolean;
    ai_api_keys: Record<string, boolean>;
  };
};

export type PublicBranding = {
  company_name: string;
  tagline: string;
  display_title: string;
  setup_completed: boolean;
  has_logo: boolean;
  logo_url: string;
};

export type SecretsPayload = {
  slack_bot_token?: string;
  slack_signing_secret?: string;
  slack_app_token?: string;
  git_token?: string;
  github_webhook_secret?: string;
  github_client_secret?: string;
  aws_access_key_id?: string;
  aws_secret_access_key?: string;
  jira_api_token?: string;
  google_credentials_json?: string;
  google_oauth_refresh_token?: string;
  web_search_api_key?: string;
  server_admin_token?: string;
  ai_api_keys?: Record<string, string>;
};

export type GoogleOAuthStatus = {
  credentials_configured: boolean;
  credentials_type: string | null;
  oauth_connected: boolean;
  oauth_refresh_token_configured: boolean;
  google_libs_installed: boolean;
  redirect_uri: string | null;
};

export type OllamaStatus = {
  ok: boolean;
  installed: boolean;
  running: boolean;
  cli_path: string | null;
  api_url: string;
  models: string[];
  recommended_model: string;
  model_ready: boolean;
  local_only: boolean;
  isolated: boolean;
  platform: string;
  install_hint: string;
  message: string;
  error: string | null;
};

export type OllamaActionResult = {
  ok: boolean;
  message?: string;
  already_installed?: boolean;
  already_running?: boolean;
  model?: string;
  steps?: Array<{ step: string; ok: boolean; message?: string }>;
  status?: OllamaStatus;
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

const TOKEN_KEY = "alfred_admin_token";

export function getAdminToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setAdminToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth: boolean | string = false,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (auth) {
    const token = (typeof auth === "string" ? auth : getAdminToken()).trim();
    if (token) headers["X-Alfred-Token"] = token;
  }
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    if (res.status === 401) {
      throw new ApiError(
        detail === "Invalid admin token" || detail === "Unauthorized"
          ? "Invalid credentials or token"
          : detail || "Unauthorized",
        res.status
      );
    }
    throw new ApiError(detail || `Request failed: ${res.status}`, res.status);
  }
  return res.json();
}

function encodePlaybookPath(filename: string): string {
  return filename
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}

function encodeScriptPath(relativePath: string): string {
  return encodePlaybookPath(relativePath);
}

export const api = {
  login: (username: string, password_or_token: string) =>
    request<{ token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password: password_or_token }),
    }),
  health: () =>
    request<{ status: string; version: string; initialized: boolean; data_dir?: string }>(
      "/api/health",
      {},
      true,
    ),
  getPublicBranding: () => request<PublicBranding>("/api/branding"),
  updateBrandingProfile: (body: {
    company_name: string;
    tagline: string;
    setup_completed: boolean;
  }) =>
    request<{ branding: PublicBranding }>(
      "/api/config/branding",
      { method: "PUT", body: JSON.stringify(body) },
      true,
    ),
  uploadBrandingLogo: async (file: File): Promise<PublicBranding> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/config/branding/logo", {
      method: "POST",
      headers: { "X-Alfred-Token": getAdminToken() },
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(String(body.detail || "Logo upload failed"), res.status);
    }
    return res.json();
  },
  deleteBrandingLogo: () =>
    request<PublicBranding>("/api/config/branding/logo", { method: "DELETE" }, true),
  checks: () => request<Record<string, HealthCheck>>("/api/health/checks", {}, true),
  getConfig: () => request<AlfredConfig>("/api/config", {}, true),
  saveConfig: (config: AlfredConfig, token?: string) =>
    request<AlfredConfig>(
      "/api/config",
      { method: "PUT", body: JSON.stringify(config) },
      token || true,
    ),
  saveSecrets: (secrets: SecretsPayload, token?: string) =>
    request<AlfredConfig>(
      "/api/config/secrets",
      { method: "PUT", body: JSON.stringify(secrets) },
      token || true,
    ),
  exportConfig: async (): Promise<Blob> => {
    const res = await fetch("/api/config/export", {
      headers: { "X-Alfred-Token": getAdminToken() },
    });
    if (!res.ok) {
      throw new Error(`Export failed: ${res.status}`);
    }
    return res.blob();
  },
  importConfig: async (file: File): Promise<AlfredConfig & { imported_files?: string[] }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/config/import", {
      method: "POST",
      headers: { "X-Alfred-Token": getAdminToken() },
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Import failed: ${res.status}`);
    }
    return res.json();
  },
  testProvider: (name: string) =>
    request<{ ok: boolean; message?: string; reply?: string }>(
      `/api/config/providers/${name}/test`,
      { method: "POST" },
      true,
    ),
  testIntegration: (name: string) =>
    request<{ ok: boolean; message?: string; skipped?: boolean }>(
      `/api/config/integrations/${name}/test`,
      { method: "POST" },
      true,
    ),
  getGoogleOAuthStatus: () =>
    request<GoogleOAuthStatus>("/api/config/google/oauth/status", {}, true),
  startGoogleOAuth: () =>
    request<{ authorization_url: string; redirect_uri: string }>(
      "/api/config/google/oauth/start",
      { method: "POST" },
      true,
    ),
  ollamaStatus: () => request<OllamaStatus>("/api/ollama/status", {}, true),
  ollamaInstall: () => request<OllamaActionResult>("/api/ollama/install", { method: "POST" }, true),
  ollamaStart: () => request<OllamaActionResult>("/api/ollama/start", { method: "POST" }, true),
  ollamaPull: (model?: string) =>
    request<OllamaActionResult>("/api/ollama/pull", {
      method: "POST",
      body: JSON.stringify({ model: model || null }),
    }, true),
  ollamaSetup: (model?: string) =>
    request<OllamaActionResult>("/api/ollama/setup", {
      method: "POST",
      body: JSON.stringify({ model: model || null }),
    }, true),

  listChatSessions: () =>
    request<{ sessions: ChatSessionSummary[] }>("/api/chat/sessions", {}, true),
  createChatSession: (title?: string) =>
    request<ChatSessionSummary>(
      "/api/chat/sessions",
      { method: "POST", body: JSON.stringify({ title: title || "New chat" }) },
      true,
    ),
  getChatSession: (id: string) => request<ChatSessionDetail>(`/api/chat/sessions/${id}`, {}, true),
  deleteChatSession: (id: string) =>
    request<{ ok: boolean }>(`/api/chat/sessions/${id}`, { method: "DELETE" }, true),
  sendChatMessage: (id: string, content: string) =>
    request<ChatMessageResponse>(
      `/api/chat/sessions/${id}/messages`,
      { method: "POST", body: JSON.stringify({ content }) },
      true,
    ),
  exportChatSession: (id: string, filename?: string) =>
    request<ChatExportResult>(
      `/api/chat/sessions/${id}/export`,
      { method: "POST", body: JSON.stringify({ filename: filename || null }) },
      true,
    ),
  chatExportDownloadUrl: (filename: string) => `/api/chat/exports/${encodeURIComponent(filename)}`,

  getGitMirrors: () => request<GitMirrorsResponse>("/api/git/mirrors", {}, true),
  getAvailableGitRepos: () =>
    request<AvailableGitReposResponse>("/api/git/mirrors/repos/available", {}, true),
  cleanupGitMirrors: (scope: GitMirrorCleanupScope) =>
    request<GitMirrorCleanupResult>(
      "/api/git/mirrors/cleanup",
      { method: "POST", body: JSON.stringify({ scope }) },
      true,
    ),
  deleteGitWorkspace: (workspaceId: string) =>
    request<{ ok: boolean; removed: string }>(
      `/api/git/mirrors/workspaces/${encodeURIComponent(workspaceId)}`,
      { method: "DELETE" },
      true,
    ),
  deleteGitSharedMirror: (sharedId: string) =>
    request<{ ok: boolean; removed: string }>(
      `/api/git/mirrors/shared/${encodeURIComponent(sharedId)}`,
      { method: "DELETE" },
      true,
    ),
  syncGitSharedMirrors: (repos?: string[]) =>
    request<GitMirrorSyncResult>(
      "/api/git/mirrors/sync",
      { method: "POST", body: JSON.stringify({ repos: repos ?? [] }) },
      true,
    ),

  getRepoContext: () => request<RepoContextResponse>("/api/repo-context", {}, true),
  generateRepoContext: () =>
    request<RepoContextGenerateResult>(
      "/api/repo-context/generate",
      { method: "POST", body: JSON.stringify({}) },
      true,
    ),
  syncMainRepoContext: () =>
    request<RepoContextSyncMainResult>(
      "/api/repo-context/sync-main",
      { method: "POST", body: JSON.stringify({}) },
      true,
    ),
  generateContextSuggestions: () =>
    request<{ ok: boolean; suggestions: ContextSuggestion[] }>(
      "/api/repo-context/suggestions/generate",
      { method: "POST", body: JSON.stringify({}) },
      true,
    ),
  approveContextSuggestion: (id: string) =>
    request<{ ok: boolean; filename: string }>(
      `/api/repo-context/suggestions/${encodeURIComponent(id)}/approve`,
      { method: "POST", body: JSON.stringify({}) },
      true,
    ),
  dismissContextSuggestion: (id: string) =>
    request<{ ok: boolean }>(
      `/api/repo-context/suggestions/${encodeURIComponent(id)}/dismiss`,
      { method: "POST", body: JSON.stringify({}) },
      true,
    ),

  getGraphifyStatus: () =>
    request<GraphifyDetailResponse>("/api/repo-context/graphify", {}, true),
  getGraphifyReport: () =>
    request<GraphifyReportResponse>("/api/repo-context/graphify/report", {}, true),
  getGraphifySummary: () =>
    request<GraphifySummaryResponse>("/api/repo-context/graphify/summary", {}, true),
  rebuildGraphify: () =>
    request<GraphifyRebuildResult>(
      "/api/repo-context/graphify/rebuild",
      { method: "POST", body: JSON.stringify({}) },
      true,
    ),

  observabilitySummary: (params: ObservabilityQuery = {}) =>
    request<ObservabilitySummaryResponse>(
      `/api/observability/summary${buildObservabilityQuery(params)}`,
      {},
      true,
    ),
  observabilityTimeseries: (params: ObservabilityQuery = {}) =>
    request<ObservabilityTimeseriesResponse>(
      `/api/observability/timeseries${buildObservabilityQuery(params)}`,
      {},
      true,
    ),
  observabilityEvents: (params: ObservabilityQuery & { limit?: number; offset?: number } = {}) =>
    request<ObservabilityEventsResponse>(
      `/api/observability/events${buildObservabilityQuery(params)}`,
      {},
      true,
    ),
  governanceAudit: (params: { limit?: number; tool_name?: string; blocked_only?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set("limit", String(params.limit));
    if (params.tool_name) q.set("tool_name", params.tool_name);
    if (params.blocked_only) q.set("blocked_only", "true");
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return request<GovernanceAuditResponse>(
      `/api/observability/audit${suffix}`,
      {},
      true,
    );
  },
  observabilityFilters: (preset = "30d") =>
    request<ObservabilityFilterOptions>(
      `/api/observability/filters?preset=${encodeURIComponent(preset)}`,
      {},
      true,
    ),
  observabilityCheckpoints: (taskId?: string) =>
    request<{ checkpoints: Array<{ task_id: string; checkpoint: string; function_name: string; status: string; timestamp: number; error?: string | null; error_stacktrace?: string | null }> }>(
      `/api/observability/checkpoints${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ""}`,
      {},
      true,
    ),

  getDbStats: () => request<DbStatsResponse>("/api/storage/db", {}, true),
  cleanupDb: (body: DbCleanupRequest) =>
    request<DbCleanupResult>(
      "/api/storage/db/cleanup",
      { method: "POST", body: JSON.stringify(body) },
      true,
    ),

  listSchedules: () =>
    request<{ schedules: ScheduledJob[] }>("/api/observability/schedules", {}, true),
  toggleSchedule: (jobId: string, active: boolean) =>
    request<{ status: string }>(
      `/api/observability/schedules/${encodeURIComponent(jobId)}/toggle`,
      { method: "POST", body: JSON.stringify({ active }) },
      true,
    ),
  triggerSchedule: (jobId: string) =>
    request<{ status: string }>(
      `/api/observability/schedules/${encodeURIComponent(jobId)}/trigger`,
      { method: "POST" },
      true,
    ),
  deleteSchedule: (jobId: string) =>
    request<{ status: string }>(
      `/api/observability/schedules/${encodeURIComponent(jobId)}`,
      { method: "DELETE" },
      true,
    ),
  getSchedule: (jobId: string) =>
    request<ScheduledJob>(`/api/observability/schedules/${encodeURIComponent(jobId)}`, {}, true),
  updateSchedule: (
    jobId: string,
    body: { name?: string; cron_expression?: string; channel_id?: string | null; instructions?: string; timezone?: string },
  ) =>
    request<{ status: string }>(
      `/api/observability/schedules/${encodeURIComponent(jobId)}`,
      { method: "PUT", body: JSON.stringify(body) },
      true,
    ),
  getLogs: (search?: string) => {
    const query = search ? `?search=${encodeURIComponent(search)}` : "";
    return request<{ logs: LogEvent[] }>(`/api/observability/logs${query}`, {}, true);
  },

  listPlaybooks: () => request<PlaybooksListResponse>("/api/playbooks", {}, true),
  listPendingPlaybooks: () =>
    request<PendingPlaybooksResponse>("/api/playbooks/pending", {}, true),
  getPendingPlaybook: (pendingId: string) =>
    request<{ pending: PendingPlaybook }>(
      `/api/playbooks/pending/${encodeURIComponent(pendingId)}`,
      {},
      true,
    ),
  approvePendingPlaybook: (pendingId: string) =>
    request<{ ok: boolean; filename: string; pending: PendingPlaybook }>(
      `/api/playbooks/pending/${encodeURIComponent(pendingId)}/approve`,
      { method: "POST" },
      true,
    ),
  rejectPendingPlaybook: (pendingId: string) =>
    request<{ ok: boolean; pending: PendingPlaybook }>(
      `/api/playbooks/pending/${encodeURIComponent(pendingId)}/reject`,
      { method: "POST" },
      true,
    ),
  getPlaybookExample: () => request<PlaybookExampleResponse>("/api/playbooks/example", {}, true),
  getPlaybook: (filename: string) =>
    request<PlaybookDetail>(`/api/playbooks/${encodePlaybookPath(filename)}`, {}, true),
  createPlaybook: (filename: string, content?: string) =>
    request<PlaybookDetail>(
      "/api/playbooks",
      { method: "POST", body: JSON.stringify({ filename, content: content ?? "" }) },
      true,
    ),
  savePlaybook: (filename: string, content: string) =>
    request<PlaybookDetail>(
      `/api/playbooks/${encodePlaybookPath(filename)}`,
      { method: "PUT", body: JSON.stringify({ content }) },
      true,
    ),
  deletePlaybook: (filename: string) =>
    request<{ ok: boolean; removed: string }>(
      `/api/playbooks/${encodePlaybookPath(filename)}`,
      { method: "DELETE" },
      true,
    ),
  uploadPlaybook: async (file: File) => {
    const content = await file.text();
    if (!content.trim()) throw new Error("File is empty");
    const filename = file.name.toLowerCase().endsWith(".md") ? file.name : `${file.name}.md`;
    try {
      await api.getPlaybook(filename);
      return api.savePlaybook(filename, content);
    } catch {
      return api.createPlaybook(filename, content);
    }
  },

  listScripts: () => request<ScriptsListResponse>("/api/scripts", {}, true),
  getScriptExample: () => request<ScriptExampleResponse>("/api/scripts/example", {}, true),
  getScriptFile: (relativePath: string) =>
    request<ScriptFileDetail>(`/api/scripts/files/${encodeScriptPath(relativePath)}`, {}, true),
  createScriptPackage: (body: {
    package_path: string;
    runtime?: string;
    description?: string;
    entry?: string;
  }) =>
    request<{ ok: boolean; package: ScriptPackageSummary }>(
      "/api/scripts/packages",
      { method: "POST", body: JSON.stringify(body) },
      true,
    ),
  createScriptFile: (relativePath: string, content = "") =>
    request<{ ok: boolean; relative_path: string }>(
      `/api/scripts/files/${encodeScriptPath(relativePath)}`,
      { method: "POST", body: JSON.stringify({ relative_path: relativePath, content }) },
      true,
    ),
  saveScriptFile: (relativePath: string, content: string) =>
    request<{ ok: boolean; relative_path: string }>(
      `/api/scripts/files/${encodeScriptPath(relativePath)}`,
      { method: "PUT", body: JSON.stringify({ content }) },
      true,
    ),
  deleteScriptPath: (relativePath: string) =>
    request<{ ok: boolean; removed: string }>(
      `/api/scripts/files/${encodeScriptPath(relativePath)}`,
      { method: "DELETE" },
      true,
    ),
  deleteScriptPackage: (packageName: string) =>
    request<{ ok: boolean; removed: string }>(
      `/api/scripts/packages/${encodeScriptPath(packageName)}`,
      { method: "DELETE" },
      true,
    ),
};

export type ChatSessionSummary = {
  id: string;
  title: string;
  message_count: number;
  updated_at?: string;
  created_at?: string;
};

export type ResponsePayload = {
  kind:
    | "text"
    | "pr_list"
    | "pr_detail"
    | "repo_list"
    | "error"
    | "code_grep"
    | "file_content"
    | "git_log"
    | "git_blame"
    | "git_show"
    | "jira_list"
    | "jira_detail"
    | "jira_action"
    | "athena_query"
    | "cloudwatch_query"
    | "cloudwatch_log_groups"
    | "google_sheet"
    | "google_doc";
  data: Record<string, unknown>;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  payload?: ResponsePayload | null;
};

export type ChatSessionDetail = ChatSessionSummary & {
  messages: ChatMessage[];
};

export type ChatMessageResponse = {
  reply: string;
  payload?: ResponsePayload;
  chat: ChatSessionDetail;
  export?: { filename: string; path: string };
};

export type ChatExportResult = {
  filename: string;
  path: string;
  download_url: string;
};

export type GitMirrorCleanupScope = "expired" | "workspaces" | "shared" | "all";

export type AvailableGitReposResponse = {
  enabled: boolean;
  repos: string[];
  configured: string[];
  remote: string[];
  source: "disabled" | "configured" | "org" | "user";
  org?: string | null;
  error?: string | null;
};

export type GitMirrorSummary = {
  workspaces_count: number;
  shared_count: number;
  workspaces_bytes: number;
  shared_bytes: number;
  total_bytes: number;
  mirror_ttl_hours: number;
  mirror_max_workspaces: number;
  mirror_refresh_minutes: number;
  main_repo?: string;
  graphify_enabled?: boolean;
};

export type GitMirrorWorkspace = {
  id: string;
  session_key?: string;
  last_used_at?: string;
  repos: string[];
  repos_detail?: Array<{
    slug: string;
    ref?: string;
    head_sha?: string;
    last_pulled_at?: string;
  }>;
  size_bytes: number;
};

export type GitMirrorShared = {
  id: string;
  repo: string;
  size_bytes: number;
  head_sha?: string | null;
};

export type GitMirrorsResponse = {
  enabled: boolean;
  summary: GitMirrorSummary;
  workspaces: GitMirrorWorkspace[];
  shared: GitMirrorShared[];
};

export type GitMirrorCleanupResult = {
  ok: boolean;
  scope: GitMirrorCleanupScope;
  removed_workspaces: string[];
  removed_shared: string[];
  summary: GitMirrorSummary;
};

export type GitMirrorSyncResult = {
  ok: boolean;
  results: Array<{ repo: string; ok: boolean; action?: string; error?: string }>;
  context?: RepoContextBuildResult | null;
  shared: GitMirrorShared[];
  summary: GitMirrorSummary;
};

export type GraphContextStatus = {
  available: boolean;
  enabled: boolean;
  present: boolean;
  repo?: string;
  node_count?: number | null;
  edge_count?: number | null;
  report_present: boolean;
  graph_path?: string | null;
  graph_rel_path?: string | null;
  report_path?: string | null;
  report_rel_path?: string | null;
  out_rel_path?: string | null;
  graph_bytes?: number | null;
  report_bytes?: number | null;
  built_at?: string | null;
  last_error?: string | null;
  mirror_present?: boolean;
  version?: string | null;
  install_hint?: string | null;
  llm_provider?: string | null;
  llm_ready?: boolean;
  llm_backend?: string | null;
  llm_model?: string | null;
  extract_running?: boolean;
  extract_pid?: number | null;
  extract_started_at?: string | null;
  extract_timeout_minutes?: number;
};

export type GraphifySummary = {
  present: boolean;
  node_count: number;
  edge_count: number;
  node_kinds: Record<string, number>;
  top_nodes: Array<{ id: string; label: string; degree: number }>;
  sample_edges: Array<{ source: string; target: string; kind: string }>;
};

export type GraphifyDetailResponse = GraphContextStatus & {
  summary?: GraphifySummary | null;
};

export type GraphifyReportResponse = {
  present: boolean;
  repo?: string;
  content: string;
  truncated?: boolean;
  bytes?: number | null;
  rel_path?: string | null;
  synthetic?: boolean;
};

export type GraphifySummaryResponse = GraphifySummary;

export type GraphifyRebuildResult = {
  ok: boolean;
  result: {
    ok?: boolean;
    error?: string;
    skipped?: boolean;
    reason?: string;
  };
  status: GraphifyDetailResponse;
};

export type ContextSuggestion = {
  id: string;
  kind: string;
  title: string;
  description: string;
  playbook_filename: string;
  status: string;
  created_at?: string;
  source_commit?: string | null;
};

export type RepoContextStatus = {
  main_repo: string;
  configured: boolean;
  generated_at?: string | null;
  head_sha?: string | null;
  files: string[];
  mirror_present: boolean;
  graphify_enabled: boolean;
  graph?: GraphContextStatus;
};

export type RepoContextBuildResult = {
  ok: boolean;
  error?: string;
  repo?: string;
  manifest?: {
    repo: string;
    head_sha?: string | null;
    generated_at?: string;
    files?: string[];
  };
};

export type RepoContextResponse = {
  status: RepoContextStatus;
  preview: string;
  suggestions: ContextSuggestion[];
};

export type RepoContextGenerateResult = {
  ok: boolean;
  manifest: RepoContextBuildResult["manifest"];
  status: RepoContextStatus;
  suggestions: ContextSuggestion[];
};

export type RepoContextSyncMainResult = {
  ok: boolean;
  sync_results: Array<{ repo: string; ok: boolean; action?: string; error?: string }>;
  context?: RepoContextBuildResult | null;
  status: RepoContextStatus;
  suggestions: ContextSuggestion[];
  shared: GitMirrorShared[];
  summary: GitMirrorSummary;
};

export type ObservabilityQuery = {
  preset?: string;
  bucket?: "hour" | "day" | "month";
  source?: string;
  user?: string;
  model?: string;
  provider?: string;
  event_type?: "llm_call" | "tool_call";
  tool_category?: string;
  since?: string;
  until?: string;
};

export type ObservabilitySummary = {
  llm_calls: number;
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  total_tasks?: number;
  successful_tasks?: number;
  plan_events?: number;
  feedback_good?: number;
  feedback_bad?: number;
  by_source: Record<string, number>;
  by_user: Record<string, number>;
  by_model: Record<string, number>;
  by_tool_category: Record<string, number>;
  by_plan?: Record<string, number>;
  by_plan_tokens?: Record<string, number>;
};

export type ObservabilityTimeseries = {
  bucket: "hour" | "day" | "month";
  points: Array<{
    period: string;
    llm_calls: number;
    tool_calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
  }>;
};

export type ObservabilityEvent = {
  recorded_at: string;
  event_type: "llm_call" | "tool_call";
  source: string;
  user_id: string;
  user_label: string;
  user_display_name?: string;
  task_id?: string | null;
  session_key?: string | null;
  provider?: string | null;
  model?: string | null;
  call_kind: string;
  skill_name?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd?: number | null;
  duration_ms?: number | null;
  tool_name?: string | null;
  tool_category?: string | null;
  success: boolean;
  metadata?: Record<string, unknown>;
};

export type ObservabilityFilters = Record<string, unknown>;

export type ObservabilitySummaryResponse = {
  filters: ObservabilityFilters;
  summary: ObservabilitySummary;
};

export type ObservabilityTimeseriesResponse = {
  filters: ObservabilityFilters;
  timeseries: ObservabilityTimeseries;
};

export type ObservabilityEventsResponse = {
  filters: ObservabilityFilters;
  total: number;
  events: ObservabilityEvent[];
};

export type ObservabilityFilterOptions = {
  sources: string[];
  users: string[];
  models: string[];
  providers: string[];
  tool_categories: string[];
};

export type GovernanceAuditEntry = {
  id: number;
  recorded_at: string;
  task_id: string;
  session_key: string;
  source: string;
  user_id: string;
  channel_id: string;
  skill_name: string;
  tool_name: string;
  tool_args: string;
  result_kind: string;
  success: boolean;
  message: string;
  blocked: boolean;
};

export type GovernanceAuditResponse = {
  entries: GovernanceAuditEntry[];
  total: number;
};

export type DbTableStats = {
  rows: number;
  oldest?: string | null;
  newest?: string | null;
};

export type DbStatsResponse = {
  path: string;
  rel_path?: string | null;
  size_bytes: number;
  tables: {
    interaction_events: DbTableStats;
    conversation_sessions: DbTableStats;
    slack_user_names: DbTableStats;
  };
};

export type DbCleanupScope = "observability" | "sessions" | "slack_cache" | "all";

export type DbCleanupRequest = {
  scope: DbCleanupScope;
  older_than_days?: number | null;
  vacuum?: boolean;
};

export type DbCleanupResult = {
  ok: boolean;
  scope: DbCleanupScope;
  older_than_days?: number | null;
  removed: {
    interaction_events: number;
    conversation_sessions: number;
    slack_user_names: number;
  };
  stats: DbStatsResponse;
};

export type PlaybookSummary = {
  filename: string;
  name?: string;
  triggers?: string[];
  mode?: string;
  channels?: string[];
  fetch_urls?: string[];
  fetch_ttl_minutes?: number;
  size_bytes?: number;
  updated_at?: string | null;
  parse_error?: string;
};

export type PlaybooksListResponse = {
  directory: string;
  playbooks: PlaybookSummary[];
  example_available: boolean;
};

export type PlaybookDetail = PlaybookSummary & {
  content: string;
  ok?: boolean;
};

export type PendingPlaybook = {
  id: string;
  kind: string;
  title: string;
  description: string;
  playbook_filename: string;
  playbook_name?: string;
  proposed_content: string;
  status: string;
  created_at: string;
  source_task_id?: string;
  source_intent?: string;
  source_channel_id?: string;
  source?: string;
};

export type PendingPlaybooksResponse = {
  pending: PendingPlaybook[];
  total: number;
};

export type ScheduledJob = {
  id: string;
  name: string;
  description?: string | null;
  cron_expression: string;
  skill_name: string;
  channel_id?: string | null;
  user_id?: string | null;
  status: "active" | "inactive";
  created_at: number;
  updated_at: number;
  last_run_at?: number | null;
  last_run_status?: string | null;
  instructions?: string;
  timezone?: string;
};

export type LogEvent = {
  timestamp: string;
  level: string;
  module: string;
  message: string;
  category: "slack" | "git" | "system";
};

export type PlaybookExampleResponse = {
  filename: string;
  content: string;
};

export type ScriptArgMeta = {
  name: string;
  description?: string;
  required?: boolean;
  default?: string | null;
};

export type ScriptPackageSummary = {
  name: string;
  description?: string;
  runtime: string;
  entry: string;
  relative_path: string;
  kind: string;
  file_count: number;
  files: string[];
  args: ScriptArgMeta[];
};

export type ScriptsListResponse = {
  directory: string;
  packages: ScriptPackageSummary[];
  example_available: boolean;
};

export type ScriptFileDetail = {
  relative_path: string;
  content: string;
  size_bytes?: number;
  updated_at?: string | null;
  is_manifest?: boolean;
};

export type ScriptExampleResponse = {
  package_path: string;
  files: Record<string, string>;
};

function buildObservabilityQuery(params: ObservabilityQuery & { limit?: number; offset?: number }) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
