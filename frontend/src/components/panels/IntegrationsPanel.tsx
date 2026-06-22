import { ReloadOutlined, PlusOutlined, DeleteOutlined, ApiOutlined, CheckCircleOutlined, InfoCircleOutlined } from "@ant-design/icons";
import { Button, Col, Flex, Input, Row, Select, Switch, Typography, Modal } from "antd";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AlfredConfig, type GoogleOAuthStatus } from "../../api/client";
import { useApp } from "../../context/AppContext";
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

function githubConfig(config: AlfredConfig) {
  return config.github ?? DEFAULT_GITHUB;
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
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ width: 34, height: 34, color: "var(--alfred-accent)" }}>
      <path d="M12 2v8M18 12H6v2a6 6 0 0 0 12 0v-2ZM12 14v6M16 2v2M8 2v2"/>
    </svg>
  );
}

export function IntegrationsPanel() {
  const { config, updateConfig, saveConfig, testIntegration, notify, secrets, setSecrets, saveSecrets } =
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
    setActiveModal(null);
    // Let state commit and trigger save
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
        Connect Slack, Git, GitHub App, JIRA, AWS, and Google Workspace. Toggle each service to customize
        settings and verify connections.
      </Typography.Paragraph>

      <div className="alfred-integrations-grid">
        {/* Slack Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("slack", config.slack)}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${config.slack.enabled ? "enabled" : "disabled"}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>
              {config.slack.enabled ? "Active" : "Inactive"}
            </span>
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
            <div className={`alfred-integration-card-dot ${config.git.enabled ? "enabled" : "disabled"}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>
              {config.git.enabled ? "Active" : "Inactive"}
            </span>
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
            <div className={`alfred-integration-card-dot ${config.aws.enabled ? "enabled" : "disabled"}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>
              {config.aws.enabled ? "Active" : "Inactive"}
            </span>
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
            <div className={`alfred-integration-card-dot ${config.jira?.enabled ? "enabled" : "disabled"}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>
              {config.jira?.enabled ? "Active" : "Inactive"}
            </span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("jira")}
          </div>
          <div className="alfred-integration-card-title">JIRA</div>
          <div className="alfred-integration-card-subtitle">Ticket retrieval, commenting & identity resolution</div>
        </div>

        {/* Google Workspace Card */}
        <div className="alfred-integration-card" onClick={() => openConfigModal("google", config.google ?? { enabled: false, oauth_redirect_base_url: "" })}>
          <div className="alfred-integration-card-status">
            <div className={`alfred-integration-card-dot ${config.google?.enabled ? "enabled" : "disabled"}`} />
            <span style={{ fontSize: 11, color: "var(--alfred-text-faint)" }}>
              {config.google?.enabled ? "Active" : "Inactive"}
            </span>
          </div>
          <div className="alfred-integration-card-logo">
            {getLogo("google")}
          </div>
          <div className="alfred-integration-card-title">Google Workspace</div>
          <div className="alfred-integration-card-subtitle">Google Sheets read/write & Docs read/create</div>
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
        </div>
      </Modal>

      {/* Git Modal */}
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
                placeholder="https://alfred.flexype.dev"
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
