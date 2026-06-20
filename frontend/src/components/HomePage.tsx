import {
  ApiOutlined,
  ArrowRightOutlined,
  KeyOutlined,
  ReloadOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { Button, Flex, Input, Spin, Typography } from "antd";
import { AlfredMark } from "./AlfredMark";
import { HealthChecksTable } from "./HealthChecksTable";
import { OllamaGetStarted } from "./OllamaGetStarted";
import { useApp } from "../context/AppContext";

export function HomePage() {
  const {
    config,
    loading,
    initialized,
    version,
    tokenInput,
    setTokenInput,
    saveToken,
    navigate,
    load,
    runChecks,
    checks,
  } = useApp();

  if (loading) {
    return (
      <Flex justify="center" align="center" style={{ minHeight: 360 }}>
        <Spin size="large" />
      </Flex>
    );
  }

  if (!initialized || !config) {
    return (
      <div className="alfred-content-grid">
        <div className="alfred-span-8">
          <Typography.Title level={1} className="alfred-page-title">
            Welcome
          </Typography.Title>
          <div className="alfred-panel">
            <Typography.Paragraph style={{ marginBottom: 16, fontSize: 15 }}>
              Alfred is not initialized on this server. Run{" "}
              <Typography.Text code>alfred init</Typography.Text> in your terminal, then refresh.
            </Typography.Paragraph>
            <Button type="primary" icon={<ReloadOutlined />} onClick={load}>
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const configured = config._secrets_configured;
  const secretsCount = [
    configured?.slack_bot_token,
    configured?.git_token,
    configured?.server_admin_token,
    Object.values(configured?.ai_api_keys || {}).some(Boolean),
  ].filter(Boolean).length;

  return (
    <div>
      <div className="alfred-home-grid">
        <div className="alfred-home-hero">
          <h1>Commands in Slack. Actions in your stack.</h1>
          <p className="alfred-home-hero-lead">
            Alfred connects to Slack, Git, and AWS — picks the right skill, runs the work, and
            replies in thread. Configure once, then @mention it from your team channel.
          </p>
          <div className="alfred-quick-actions">
            <Button type="primary" icon={<RobotOutlined />} onClick={() => navigate("settings", "ai")}>
              Configure AI
            </Button>
            <Button icon={<KeyOutlined />} onClick={() => navigate("settings", "secrets")}>
              Secrets
            </Button>
            <Button icon={<ApiOutlined />} onClick={() => navigate("settings", "integrations")}>
              Integrations
            </Button>
          </div>
        </div>

        <div className="alfred-home-visual">
          <AlfredMark size={96} className="alfred-home-visual-mark" />
          <span className="alfred-home-visual-caption">At your service</span>
        </div>
      </div>

      <div className="alfred-stat-grid">
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">Status</div>
          <div className="alfred-stat-value alfred-status-ok">Ready</div>
        </div>
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">Version</div>
          <div className="alfred-stat-value">v{version}</div>
        </div>
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">Default AI</div>
          <div className="alfred-stat-value" style={{ textTransform: "capitalize" }}>
            {config.ai.default_provider}
          </div>
        </div>
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">Secrets</div>
          <div className="alfred-stat-value">{secretsCount} / 4</div>
        </div>
      </div>

      <div className="alfred-content-grid" style={{ marginTop: 16 }}>
        <div className="alfred-span-12">
          <OllamaGetStarted />
        </div>
      </div>

      <div className="alfred-content-grid" style={{ marginTop: 16 }}>
        <div className="alfred-span-6">
          <div className="alfred-panel">
            <div className="alfred-section-title">Admin access</div>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 16, fontSize: 14 }}>
              Paste the token from <Typography.Text code>alfred token</Typography.Text> (run in the
              project directory) to save configuration and secrets.
            </Typography.Paragraph>
            <Flex gap={10} wrap="wrap">
              <Input.Password
                placeholder="Admin token"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                style={{ flex: 1, minWidth: 200 }}
              />
              <Button type="primary" onClick={saveToken}>
                Save token
              </Button>
            </Flex>
          </div>
        </div>

        <div className="alfred-span-6">
          <div className="alfred-panel">
            <Flex justify="space-between" align="center" style={{ marginBottom: 14 }}>
              <div className="alfred-section-title" style={{ marginBottom: 0 }}>
                Health
              </div>
              <Button size="small" onClick={runChecks}>
                Run checks
              </Button>
            </Flex>
            {!checks ? (
              <Typography.Text type="secondary" style={{ fontSize: 14 }}>
                Test Slack, Git, AWS, and AI connectivity.
              </Typography.Text>
            ) : (
              <HealthChecksTable checks={checks} compact />
            )}
            <Button
              type="link"
              icon={<ArrowRightOutlined />}
              onClick={() => navigate("settings", "health")}
              style={{ paddingLeft: 0, marginTop: 14, color: "var(--alfred-accent)" }}
            >
              Full health panel
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
