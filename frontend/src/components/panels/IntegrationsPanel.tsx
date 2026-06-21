import { ReloadOutlined } from "@ant-design/icons";
import { Button, Col, Flex, Input, Row, Select, Switch, Typography } from "antd";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AlfredConfig } from "../../api/client";
import { useApp } from "../../context/AppContext";

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

function IntegrationBlock({
  title,
  enabled,
  onToggle,
  onTest,
  children,
}: {
  title: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  onTest: () => void;
  children: ReactNode;
}) {
  return (
    <div className="alfred-provider-card">
      <div className="alfred-settings-action" style={{ paddingTop: 0 }}>
        <Typography.Text strong>{title}</Typography.Text>
        <Switch checked={enabled} checkedChildren="on" unCheckedChildren="off" onChange={onToggle} />
      </div>
      {children}
      <Button size="small" style={{ marginTop: 12 }} onClick={onTest}>
        Test connection
      </Button>
    </div>
  );
}

export function IntegrationsPanel() {
  const { config, updateConfig, saveConfig, testIntegration } = useApp();
  const [availableRepos, setAvailableRepos] = useState<string[]>([]);
  const [reposSource, setReposSource] = useState<string>("configured");
  const [reposOrg, setReposOrg] = useState<string | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);
  const [loadingRepos, setLoadingRepos] = useState(false);

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

  if (!config) return null;

  const mainRepoSelectOptions = useMemo(
    () => mainRepoOptions(availableRepos, config.git.main_repo),
    [availableRepos, config.git.main_repo],
  );

  return (
    <div>
      <Typography.Title level={3} className="alfred-page-title">
        Integrations
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Connect Slack, Git, GitHub App, JIRA, and AWS. Toggle each service and verify credentials.
      </Typography.Paragraph>

      <IntegrationBlock
        title="Slack"
        enabled={config.slack.enabled}
        onToggle={(v) => updateConfig({ slack: { ...config.slack, enabled: v } })}
        onTest={() => testIntegration("slack")}
      >
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
      </IntegrationBlock>

      <IntegrationBlock
        title="Git"
        enabled={config.git.enabled}
        onToggle={(v) => updateConfig({ git: { ...config.git, enabled: v } })}
        onTest={() => testIntegration("git")}
      >
        <Row gutter={[12, 12]}>
          <Col xs={24} md={8}>
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
          <Col xs={24} md={8}>
            <label className="alfred-field-label">Org</label>
            <Input
              placeholder="YourOrg"
              value={config.git.default_org}
              onChange={(e) => updateConfig({ git: { ...config.git, default_org: e.target.value } })}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Short repo names (e.g. backend) resolve to Org/backend.
            </Typography.Text>
          </Col>
          <Col xs={24} md={8}>
            <label className="alfred-field-label">Repos</label>
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
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Main repo</label>
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
                aria-label="Reload repos from org"
              />
            </Flex>
            <Typography.Text type="secondary" style={{ fontSize: 12, display: "block" }}>
              {mainRepoSourceLabel(reposSource, reposOrg)}
            </Typography.Text>
            {reposError ? (
              <Typography.Text type="warning" style={{ fontSize: 12, display: "block" }}>
                {reposError}
              </Typography.Text>
            ) : null}
            <Typography.Text type="secondary" style={{ fontSize: 12, display: "block" }}>
              Default codebase for context and investigation. Sync under Repo mirrors.
            </Typography.Text>
          </Col>
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Graphify</label>
            <div className="alfred-settings-action" style={{ paddingTop: 4 }}>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                Build knowledge graphs on sync; enables <Typography.Text code>query_graph</Typography.Text>.
                Install once: <Typography.Text code>uv sync --extra graphify</Typography.Text>
              </Typography.Text>
              <Switch
                checked={Boolean(config.git.graphify_enabled)}
                checkedChildren="on"
                unCheckedChildren="off"
                onChange={(v) =>
                  updateConfig({ git: { ...config.git, graphify_enabled: v } })
                }
              />
            </div>
          </Col>
        </Row>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          Manage local repo checkouts under Configure → Repo mirrors.
        </Typography.Paragraph>
      </IntegrationBlock>

      <div className="alfred-provider-card">
        <div className="alfred-settings-action" style={{ paddingTop: 0 }}>
          <Typography.Text strong>GitHub App</Typography.Text>
          <Switch
            checked={githubConfig(config).enabled}
            checkedChildren="on"
            unCheckedChildren="off"
            onChange={(v) =>
              updateConfig({ github: { ...githubConfig(config), enabled: v } })
            }
          />
        </div>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 13 }}>
          PR comment bot — comment <Typography.Text code>@alfred review</Typography.Text> on a pull
          request. Requires public HTTPS (tunnel) plus webhook secret in Secrets.
        </Typography.Paragraph>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12}>
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
          <Col xs={24} md={12}>
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
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Bot login (optional)</label>
            <Input
              placeholder="alfred"
              value={githubConfig(config).bot_login}
              onChange={(e) =>
                updateConfig({
                  github: { ...githubConfig(config), bot_login: e.target.value },
                })
              }
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              GitHub App slug for @mentions (default <Typography.Text code>alfred</Typography.Text>). Must match your app name on GitHub.
            </Typography.Text>
          </Col>
          <Col xs={24} md={12}>
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
          <Col xs={24}>
            <label className="alfred-field-label">Allowed repos (optional)</label>
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
          <div style={{ marginTop: 12 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12, display: "block" }}>
              Paste these into your GitHub App settings:
            </Typography.Text>
            <Typography.Paragraph style={{ marginBottom: 4, fontSize: 13 }}>
              Webhook:{" "}
              <Typography.Text code copyable>
                {githubUrls(githubConfig(config).callback_base_url)!.webhook}
              </Typography.Text>
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, fontSize: 13 }}>
              Callback:{" "}
              <Typography.Text code copyable>
                {githubUrls(githubConfig(config).callback_base_url)!.callback}
              </Typography.Text>
            </Typography.Paragraph>
          </div>
        )}
      </div>

      <IntegrationBlock
        title="AWS"
        enabled={config.aws.enabled}
        onToggle={(v) => updateConfig({ aws: { ...config.aws, enabled: v } })}
        onTest={() => testIntegration("aws")}
      >
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Profile</label>
            <Input
              value={config.aws.profile}
              onChange={(e) => updateConfig({ aws: { ...config.aws, profile: e.target.value } })}
            />
          </Col>
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Region</label>
            <Input
              value={config.aws.region}
              onChange={(e) => updateConfig({ aws: { ...config.aws, region: e.target.value } })}
            />
          </Col>
        </Row>
      </IntegrationBlock>

      <IntegrationBlock
        title="JIRA"
        enabled={config.jira?.enabled ?? false}
        onToggle={(v) =>
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
        onTest={() => testIntegration("jira")}
      >
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Site URL</label>
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
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Account email</label>
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
          <Col xs={24} md={8}>
            <label className="alfred-field-label">Default project</label>
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
          <Col xs={24} md={16}>
            <label className="alfred-field-label">Allowed projects</label>
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
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0, fontSize: 13 }}>
          Alfred can list tickets, change status, comment, and link GitHub PRs. Add your API token in Secrets.
        </Typography.Paragraph>
      </IntegrationBlock>

      <Button type="primary" onClick={saveConfig}>
        Save changes
      </Button>
    </div>
  );
}
