import {
  ApiOutlined,
  ArrowRightOutlined,
  DownloadOutlined,
  KeyOutlined,
  ReloadOutlined,
  RobotOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Button, Flex, Input, Modal, Spin, Typography, Upload } from "antd";
import { AlfredMark } from "./AlfredMark";
import { HealthChecksTable } from "./HealthChecksTable";
import { OllamaGetStarted } from "./OllamaGetStarted";
import { useApp } from "../context/AppContext";
import { api } from "../api/client";
import { summarizeHealth } from "../health";

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
    refreshBranding,
    runChecks,
    checks,
    notify,
  } = useApp();

  const onExportConfig = async () => {
    try {
      const blob = await api.exportConfig();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "alfred-config.zip";
      a.click();
      URL.revokeObjectURL(url);
      notify("success", "Configuration and secrets exported successfully.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Export failed");
    }
  };

  const onImportConfig = (file: File) => {
    Modal.confirm({
      title: "Import configuration?",
      content:
        "This replaces config, secrets, encryption key, playbooks, and branding on this server with the contents of the zip. This cannot be undone.",
      okText: "Import",
      okType: "danger",
      cancelText: "Cancel",
      onOk: async () => {
        try {
          const result = await api.importConfig(file);
          await load();
          await refreshBranding();
          const count = result.imported_files?.length ?? 0;
          notify("success", `Imported ${count} file${count === 1 ? "" : "s"} successfully.`);
        } catch (err) {
          notify("error", err instanceof Error ? err.message : "Import failed");
          throw err;
        }
      },
    });
    return false;
  };

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
    configured?.jira_api_token,
    configured?.aws_access_key_id,
    configured?.google_credentials_json,
    configured?.web_search_api_key,
    configured?.server_admin_token,
    Object.values(configured?.ai_api_keys || {}).some(Boolean),
  ].filter(Boolean).length;
  const healthSummary = summarizeHealth(checks);
  const statusClass =
    healthSummary.failed > 0
      ? "alfred-status-warn"
      : healthSummary.total > 0
        ? "alfred-status-ok"
        : "alfred-status-ok";

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
          <div className={`alfred-stat-value ${statusClass}`}>{healthSummary.headline}</div>
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
          <div className="alfred-stat-value">{secretsCount} configured</div>
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
            <div style={{ marginTop: 12, borderTop: "1px solid var(--alfred-border-subtle)", paddingTop: 12 }}>
              <Flex gap={8} wrap="wrap">
                <Button
                  type="default"
                  icon={<DownloadOutlined />}
                  onClick={onExportConfig}
                  disabled={!tokenInput}
                >
                  Export Config (.zip)
                </Button>
                <Upload
                  accept=".zip,application/zip"
                  showUploadList={false}
                  beforeUpload={(file) => onImportConfig(file)}
                  disabled={!tokenInput}
                >
                  <Button type="default" icon={<UploadOutlined />} disabled={!tokenInput}>
                    Import Config (.zip)
                  </Button>
                </Upload>
              </Flex>
            </div>
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
                Run checks to verify Slack, Git, JIRA, AWS, Google, web search, and AI connectivity.
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
