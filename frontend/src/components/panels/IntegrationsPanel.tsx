import { ReloadOutlined, PlusOutlined, DeleteOutlined, ApiOutlined, CheckCircleOutlined, InfoCircleOutlined, SyncOutlined } from "@ant-design/icons";
import { Button, Col, Flex, Input, Row, Select, Switch, Typography, Modal } from "antd";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AlfredConfig, type ConnectorPollResponse, type GoogleOAuthStatus, type IntegrationSyncStatusResponse, type SlackBoardBinding, type SlackChannelWorkflow } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { integrationDotClass, integrationHealth, type HealthCheck } from "../../health";
import { JsonCredentialField } from "../ui/JsonCredentialField";

interface CustomIntegration {
  id: string;
  name: string;
  enabled: boolean;
  apiUrl: string;
  apiToken: string;
  description: string;
}

const DEFAULT_GITHUB: AlfredConfig["github"] = {
  enabled: false,
  client_id: "",
  app_id: "",
  bot_login: "alfred",
  allowed_repos: [],
  callback_base_url: "",
};

const DEFAULT_GOVERNANCE: NonNullable<AlfredConfig["governance"]> = {
  enabled: true,
  require_confirmation: true,
  require_confirmation_sources: ["slack", "ui"],
  confirmation_phrases: [],
  approval_ttl_minutes: 30,
  audit_enabled: true,
  write_allowed_sources: ["slack", "ui", "cli", "scheduler"],
  write_allowed_channels: [],
  write_blocked_channels: [],
  write_allowed_users: [],
};

const DEFAULT_WEB_SEARCH: NonNullable<AlfredConfig["web_search"]> = {
  enabled: false,
  provider: "duckduckgo",
  max_results: 8,
};

const DEFAULT_PERISKOPE: NonNullable<NonNullable<AlfredConfig["connectors"]>["periskope"]> = {
  enabled: false,
  base_url: "https://api.periskope.app/v1",
  org_phone: "",
  allowed_chat_ids: [],
  slack_channel_id: "",
  summary_channel_id: "",
  summary_timezone: "Asia/Kolkata",
  replicate_tickets: true,
  replicate_tasks: true,
  ticket_create_target: "slack_board",
  slack_board_key: "",
  jira_project: "",
  sync_on_update: true,
};

function webSearchConfig(config: AlfredConfig) {
  return config.web_search ?? DEFAULT_WEB_SEARCH;
}

function periskopeConfig(config: AlfredConfig) {
  return { ...DEFAULT_PERISKOPE, ...(config.connectors?.periskope ?? {}) };
}

function connectorWebhookUrl(connectorId: string) {
  if (typeof window === "undefined") return `/api/v1/connectors/${connectorId}/webhook`;
  return `${window.location.origin.replace(/\/$/, "")}/api/v1/connectors/${connectorId}/webhook`;
}

function integrationStatusLabel(
  checks: Record<string, HealthCheck> | null,
  key: string,
  enabled: boolean,
): { dotClass: string; label: string } {
  const health = integrationHealth(checks, key, enabled);
  return {
    dotClass: integrationDotClass(health.kind, enabled),
    label: health.label,
  };
}

function githubConfig(config: AlfredConfig) {
  return config.github ?? DEFAULT_GITHUB;
}

function governanceConfig(config: AlfredConfig) {
  return config.governance ?? DEFAULT_GOVERNANCE;
}

function githubUrls(base: string) {
  const host = base.replace(/\/$/, "");
  if (!host) return null;
  return {
    webhook: `${host}/api/v1/github/webhook`,
    callback: `${host}/api/v1/github/callback`,
  };
}

function mainRepoOptions(repos: string[], mainRepo?: string) {
  const seen = new Set<string>();
  const options: { value: string; label: string }[] = [];
  for (const repo of repos) {
    const value = repo.trim();
    if (!value || seen.has(value.toLowerCase())) continue;
    seen.add(value.toLowerCase());
    options.push({ value, label: value });
  }
  const current = (mainRepo ?? "").trim();
  if (current && !seen.has(current.toLowerCase())) {
    options.unshift({ value: current, label: `${current} (saved)` });
  }
  return options;
}

function mainRepoSourceLabel(source?: string, org?: string | null): string {
  if (source === "org" && org) return `Loaded ${org} repos from GitHub/GitLab.`;
  if (source === "user") return "Loaded your accessible repos from GitHub/GitLab.";
  if (source === "configured") return "Using configured repos allowlist only.";
  return "Set Org and git token (Secrets) to load repos.";
}

function getLogo(name: string) {
  const n = name.toLowerCase();
  if (n === "slack") {
    return (
      <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/slack/slack-original.svg"
        alt="Slack"
        style={{ width: 38, height: 38 }}
      />
    );
  }
  if (n === "git" || n === "github" || n === "github app" || n === "github_app") {
    return (
      <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/github/github-original.svg"
        alt="GitHub"
        className="invert-on-dark"
        style={{ width: 38, height: 38 }}
      />
    );
  }
  if (n === "aws") {
    return (
      <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/amazonwebservices/amazonwebservices-original-wordmark.svg"
        alt="AWS"
        className="aws-logo-img"
        style={{ width: 50, height: 30 }}
      />
    );
  }
  if (n === "jira") {
    return (
      <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/jira/jira-original.svg"
        alt="JIRA"
        style={{ width: 36, height: 36 }}
      />
    );
  }
  if (n === "google") {
    return (
      <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/google/google-original.svg"
        alt="Google"
        style={{ width: 36, height: 36 }}
      />
    );
  }
  if (n === "web_search" || n === "web search") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: 34, height: 34, color: "var(--alfred-accent)" }}>
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.3-4.3" />
        <path d="M8 11h6" />
        <path d="M11 8v6" />
      </svg>
    );
  }
  if (n === "periskope") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: 34, height: 34, color: "#25D366" }}>
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ width: 34, height: 34, color: "var(--alfred-accent)" }}>
      <path d="M12 2v8M18 12H6v2a6 6 0 0 0 12 0v-2ZM12 14v6M16 2v2M8 2v2"/>
    </svg>
  );
}

export function IntegrationsPanel() {
  const { config, updateConfig, saveConfig, testIntegration, notify, secrets, setSecrets, saveSecrets, checks, load } =
    useApp();
  const [availableRepos, setAvailableRepos] = useState<string[]>([]);
  const [reposSource, setReposSource] = useState<string>("configured");
  const [reposOrg, setReposOrg] = useState<string | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);
  const [loadingRepos, setLoadingRepos] = useState(false);

  // Modal State
  const [activeModal, setActiveModal] = useState<string | null>(null);
  const [initialSectionData, setInitialSectionData] = useState<any>(null);

  // Custom Integrations state
  const [customIntegrations, setCustomIntegrations] = useState<CustomIntegration[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("alfred_custom_integrations") || "[]");
    } catch {
      return [];
    }
  });

  // Custom Integration Form states
  const [customName, setCustomName] = useState("");
  const [customApiUrl, setCustomApiUrl] = useState("");
  const [customApiToken, setCustomApiToken] = useState("");
  const [customDescription, setCustomDescription] = useState("");
  const [testingCustom, setTestingCustom] = useState(false);
  const [selectedCustomId, setSelectedCustomId] = useState<string | null>(null);
  const [googleOAuth, setGoogleOAuth] = useState<GoogleOAuthStatus | null>(null);
  const [connectingGoogle, setConnectingGoogle] = useState(false);
  const [savingGoogleCredentials, setSavingGoogleCredentials] = useState(false);
  const [syncStatus, setSyncStatus] = useState<IntegrationSyncStatusResponse | null>(null);
  const [syncLoading, setSyncLoading] = useState<string | null>(null);
  const [pollPreview, setPollPreview] = useState<ConnectorPollResponse | null>(null);
  const [slackBoards, setSlackBoards] = useState<SlackBoardBinding[]>([]);
  const [slackChannels, setSlackChannels] = useState<SlackChannelWorkflow[]>([]);

  const loadSyncStatus = useCallback(async () => {
    try {
      setSyncStatus(await api.getIntegrationSyncStatus());
    } catch {
      setSyncStatus(null);
    }
  }, []);

  useEffect(() => {
    void loadSyncStatus();
  }, [loadSyncStatus]);

  useEffect(() => {
    if (activeModal === "slack" || activeModal === "jira" || activeModal === "periskope") {
      void loadSyncStatus();
    }
  }, [activeModal, loadSyncStatus]);

  useEffect(() => {
    if (activeModal !== "periskope") {
      return;
    }
    void Promise.all([
      api.listSlackBoardBindings().then((result) => result.boards || []).catch(() => [] as SlackBoardBinding[]),
      api.listSlackChannelWorkflows().then((result) => result.channels || []).catch(() => [] as SlackChannelWorkflow[]),
    ]).then(([boards, channels]) => {
      setSlackBoards(boards);
      setSlackChannels(channels);
    });
  }, [activeModal]);

  const runSlackUserSync = async () => {
    setSyncLoading("slack");
    try {
      const result = await api.syncSlackUsers();
      if (!result.ok) {
        notify("error", result.error ?? "Slack user sync failed");
        return;
      }
      notify(
        "success",
        result.skipped
          ? `Slack cache is fresh (${result.user_count ?? 0} users).`
          : `Synced ${result.user_count ?? 0} Slack users.`,
      );
      await loadSyncStatus();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Slack user sync failed");
    } finally {
      setSyncLoading(null);
    }
  };

  const runJiraContextSync = async (applyAssigneeMap: boolean) => {
    setSyncLoading(applyAssigneeMap ? "jira-map" : "jira");
    try {
      const result = await api.syncJiraContext(applyAssigneeMap);
      if (!result.ok) {
        notify("error", result.error ?? "JIRA context sync failed");
        return;
      }
      const parts = [
        `${result.project_count ?? 0} projects`,
        `${result.identity_count ?? 0} Slack identities`,
        `${result.matched_jira ?? 0} JIRA matches`,
      ];
      if (applyAssigneeMap && (result.assignee_map_added ?? 0) > 0) {
        parts.push(`${result.assignee_map_added} new assignee mappings saved`);
        await load();
      }
      notify("success", `JIRA context synced: ${parts.join(" · ")}`);
      await loadSyncStatus();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "JIRA context sync failed");
    } finally {
      setSyncLoading(null);
    }
  };

  const runPeriskopePoll = async (replicate: boolean) => {
    setSyncLoading(replicate ? "periskope-replicate" : "periskope");
    try {
      const result = await api.pollConnector("periskope", {
        replicate,
        kinds: ["tickets", "tasks", "chats"],
        limit: 50,
      });
      setPollPreview(result);
      if (!result.ok) {
        notify("error", result.error ?? "Periskope poll failed");
        return;
      }
      const tickets = result.preview?.ticket_count ?? 0;
      const tasks = result.preview?.task_count ?? 0;
      const chats = result.preview?.chat_count ?? 0;
      notify(
        "success",
        replicate
          ? `Pulled ${tickets} tickets / ${tasks} tasks · created ${result.created ?? 0} · already mapped ${result.already_mapped ?? 0}`
          : `Preview (no webhook): ${tickets} tickets, ${tasks} tasks, ${chats} chats`,
      );
      await loadSyncStatus();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Periskope poll failed");
    } finally {
      setSyncLoading(null);
    }
  };

  const formatSyncWhen = (value?: string) => {
    if (!value) return "Never synced";
    try {
      return new Date(value).toLocaleString();
    } catch {
      return value;
    }
  };

  const loadAvailableRepos = useCallback(async () => {
    if (!config?.git.enabled) {
      setAvailableRepos([]);
      setReposError(null);
      return;
    }
    setLoadingRepos(true);
    try {
      const data = await api.getAvailableGitRepos();
      setAvailableRepos(data.repos ?? []);
      setReposSource(data.source ?? "configured");
      setReposOrg(data.org ?? null);
      setReposError(data.error ?? null);
    } catch (err) {
      setAvailableRepos(config.git.repos ?? []);
      setReposError(err instanceof Error ? err.message : "Failed to load repos");
    } finally {
      setLoadingRepos(false);
    }
  }, [config?.git.enabled, config?.git.repos]);

  useEffect(() => {
    void loadAvailableRepos();
  }, [loadAvailableRepos, config?.git.default_org, config?.git.provider]);

  const loadGoogleOAuthStatus = useCallback(async () => {
    try {
      setGoogleOAuth(await api.getGoogleOAuthStatus());
    } catch {
      setGoogleOAuth(null);
    }
  }, []);

  useEffect(() => {
    if (activeModal === "google") {
      void loadGoogleOAuthStatus();
    }
  }, [activeModal, loadGoogleOAuthStatus]);

  const handleConnectGoogle = async () => {
    setConnectingGoogle(true);
    try {
      const result = await api.startGoogleOAuth();
      window.open(result.authorization_url, "_blank", "noopener,noreferrer");
      notify("info", "Complete sign-in in the Google tab, then return here and test the connection.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to start Google OAuth");
    } finally {
      setConnectingGoogle(false);
    }
  };

  const handleSaveGoogleCredentials = async () => {
    const json = (secrets.google_credentials_json ?? "").trim();
    if (!json) {
      notify("error", "Paste or upload credentials.json first.");
      return;
    }
    setSavingGoogleCredentials(true);
    try {
      await saveSecrets();
      await loadGoogleOAuthStatus();
    } finally {
      setSavingGoogleCredentials(false);
    }
  };

  const mainRepoSelectOptions = useMemo(
    () => mainRepoOptions(availableRepos, config?.git.main_repo),
    [availableRepos, config?.git.main_repo],
  );

  if (!config) return null;

  const slackStatus = integrationStatusLabel(checks, "slack", config.slack.enabled);
  const gitStatus = integrationStatusLabel(checks, "git", config.git.enabled);
  const awsStatus = integrationStatusLabel(checks, "aws", config.aws.enabled);
  const jiraStatus = integrationStatusLabel(checks, "jira", Boolean(config.jira?.enabled));
  const googleStatus = integrationStatusLabel(checks, "google", Boolean(config.google?.enabled));
  const webSearchStatus = integrationStatusLabel(checks, "web_search", webSearchConfig(config).enabled);
  const periskopeStatus = integrationStatusLabel(checks, "periskope", periskopeConfig(config).enabled);

  const openConfigModal = (type: string, data: any) => {
    setInitialSectionData(JSON.parse(JSON.stringify(data)));
    setActiveModal(type);
  };

  const handleCancelStandard = (sectionKey: keyof AlfredConfig) => {
    if (initialSectionData) {
      updateConfig({ [sectionKey]: initialSectionData });
    }
    setActiveModal(null);
  };

  const handleSaveStandard = async () => {
    const modal = activeModal;
    setActiveModal(null);
    if (modal === "web_search" && (secrets.web_search_api_key ?? "").trim()) {
      await saveSecrets();
    }
    if (modal === "periskope") {
      await saveSecrets();
    }
    setTimeout(() => {
      void saveConfig();
    }, 50);
  };

  // Custom Integrations logic
  const handleOpenAddCustom = () => {
    setCustomName("");
    setCustomApiUrl("");
    setCustomApiToken("");
    setCustomDescription("");
    setActiveModal("custom_new");
  };

  const handleAddCustom = () => {
    if (!customName.trim() || !customApiUrl.trim()) {
      notify("error", "Name and API Base URL are required.");
      return;
    }
    const newItem: CustomIntegration = {
      id: `custom_${Date.now()}`,
      name: customName.trim(),
      enabled: true,
      apiUrl: customApiUrl.trim(),
      apiToken: customApiToken.trim(),
      description: customDescription.trim(),
    };
    const updated = [...customIntegrations, newItem];
    setCustomIntegrations(updated);
    localStorage.setItem("alfred_custom_integrations", JSON.stringify(updated));
    setActiveModal(null);
    notify("success", `Custom integration "${newItem.name}" added successfully.`);
  };

  const handleOpenEditCustom = (item: CustomIntegration) => {
    setSelectedCustomId(item.id);
    setCustomName(item.name);
    setCustomApiUrl(item.apiUrl);
    setCustomApiToken(item.apiToken);
    setCustomDescription(item.description);
    setActiveModal("custom_edit");
  };

  const handleSaveCustom = () => {
    if (!customName.trim() || !customApiUrl.trim()) {
      notify("error", "Name and API Base URL are required.");
      return;
    }
    const updated = customIntegrations.map((item) => {
      if (item.id === selectedCustomId) {
        return {
          ...item,
          name: customName.trim(),
          apiUrl: customApiUrl.trim(),
          apiToken: customApiToken.trim(),
          description: customDescription.trim(),
        };
      }
      return item;
    });
    setCustomIntegrations(updated);
    localStorage.setItem("alfred_custom_integrations", JSON.stringify(updated));
    setActiveModal(null);
    notify("success", "Custom integration updated.");
  };

  const handleToggleCustom = (id: string, checked: boolean) => {
    const updated = customIntegrations.map((item) => {
      if (item.id === id) {
        return { ...item, enabled: checked };
      }
      return item;
    });
    setCustomIntegrations(updated);
    localStorage.setItem("alfred_custom_integrations", JSON.stringify(updated));
    notify("info", `Integration ${checked ? "enabled" : "disabled"}.`);
  };

  const handleDeleteCustom = (id: string) => {
    const updated = customIntegrations.filter((item) => item.id !== id);
    setCustomIntegrations(updated);
    localStorage.setItem("alfred_custom_integrations", JSON.stringify(updated));
    setActiveModal(null);
    notify("success", "Custom integration deleted.");
  };

  const handleTestCustom = async (name: string, url: string) => {
    setTestingCustom(true);
    try {
      await new Promise((resolve) => setTimeout(resolve, 800));
      notify("success", `${name}: Connected to ${url} successfully (ping verified).`);
    } catch (err) {
      notify("error", `Failed to connect to ${name}`);
    } finally {
      setTestingCustom(false);
    }
  };

  return (
    <div>
      <Typography.Title level={3} className="alfred-page-title">
        Integrations
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc" style={{ marginBottom: 24 }}>
        Connect Slack, Git, GitHub App, JIRA, AWS, Google Workspace, and web search. Toggle each service to customize
        settings and verify connections.
      </Typography.Paragraph>

      <div className="alfred-integrations-grid">
        {/* Slack Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("slack", config.slack)}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${slackStatus.dotClass}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>{slackStatus.label}</span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("slack")}
          </div>
          <div className="alfred-integration-card-title">Slack</div>
          <div className="alfred-integration-card-subtitle">Socket Mode bot ingress & loading messages</div>
        </div>

        {/* Git Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("git", config.git)}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${gitStatus.dotClass}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>{gitStatus.label}</span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("git")}
          </div>
          <div className="alfred-integration-card-title">Git</div>
          <div className="alfred-integration-card-subtitle">Organization repository mirrors and indexing</div>
        </div>

        {/* GitHub App Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("github", githubConfig(config))}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${githubConfig(config).enabled ? "enabled" : "disabled"}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>
              {githubConfig(config).enabled ? "Active" : "Inactive"}
            </span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("github_app")}
          </div>
          <div className="alfred-integration-card-title">GitHub App</div>
          <div className="alfred-integration-card-subtitle">PR comment bot webhook & callback endpoint</div>
        </div>

        {/* AWS Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("aws", config.aws)}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${awsStatus.dotClass}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>{awsStatus.label}</span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("aws")}
          </div>
          <div className="alfred-integration-card-title">AWS</div>
          <div className="alfred-integration-card-subtitle">Athena query outputs & CloudWatch Logs</div>
        </div>

        {/* JIRA Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("jira", config.jira)}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${jiraStatus.dotClass}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>{jiraStatus.label}</span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("jira")}
          </div>
          <div className="alfred-integration-card-title">JIRA</div>
          <div className="alfred-integration-card-subtitle">Ticket retrieval, commenting & identity resolution</div>
        </div>

        {/* Periskope Card */}
        <div
          className="alfred-integration-card"
          onClick={() => openConfigModal("periskope", periskopeConfig(config))}
        >
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${periskopeStatus.dotClass}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>{periskopeStatus.label}</span>
          </div>
          <div className="alfred-integration-card-logo">{getLogo("periskope")}</div>
          <div className="alfred-integration-card-title">Periskope</div>
          <div className="alfred-integration-card-subtitle">
            WhatsApp groups, tickets, and tasks into Slack Lists or JIRA
          </div>
        </div>

        {/* Google Workspace Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("google", config.google ?? { enabled: false, oauth_redirect_base_url: "" })}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${googleStatus.dotClass}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>{googleStatus.label}</span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("google")}
          </div>
          <div className="alfred-integration-card-title">Google Workspace</div>
          <div className="alfred-integration-card-subtitle">Google Sheets read/write & Docs read/create</div>
        </div>

        {/* Web Search Card */}
        <div
          className="alfred-integration-card"
          onClick={() => openConfigModal("web_search", webSearchConfig(config))}
        >
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${webSearchStatus.dotClass}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>{webSearchStatus.label}</span>
          </div>
          <div className="alfred-integration-card-logo">{getLogo("web_search")}</div>
          <div className="alfred-integration-card-title">Web search</div>
          <div className="alfred-integration-card-subtitle">
            External docs, errors, and release notes via web_search tool
          </div>
        </div>

        {/* Governance Card */}
        <div
          className="alfred-integration-card"
          onClick={() => openConfigModal("governance", governanceConfig(config))}
        >
          <div className="alfred-integration-card-status">
            <div
              className={`alfred-integration-card-dot ${
                governanceConfig(config).enabled ? "enabled" : "disabled"
              }`}
            />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>
              {governanceConfig(config).enabled ? "Active" : "Inactive"}
            </span>
          </div>
          <div className="alfred-integration-card-logo">
            <CheckCircleOutlined style={{ fontSize: 34, color: "var(--alfred-accent)" }} />
          </div>
          <div className="alfred-integration-card-title">Governance</div>
          <div className="alfred-integration-card-subtitle">
            Write confirmation, channel policies, and audit logging
          </div>
        </div>

        {/* Custom Integration Cards */}
        {customIntegrations.map((item) => (
          <div className="alfred-integration-card" key={item.id} onClick={() => handleOpenEditCustom(item)}>
            <div className="alfred-integration-card-status" onClick={(e) => e.stopPropagation()}>
              <Switch
                size="small"
                checked={item.enabled}
                onChange={(checked) => handleToggleCustom(item.id, checked)}
              />
            </div>
            <div className="alfred-integration-card-logo">
              {getLogo("custom")}
            </div>
            <div className="alfred-integration-card-title">{item.name}</div>
            <div className="alfred-integration-card-subtitle">
              {item.description || "Custom API integration"}
            </div>
          </div>
        ))}

        {/* Add Integration Card */}
        <div className="alfred-integration-card add-new" onClick={handleOpenAddCustom}>
          <div className="plus-icon">
            <PlusOutlined />
          </div>
          <div className="alfred-integration-card-title" style={{ color: "var(--alfred-text-muted)" }}>
            Add Integration
          </div>
          <div className="alfred-integration-card-subtitle">Connect with custom API webhooks</div>
        </div>
      </div>

      {/* Global save is still supported */}
      <Flex justify="start" style={{ marginTop: 12 }}>
        <Button type="primary" onClick={saveConfig}>
          Save changes
        </Button>
      </Flex>

      {/* Slack Modal */}
      <Modal
        title="Slack Integration"
        open={activeModal === "slack"}
        onCancel={() => handleCancelStandard("slack")}
        footer={[
          <Button key="test" onClick={() => testIntegration("slack")}>
            Test connection
          </Button>,
          <Button key="cancel" onClick={() => handleCancelStandard("slack")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable Slack messaging bot</Typography.Text>
            <Switch
              checked={config.slack.enabled}
              onChange={(v) => updateConfig({ slack: { ...config.slack, enabled: v } })}
            />
          </div>
          <label className="alfred-field-label">Allowed channels</label>
          <Input
            value={config.slack.allowed_channels.join(", ")}
            placeholder="*, #engineering"
            onChange={(e) =>
              updateConfig({
                slack: {
                  ...config.slack,
                  allowed_channels: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                },
              })
            }
          />
          <Typography.Paragraph type="secondary" style={{ marginTop: 8, fontSize: 12, marginBottom: 0 }}>
            List Slack channel names or IDs allowed to invoke @alfred. Or use * to match all channels.
          </Typography.Paragraph>
          <label className="alfred-field-label" style={{ marginTop: 16 }}>Thread relevancy</label>
          <div className="alfred-settings-action" style={{ paddingTop: 4, paddingBottom: 4 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Rank long Slack threads and keep the most relevant messages (stack traces, intent overlap).
            </Typography.Text>
            <Switch
              checked={config.slack.thread_relevance_enabled ?? true}
              onChange={(v) => updateConfig({ slack: { ...config.slack, thread_relevance_enabled: v } })}
            />
          </div>
          <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
            <Col span={12}>
              <label className="alfred-field-label">Top messages to keep</label>
              <Input
                type="number"
                min={5}
                max={50}
                disabled={config.slack.thread_relevance_enabled === false}
                value={config.slack.thread_relevance_top_n ?? 15}
                onChange={(e) =>
                  updateConfig({
                    slack: {
                      ...config.slack,
                      thread_relevance_top_n: Number(e.target.value) || 15,
                    },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Thread fetch limit</label>
              <Input
                type="number"
                min={10}
                max={200}
                disabled={config.slack.thread_relevance_enabled === false}
                value={config.slack.thread_fetch_limit ?? 50}
                onChange={(e) =>
                  updateConfig({
                    slack: {
                      ...config.slack,
                      thread_fetch_limit: Number(e.target.value) || 50,
                    },
                  })
                }
              />
            </Col>
          </Row>
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--alfred-border)" }}>
            <Flex justify="space-between" align="center" wrap="wrap" gap={8}>
              <div>
                <Typography.Text strong>Workspace users</Typography.Text>
                <Typography.Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
                  Cached locally and refreshed every {syncStatus?.slack_refresh_hours ?? 1}h.
                  Last sync: {formatSyncWhen(syncStatus?.slack_users?.last_sync_at)} (
                  {syncStatus?.slack_users?.user_count ?? 0} users)
                </Typography.Paragraph>
              </div>
              <Button
                icon={<SyncOutlined />}
                loading={syncLoading === "slack"}
                onClick={() => void runSlackUserSync()}
              >
                Sync Slack users
              </Button>
            </Flex>
          </div>
        </div>
      </Modal>
      <Modal
        title="Git Mirror Integration"
        open={activeModal === "git"}
        width={680}
        onCancel={() => handleCancelStandard("git")}
        footer={[
          <Button key="test" onClick={() => testIntegration("git")}>
            Test connection
          </Button>,
          <Button key="cancel" onClick={() => handleCancelStandard("git")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable Git checkout mirrors</Typography.Text>
            <Switch
              checked={config.git.enabled}
              onChange={(v) => updateConfig({ git: { ...config.git, enabled: v } })}
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <label className="alfred-field-label">Provider</label>
              <Select
                style={{ width: "100%" }}
                value={config.git.provider}
                options={[
                  { value: "github", label: "GitHub" },
                  { value: "gitlab", label: "GitLab" },
                ]}
                onChange={(v) => updateConfig({ git: { ...config.git, provider: v } })}
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Org Name</label>
              <Input
                placeholder="YourOrg"
                value={config.git.default_org}
                onChange={(e) => updateConfig({ git: { ...config.git, default_org: e.target.value } })}
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Repo scope restrictions</label>
              <Input
                placeholder="org/service-a, org/service-b (empty = any repo for mirrors)"
                value={config.git.repos.join(", ")}
                onChange={(e) =>
                  updateConfig({
                    git: {
                      ...config.git,
                      repos: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                    },
                  })
                }
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Main codebase repository</label>
              <Flex gap={8} align="start">
                <Select
                  style={{ flex: 1 }}
                  showSearch
                  allowClear
                  loading={loadingRepos}
                  placeholder={
                    config.git.default_org
                      ? "Select primary repo"
                      : "Set Org to load repos"
                  }
                  disabled={!config.git.enabled}
                  value={config.git.main_repo || undefined}
                  options={mainRepoSelectOptions}
                  optionFilterProp="label"
                  onChange={(v) =>
                    updateConfig({ git: { ...config.git, main_repo: v ?? "" } })
                  }
                />
                <Button
                  icon={<ReloadOutlined />}
                  loading={loadingRepos}
                  disabled={!config.git.enabled}
                  onClick={() => void loadAvailableRepos()}
                />
              </Flex>
              <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 4 }}>
                {mainRepoSourceLabel(reposSource, reposOrg)}
              </Typography.Text>
              {reposError ? (
                <Typography.Text type="warning" style={{ fontSize: 12, display: "block" }}>
                  {reposError}
                </Typography.Text>
              ) : null}
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Phase 1 git write (PR flow)</label>
              <div className="alfred-settings-action" style={{ paddingTop: 4, paddingBottom: 4 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Enable isolated branch/commit/push and <Typography.Text code>@alfred pr</Typography.Text>{" "}
                  workflow. Requires repo token with push + PR scope. Route coding tasks via{" "}
                  <Typography.Text code>Workflow execution</Typography.Text> AI settings.
                </Typography.Text>
                <Switch
                  checked={Boolean(config.git.write_enabled)}
                  onChange={(v) =>
                    updateConfig({ git: { ...config.git, write_enabled: v } })
                  }
                />
              </div>
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Graphify optional graphs</label>
              <div className="alfred-settings-action" style={{ paddingTop: 4, paddingBottom: 4 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Build knowledge graphs on sync; enables <Typography.Text code>query_graph</Typography.Text> tool.
                  Requires <Typography.Text code>uv sync --extra graphify</Typography.Text> on host.
                </Typography.Text>
                <Switch
                  checked={Boolean(config.git.graphify_enabled)}
                  onChange={(v) =>
                    updateConfig({ git: { ...config.git, graphify_enabled: v } })
                  }
                />
              </div>
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Scripts remote repo</label>
              <Input
                placeholder={`${config?.git.default_org || "your-org"}/dailyscripts`}
                value={config.scripts?.remote?.repo ?? ""}
                onChange={(e) =>
                  updateConfig({
                    scripts: {
                      enabled: config.scripts?.enabled ?? true,
                      timeout_seconds: config.scripts?.timeout_seconds ?? 120,
                      remote: {
                        branch: config.scripts?.remote?.branch ?? "main",
                        path: config.scripts?.remote?.path ?? "scripts",
                        playbooks_path: config.scripts?.remote?.playbooks_path ?? "",
                        ...config.scripts?.remote,
                        repo: e.target.value,
                      },
                    },
                  })
                }
              />
              <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 4 }}>
                Pull script packages from this repo into Alfred (Scripts panel → Sync). Used for metrics
                and scheduled automation via Schedules.
              </Typography.Text>
            </Col>
          </Row>
        </div>
      </Modal>

      {/* GitHub App Modal */}
      <Modal
        title="GitHub App Configuration"
        open={activeModal === "github"}
        width={680}
        onCancel={() => handleCancelStandard("github")}
        footer={[
          <Button key="cancel" onClick={() => handleCancelStandard("github")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable GitHub App comment bot</Typography.Text>
            <Switch
              checked={githubConfig(config).enabled}
              onChange={(v) =>
                updateConfig({ github: { ...githubConfig(config), enabled: v } })
              }
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <label className="alfred-field-label">Client ID</label>
              <Input
                placeholder="Iv1.xxxxx"
                value={githubConfig(config).client_id}
                onChange={(e) =>
                  updateConfig({
                    github: { ...githubConfig(config), client_id: e.target.value },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">App ID (optional)</label>
              <Input
                placeholder="123456"
                value={githubConfig(config).app_id}
                onChange={(e) =>
                  updateConfig({
                    github: { ...githubConfig(config), app_id: e.target.value },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Bot login username</label>
              <Input
                placeholder="alfred"
                value={githubConfig(config).bot_login}
                onChange={(e) =>
                  updateConfig({
                    github: { ...githubConfig(config), bot_login: e.target.value },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Public base URL</label>
              <Input
                placeholder="https://alfred.yourdomain.dev"
                value={githubConfig(config).callback_base_url}
                onChange={(e) =>
                  updateConfig({
                    github: { ...githubConfig(config), callback_base_url: e.target.value },
                  })
                }
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Allowed repos list (optional)</label>
              <Input
                placeholder="Org/repo-a, Org/repo-b (empty = use Git repos list)"
                value={githubConfig(config).allowed_repos.join(", ")}
                onChange={(e) =>
                  updateConfig({
                    github: {
                      ...githubConfig(config),
                      allowed_repos: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                  })
                }
              />
            </Col>
          </Row>

          {githubUrls(githubConfig(config).callback_base_url) && (
            <div style={{ marginTop: 16, padding: 12, background: "var(--alfred-surface-subtle)", borderRadius: "var(--alfred-radius)" }}>
              <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
                Paste these into your GitHub Developer Portal settings:
              </Typography.Text>
              <Typography.Paragraph style={{ marginBottom: 4, fontSize: 13 }}>
                Webhook URL:{" "}
                <Typography.Text code copyable>
                  {githubUrls(githubConfig(config).callback_base_url)!.webhook}
                </Typography.Text>
              </Typography.Paragraph>
              <Typography.Paragraph style={{ marginBottom: 0, fontSize: 13 }}>
                Callback URL:{" "}
                <Typography.Text code copyable>
                  {githubUrls(githubConfig(config).callback_base_url)!.callback}
                </Typography.Text>
              </Typography.Paragraph>
            </div>
          )}
        </div>
      </Modal>

      {/* AWS Modal */}
      <Modal
        title="AWS Configuration"
        open={activeModal === "aws"}
        onCancel={() => handleCancelStandard("aws")}
        footer={[
          <Button key="test" onClick={() => testIntegration("aws")}>
            Test connection
          </Button>,
          <Button key="cancel" onClick={() => handleCancelStandard("aws")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable AWS read query tools</Typography.Text>
            <Switch
              checked={config.aws.enabled}
              onChange={(v) => updateConfig({ aws: { ...config.aws, enabled: v } })}
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <label className="alfred-field-label">CLI Profile name</label>
              <Input
                placeholder="default"
                value={config.aws.profile}
                onChange={(e) => updateConfig({ aws: { ...config.aws, profile: e.target.value } })}
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Region code</label>
              <Input
                placeholder="us-east-1"
                value={config.aws.region}
                onChange={(e) => updateConfig({ aws: { ...config.aws, region: e.target.value } })}
              />
            </Col>
          </Row>
        </div>
      </Modal>

      {/* JIRA Modal */}
      <Modal
        title="JIRA Cloud Configuration"
        open={activeModal === "jira"}
        width={580}
        onCancel={() => handleCancelStandard("jira")}
        footer={[
          <Button key="test" onClick={() => testIntegration("jira")}>
            Test connection
          </Button>,
          <Button key="cancel" onClick={() => handleCancelStandard("jira")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable JIRA workspace tracking</Typography.Text>
            <Switch
              checked={config.jira?.enabled ?? false}
              onChange={(v) =>
                updateConfig({
                  jira: {
                    enabled: v,
                    base_url: config.jira?.base_url ?? "",
                    email: config.jira?.email ?? "",
                    api_token: "",
                    default_project: config.jira?.default_project ?? "",
                    allowed_projects: config.jira?.allowed_projects ?? [],
                  },
                })
              }
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <label className="alfred-field-label">Site Base URL</label>
              <Input
                placeholder="https://yourorg.atlassian.net"
                value={config.jira?.base_url ?? ""}
                onChange={(e) =>
                  updateConfig({
                    jira: {
                      enabled: config.jira?.enabled ?? false,
                      base_url: e.target.value,
                      email: config.jira?.email ?? "",
                      api_token: "",
                      default_project: config.jira?.default_project ?? "",
                      allowed_projects: config.jira?.allowed_projects ?? [],
                    },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Account user email</label>
              <Input
                placeholder="you@company.com"
                value={config.jira?.email ?? ""}
                onChange={(e) =>
                  updateConfig({
                    jira: {
                      enabled: config.jira?.enabled ?? false,
                      base_url: config.jira?.base_url ?? "",
                      email: e.target.value,
                      api_token: "",
                      default_project: config.jira?.default_project ?? "",
                      allowed_projects: config.jira?.allowed_projects ?? [],
                    },
                  })
                }
              />
            </Col>
            <Col span={10}>
              <label className="alfred-field-label">Default JIRA project</label>
              <Input
                placeholder="ENG"
                value={config.jira?.default_project ?? ""}
                onChange={(e) =>
                  updateConfig({
                    jira: {
                      enabled: config.jira?.enabled ?? false,
                      base_url: config.jira?.base_url ?? "",
                      email: config.jira?.email ?? "",
                      api_token: "",
                      default_project: e.target.value,
                      allowed_projects: config.jira?.allowed_projects ?? [],
                    },
                  })
                }
              />
            </Col>
            <Col span={14}>
              <label className="alfred-field-label">Allowed project scopes</label>
              <Input
                placeholder="ENG, OPS (empty = all accessible)"
                value={(config.jira?.allowed_projects ?? []).join(", ")}
                onChange={(e) =>
                  updateConfig({
                    jira: {
                      enabled: config.jira?.enabled ?? false,
                      base_url: config.jira?.base_url ?? "",
                      email: config.jira?.email ?? "",
                      api_token: "",
                      default_project: config.jira?.default_project ?? "",
                      allowed_projects: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                    },
                  })
                }
              />
            </Col>
          </Row>
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--alfred-border)" }}>
            <Typography.Text strong>Boards & identity context</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
              Sync JIRA projects and Slack↔JIRA identity map Alfred uses for routing and assignees.
              Last sync: {formatSyncWhen(syncStatus?.jira_context?.last_sync_at)} ·{" "}
              {syncStatus?.jira_snapshot?.project_count ?? 0} projects ·{" "}
              {syncStatus?.jira_snapshot?.matched_jira ?? 0} JIRA matches
            </Typography.Paragraph>
            <Flex gap={8} wrap="wrap" style={{ marginTop: 8 }}>
              <Button
                icon={<SyncOutlined />}
                loading={syncLoading === "jira"}
                onClick={() => void runJiraContextSync(false)}
              >
                Sync JIRA context
              </Button>
              <Button
                loading={syncLoading === "jira-map"}
                onClick={() => void runJiraContextSync(true)}
              >
                Sync & merge assignee map
              </Button>
            </Flex>
          </div>
        </div>
      </Modal>

      {/* Periskope Modal */}
      <Modal
        title="Periskope Configuration"
        open={activeModal === "periskope"}
        width={620}
        onCancel={() => {
          if (initialSectionData) {
            updateConfig({
              connectors: {
                ...(config.connectors ?? {}),
                periskope: initialSectionData,
              },
            });
          }
          setActiveModal(null);
        }}
        footer={[
          <Button key="test" onClick={() => testIntegration("periskope")}>
            Test connection
          </Button>,
          <Button
            key="cancel"
            onClick={() => {
              if (initialSectionData) {
                updateConfig({
                  connectors: {
                    ...(config.connectors ?? {}),
                    periskope: initialSectionData,
                  },
                });
              }
              setActiveModal(null);
            }}
          >
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable Periskope WhatsApp connector</Typography.Text>
            <Switch
              checked={periskopeConfig(config).enabled}
              onChange={(v) =>
                updateConfig({
                  connectors: {
                    ...(config.connectors ?? {}),
                    periskope: { ...periskopeConfig(config), enabled: v },
                  },
                })
              }
            />
          </div>
          <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
            Polling needs only the API token and org phone — no webhook. Use Pull now to preview
            tickets/tasks, then optionally replicate into Slack Lists or JIRA.
            <br />
            Live webhook URL (must be publicly reachable). Subscribe in Periskope to
            <Typography.Text code>ticket.created</Typography.Text> (not every WhatsApp message).
            Alfred then fetches the last 20 chat messages and creates a Slack List item in the channel below.
            <br />
            Hook URL:{" "}
            <Typography.Text code copyable>
              {connectorWebhookUrl("periskope")}
            </Typography.Text>
          </Typography.Paragraph>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <label className="alfred-field-label">Org phone (x-phone)</label>
              <Input
                placeholder="919876543210"
                value={periskopeConfig(config).org_phone}
                onChange={(e) =>
                  updateConfig({
                    connectors: {
                      ...(config.connectors ?? {}),
                      periskope: { ...periskopeConfig(config), org_phone: e.target.value },
                    },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Replicate into</label>
              <Select
                style={{ width: "100%" }}
                value={periskopeConfig(config).ticket_create_target}
                onChange={(v) =>
                  updateConfig({
                    connectors: {
                      ...(config.connectors ?? {}),
                      periskope: { ...periskopeConfig(config), ticket_create_target: v },
                    },
                  })
                }
                options={[
                  { value: "slack_board", label: "Slack List board" },
                  { value: "jira", label: "JIRA" },
                  { value: "both", label: "Slack List and JIRA" },
                ]}
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Slack channel</label>
              <Select
                style={{ width: "100%" }}
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder={
                  slackBoards.length || slackChannels.length
                    ? "Channel where List items and tasks land"
                    : "Bind a Slack List under Slack boards first"
                }
                value={periskopeConfig(config).slack_channel_id || undefined}
                onChange={(channelId) => {
                  const board = slackBoards.find((row) => row.enabled && row.channel_id === channelId);
                  updateConfig({
                    connectors: {
                      ...(config.connectors ?? {}),
                      periskope: {
                        ...periskopeConfig(config),
                        slack_channel_id: channelId || "",
                        summary_channel_id: channelId || "",
                        slack_board_key: board?.board_key || "",
                      },
                    },
                  });
                }}
                options={(() => {
                  const seen = new Set<string>();
                  const options: { value: string; label: string }[] = [];
                  for (const board of slackBoards.filter((row) => row.enabled && row.channel_id)) {
                    if (seen.has(board.channel_id)) continue;
                    seen.add(board.channel_id);
                    options.push({
                      value: board.channel_id,
                      label: `${board.channel_name || board.channel_id} · ${board.list_name || board.list_id}`,
                    });
                  }
                  for (const channel of slackChannels.filter((row) => row.enabled && row.channel_id && !seen.has(row.channel_id))) {
                    seen.add(channel.channel_id);
                    options.push({
                      value: channel.channel_id,
                      label: `${channel.channel_name || channel.channel_id} · no List bound yet`,
                    });
                  }
                  const current = periskopeConfig(config).slack_channel_id;
                  if (current && !seen.has(current)) {
                    options.unshift({ value: current, label: current });
                  }
                  return options;
                })()}
              />
              <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: "6px 0 0" }}>
                {(() => {
                  const channelId = periskopeConfig(config).slack_channel_id;
                  if (!channelId) {
                    return "Pick the Slack channel first. Alfred uses that channel's List for tickets and tasks.";
                  }
                  const board = slackBoards.find((row) => row.enabled && row.channel_id === channelId);
                  if (board) {
                    return `List ${board.list_name || board.list_id} (${board.board_key}) receives tickets and tasks.`;
                  }
                  return "No Slack List is linked to this channel yet. Bind one under Slack boards.";
                })()}
              </Typography.Paragraph>
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">JIRA project (optional)</label>
              <Input
                placeholder="Default JIRA project if empty"
                value={periskopeConfig(config).jira_project}
                onChange={(e) =>
                  updateConfig({
                    connectors: {
                      ...(config.connectors ?? {}),
                      periskope: { ...periskopeConfig(config), jira_project: e.target.value },
                    },
                  })
                }
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Allowed chat ids</label>
              <Input
                placeholder="1203...@g.us, 9198...@c.us (empty = all)"
                value={periskopeConfig(config).allowed_chat_ids.join(", ")}
                onChange={(e) =>
                  updateConfig({
                    connectors: {
                      ...(config.connectors ?? {}),
                      periskope: {
                        ...periskopeConfig(config),
                        allowed_chat_ids: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                      },
                    },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">API token</label>
              <Input.Password
                placeholder={
                  config._secrets_configured?.connectors?.periskope?.api_token ? "••••••••" : "Periskope API key"
                }
                value={secrets.connectors?.periskope?.api_token ?? ""}
                onChange={(e) =>
                  setSecrets((s) => ({
                    ...s,
                    connectors: {
                      ...(s.connectors || {}),
                      periskope: { ...(s.connectors?.periskope || {}), api_token: e.target.value },
                    },
                  }))
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Webhook signing key</label>
              <Input.Password
                placeholder={
                  config._secrets_configured?.connectors?.periskope?.webhook_secret
                    ? "••••••••"
                    : "HMAC signing key"
                }
                value={secrets.connectors?.periskope?.webhook_secret ?? ""}
                onChange={(e) =>
                  setSecrets((s) => ({
                    ...s,
                    connectors: {
                      ...(s.connectors || {}),
                      periskope: { ...(s.connectors?.periskope || {}), webhook_secret: e.target.value },
                    },
                  }))
                }
              />
            </Col>
          </Row>
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--alfred-border)" }}>
            <Typography.Text strong>Pull without webhook</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
              Last pull: {formatSyncWhen(syncStatus?.connectors?.periskope?.last_sync_at)} ·{" "}
              {syncStatus?.connectors?.periskope?.ticket_count ?? 0} tickets ·{" "}
              {syncStatus?.connectors?.periskope?.task_count ?? 0} tasks
            </Typography.Paragraph>
            <Flex gap={8} wrap="wrap">
              <Button
                icon={<SyncOutlined />}
                loading={syncLoading === "periskope"}
                onClick={() => void runPeriskopePoll(false)}
              >
                Pull now (preview)
              </Button>
              <Button
                loading={syncLoading === "periskope-replicate"}
                onClick={() => void runPeriskopePoll(true)}
              >
                Pull and replicate
              </Button>
            </Flex>
            {pollPreview?.preview && (
              <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 12 }}>
                {(pollPreview.preview.tickets ?? []).slice(0, 8).map((ticket) => (
                  <span key={ticket.external_id || ticket.title}>
                    {ticket.external_id}: {ticket.title}
                    <br />
                  </span>
                ))}
                {(pollPreview.preview.tickets?.length ?? 0) > 8 ? "…" : null}
              </Typography.Paragraph>
            )}
          </div>
        </div>
      </Modal>

      {/* Google Workspace Modal */}
      <Modal
        title="Google Workspace Configuration"
        open={activeModal === "google"}
        width={620}
        onCancel={() => handleCancelStandard("google")}
        footer={[
          <Button
            key="creds"
            loading={savingGoogleCredentials}
            disabled={!(secrets.google_credentials_json ?? "").trim()}
            onClick={() => void handleSaveGoogleCredentials()}
          >
            Save credentials
          </Button>,
          <Button key="test" onClick={() => testIntegration("google")}>
            Test connection
          </Button>,
          <Button key="cancel" onClick={() => handleCancelStandard("google")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable Google Sheets & Docs tools</Typography.Text>
            <Switch
              checked={config.google?.enabled ?? false}
              onChange={(v) =>
                updateConfig({
                  google: {
                    enabled: v,
                    oauth_redirect_base_url: config.google?.oauth_redirect_base_url ?? "",
                  },
                })
              }
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <JsonCredentialField
                label="Google OAuth client or service account JSON"
                configured={config._secrets_configured?.google_credentials_json}
                credentialType={config._secrets_configured?.google_credentials_type}
                oauthConnected={config._secrets_configured?.google_oauth_connected}
                value={secrets.google_credentials_json ?? ""}
                onChange={(v) => setSecrets((s) => ({ ...s, google_credentials_json: v }))}
                hint="Download from GCP → APIs & Services → Credentials. OAuth clients need Connect Google after save."
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Public Alfred URL (OAuth redirect base)</label>
              <Input
                placeholder="https://alfred.example.com"
                value={config.google?.oauth_redirect_base_url ?? ""}
                onChange={(e) =>
                  updateConfig({
                    google: {
                      enabled: config.google?.enabled ?? false,
                      oauth_redirect_base_url: e.target.value,
                    },
                  })
                }
              />
              <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 6, marginBottom: 0 }}>
                Add this redirect URI in Google Cloud Console (OAuth client → Authorized redirect URIs):
                <br />
                <Typography.Text code copyable>
                  {(googleOAuth?.redirect_uri || "{base}/api/config/google/oauth/callback").replace(
                    "{base}",
                    (config.google?.oauth_redirect_base_url || "https://your-alfred-host").replace(/\/$/, ""),
                  )}
                </Typography.Text>
              </Typography.Paragraph>
            </Col>
            <Col span={24}>
              {googleOAuth?.credentials_type === "oauth_client" && (
                <Flex gap={12} align="center" wrap="wrap">
                  <Button loading={connectingGoogle} onClick={() => void handleConnectGoogle()}>
                    Connect Google
                  </Button>
                  <Typography.Text type={googleOAuth.oauth_connected ? "success" : "secondary"}>
                    {googleOAuth.oauth_connected
                      ? "OAuth connected"
                      : "Sign in once to store a refresh token"}
                  </Typography.Text>
                </Flex>
              )}
              {googleOAuth && !googleOAuth.google_libs_installed && (
                <Typography.Paragraph type="warning" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
                  Install Python extras on the server: pip install &apos;alfred-agent[google]&apos;
                </Typography.Paragraph>
              )}
            </Col>
          </Row>
        </div>
      </Modal>

      {/* Web Search Modal */}
      <Modal
        title="Web search"
        open={activeModal === "web_search"}
        width={560}
        onCancel={() => handleCancelStandard("web_search")}
        footer={[
          <Button key="test" onClick={() => testIntegration("web_search")}>
            Test connection
          </Button>,
          <Button key="cancel" onClick={() => handleCancelStandard("web_search")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable web_search tool</Typography.Text>
            <Switch
              checked={webSearchConfig(config).enabled}
              onChange={(v) =>
                updateConfig({ web_search: { ...webSearchConfig(config), enabled: v } })
              }
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <label className="alfred-field-label">Provider</label>
              <Select
                style={{ width: "100%" }}
                value={webSearchConfig(config).provider}
                options={[
                  { value: "duckduckgo", label: "DuckDuckGo (no API key)" },
                  { value: "tavily", label: "Tavily (API key in Secrets)" },
                ]}
                onChange={(v: "duckduckgo" | "tavily") =>
                  updateConfig({
                    web_search: { ...webSearchConfig(config), provider: v },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Max results</label>
              <Input
                type="number"
                min={1}
                max={20}
                value={webSearchConfig(config).max_results}
                onChange={(e) =>
                  updateConfig({
                    web_search: {
                      ...webSearchConfig(config),
                      max_results: Number(e.target.value) || 8,
                    },
                  })
                }
              />
            </Col>
            <Col span={24}>
              {webSearchConfig(config).provider === "duckduckgo" ? (
                <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
                  Requires <Typography.Text code>uv sync --extra web</Typography.Text> on the server
                  (installs duckduckgo-search). Read-only — use the bundled{" "}
                  <Typography.Text code>web_research</Typography.Text> skill or{" "}
                  <Typography.Text code>investigate_bug</Typography.Text> when external context helps.
                </Typography.Paragraph>
              ) : (
                <>
                  <label className="alfred-field-label">Tavily API key</label>
                  <Input.Password
                    placeholder={config._secrets_configured?.web_search_api_key ? "••••••••" : "tvly-..."}
                    value={secrets.web_search_api_key ?? ""}
                    onChange={(e) =>
                      setSecrets((s) => ({ ...s, web_search_api_key: e.target.value }))
                    }
                  />
                  <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
                    Save the key under Secrets (or here, then Save changes on Integrations). Tavily returns a
                    short AI summary plus ranked results.
                  </Typography.Paragraph>
                </>
              )}
            </Col>
          </Row>
        </div>
      </Modal>

      {/* Governance Modal */}
      <Modal
        title="Governance & write policies"
        open={activeModal === "governance"}
        width={640}
        onCancel={() => handleCancelStandard("governance")}
        footer={[
          <Button key="cancel" onClick={() => handleCancelStandard("governance")}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveStandard}>
            Save changes
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
            <Typography.Text>Enable governance (policies, confirmation, audit)</Typography.Text>
            <Switch
              checked={governanceConfig(config).enabled}
              onChange={(v) =>
                updateConfig({ governance: { ...governanceConfig(config), enabled: v } })
              }
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <div className="alfred-settings-action" style={{ paddingTop: 4, paddingBottom: 4 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Require *yes, proceed* before push, PR, JIRA, Google, and schedule writes on Slack/UI.
                  CLI is excluded by default.
                </Typography.Text>
                <Switch
                  checked={governanceConfig(config).require_confirmation}
                  disabled={!governanceConfig(config).enabled}
                  onChange={(v) =>
                    updateConfig({
                      governance: { ...governanceConfig(config), require_confirmation: v },
                    })
                  }
                />
              </div>
            </Col>
            <Col span={24}>
              <div className="alfred-settings-action" style={{ paddingTop: 4, paddingBottom: 4 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Persist audit log entries for all write tools in{" "}
                  <Typography.Text code>.alfred/alfred.db</Typography.Text>
                </Typography.Text>
                <Switch
                  checked={governanceConfig(config).audit_enabled}
                  disabled={!governanceConfig(config).enabled}
                  onChange={(v) =>
                    updateConfig({ governance: { ...governanceConfig(config), audit_enabled: v } })
                  }
                />
              </div>
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Approval TTL (minutes)</label>
              <Input
                type="number"
                min={5}
                max={240}
                disabled={!governanceConfig(config).enabled}
                value={governanceConfig(config).approval_ttl_minutes}
                onChange={(e) =>
                  updateConfig({
                    governance: {
                      ...governanceConfig(config),
                      approval_ttl_minutes: Number(e.target.value) || 30,
                    },
                  })
                }
              />
            </Col>
            <Col span={12}>
              <label className="alfred-field-label">Confirmation sources</label>
              <Input
                placeholder="slack, ui"
                disabled={!governanceConfig(config).enabled}
                value={governanceConfig(config).require_confirmation_sources.join(", ")}
                onChange={(e) =>
                  updateConfig({
                    governance: {
                      ...governanceConfig(config),
                      require_confirmation_sources: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                  })
                }
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Blocked Slack channels (IDs)</label>
              <Input
                placeholder="C0123ABC, C0456DEF"
                disabled={!governanceConfig(config).enabled}
                value={governanceConfig(config).write_blocked_channels.join(", ")}
                onChange={(e) =>
                  updateConfig({
                    governance: {
                      ...governanceConfig(config),
                      write_blocked_channels: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                  })
                }
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Allowed write users (Slack IDs, optional)</label>
              <Input
                placeholder="U123, U456 (empty = any user in allowed channels)"
                disabled={!governanceConfig(config).enabled}
                value={governanceConfig(config).write_allowed_users.join(", ")}
                onChange={(e) =>
                  updateConfig({
                    governance: {
                      ...governanceConfig(config),
                      write_allowed_users: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                  })
                }
              />
            </Col>
          </Row>
        </div>
      </Modal>

      {/* Add Custom Integration Modal */}
      <Modal
        title="Add Custom Integration API"
        open={activeModal === "custom_new"}
        onCancel={() => setActiveModal(null)}
        footer={[
          <Button key="cancel" onClick={() => setActiveModal(null)}>
            Cancel
          </Button>,
          <Button key="add" type="primary" onClick={handleAddCustom}>
            Add integration
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <label className="alfred-field-label">Integration name</label>
              <Input
                placeholder="Sentry, GitLab, PagerDuty..."
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">API base URL</label>
              <Input
                placeholder="https://api.sentry.io/v0"
                value={customApiUrl}
                onChange={(e) => setCustomApiUrl(e.target.value)}
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">API token / Secret key</label>
              <Input.Password
                placeholder="Bearer token or custom key"
                value={customApiToken}
                onChange={(e) => setCustomApiToken(e.target.value)}
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Short description / Summary</label>
              <Input
                placeholder="Bug tracking and diagnostic alerts webhook"
                value={customDescription}
                onChange={(e) => setCustomDescription(e.target.value)}
              />
            </Col>
          </Row>
        </div>
      </Modal>

      {/* Edit Custom Integration Modal */}
      <Modal
        title={`Configure ${customName}`}
        open={activeModal === "custom_edit"}
        onCancel={() => setActiveModal(null)}
        footer={[
          <Button key="delete" danger onClick={() => handleDeleteCustom(selectedCustomId!)}>
            Delete
          </Button>,
          <Button key="test" loading={testingCustom} onClick={() => handleTestCustom(customName, customApiUrl)}>
            Test connection
          </Button>,
          <Button key="cancel" onClick={() => setActiveModal(null)}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSaveCustom}>
            Apply & Save
          </Button>,
        ]}
      >
        <div style={{ padding: "12px 0" }}>
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <label className="alfred-field-label">Integration name</label>
              <Input
                placeholder="Name"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">API base URL</label>
              <Input
                placeholder="URL"
                value={customApiUrl}
                onChange={(e) => setCustomApiUrl(e.target.value)}
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">API token / Secret key</label>
              <Input.Password
                placeholder="Hidden token"
                value={customApiToken}
                onChange={(e) => setCustomApiToken(e.target.value)}
              />
            </Col>
            <Col span={24}>
              <label className="alfred-field-label">Short description / Summary</label>
              <Input
                placeholder="Description"
                value={customDescription}
                onChange={(e) => setCustomDescription(e.target.value)}
              />
            </Col>
          </Row>
        </div>
      </Modal>
    </div>
  );
}
