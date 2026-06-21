import { Button, Col, Input, Row, Select, Switch, Typography } from "antd";
import type { ReactNode } from "react";
import { useApp } from "../../context/AppContext";

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
        Connect Slack, Git, and AWS. Toggle each service and verify credentials.
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
              value={config.git.default_org}
              onChange={(e) => updateConfig({ git: { ...config.git, default_org: e.target.value } })}
            />
          </Col>
          <Col xs={24} md={8}>
            <label className="alfred-field-label">Repos</label>
            <Input
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
