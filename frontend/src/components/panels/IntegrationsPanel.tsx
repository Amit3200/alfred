import { Button, Col, Input, Row, Select, Switch, Typography } from "antd";
import type { ReactNode } from "react";
import { useApp } from "../../context/AppContext";
import type { AlfredConfig } from "../../api/client";

const DEFAULT_GITHUB: AlfredConfig["github"] = {
  enabled: false,
  client_id: "",
  app_id: "",
  bot_login: "",
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
  if (!config) return null;

  return (
    <div>
      <Typography.Title level={3} className="alfred-page-title">
        Integrations
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Connect Slack, Git, GitHub App, and AWS. Toggle each service and verify credentials.
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
              placeholder="alfred-flx"
              value={githubConfig(config).bot_login}
              onChange={(e) =>
                updateConfig({
                  github: { ...githubConfig(config), bot_login: e.target.value },
                })
              }
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              App slug for @mentions (e.g. alfred-flx) and to ignore bot comment loops.
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

      <Button type="primary" onClick={saveConfig}>
        Save changes
      </Button>
    </div>
  );
}
