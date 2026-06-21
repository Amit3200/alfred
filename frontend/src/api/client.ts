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
  };
  git: {
    enabled: boolean;
    provider: "github" | "gitlab";
    token: string;
    default_org: string;
    repos: string[];
    mirror_ttl_hours?: number;
    mirror_refresh_minutes?: number;
    mirror_max_workspaces?: number;
    mirror_shallow_depth?: number;
  };
  aws: {
    enabled: boolean;
    profile: string;
    region: string;
    access_key_id: string;
    secret_access_key: string;
    allowed_services: string[];
  };
  ai: {
    default_provider: string;
    routing: {
      skill_matching: string;
      investigation: string;
      workflow_execution: string;
    };
    providers: Record<string, AIProviderConfig>;
  };
  skills: {
    directory: string;
    custom_directory: string;
    disabled: string[];
  };
  _secrets_configured?: {
    slack_bot_token: boolean;
    slack_bot_token_valid?: boolean;
    slack_bot_token_hint?: string | null;
    slack_signing_secret: boolean;
    slack_app_token: boolean;
    git_token: boolean;
    aws_access_key_id: boolean;
    aws_secret_access_key: boolean;
    server_admin_token: boolean;
    ai_api_keys: Record<string, boolean>;
  };
};

export type SecretsPayload = {
  slack_bot_token?: string;
  slack_signing_secret?: string;
  slack_app_token?: string;
  git_token?: string;
  aws_access_key_id?: string;
  aws_secret_access_key?: string;
  server_admin_token?: string;
  ai_api_keys?: Record<string, string>;
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
      throw new Error(
        detail === "Invalid admin token"
          ? "Invalid admin token — run alfred token from the project directory (see data dir on Secrets page)"
          : detail || "Unauthorized",
      );
    }
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () =>
    request<{ status: string; version: string; initialized: boolean; data_dir?: string }>(
      "/api/health",
    ),
  checks: () => request<Record<string, { ok: boolean; message?: string; skipped?: boolean }>>("/api/health/checks"),
  getConfig: () => request<AlfredConfig>("/api/config"),
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
  ollamaStatus: () => request<OllamaStatus>("/api/ollama/status"),
  ollamaInstall: () => request<OllamaActionResult>("/api/ollama/install", { method: "POST" }),
  ollamaStart: () => request<OllamaActionResult>("/api/ollama/start", { method: "POST" }),
  ollamaPull: (model?: string) =>
    request<OllamaActionResult>("/api/ollama/pull", {
      method: "POST",
      body: JSON.stringify({ model: model || null }),
    }),
  ollamaSetup: (model?: string) =>
    request<OllamaActionResult>("/api/ollama/setup", {
      method: "POST",
      body: JSON.stringify({ model: model || null }),
    }),

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
};

export type ChatSessionSummary = {
  id: string;
  title: string;
  message_count: number;
  updated_at?: string;
  created_at?: string;
};

export type ResponsePayload = {
  kind: "text" | "pr_list" | "pr_detail" | "repo_list" | "error";
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

export type GitMirrorSummary = {
  workspaces_count: number;
  shared_count: number;
  workspaces_bytes: number;
  shared_bytes: number;
  total_bytes: number;
  mirror_ttl_hours: number;
  mirror_max_workspaces: number;
  mirror_refresh_minutes: number;
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
  shared: GitMirrorShared[];
  summary: GitMirrorSummary;
};
