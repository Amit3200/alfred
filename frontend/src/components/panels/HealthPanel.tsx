import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Descriptions, Flex, Popconfirm, Space, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, type DbStatsResponse } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { summarizeHealth } from "../../health";
import { HealthChecksTable } from "../HealthChecksTable";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatWhen(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export function HealthPanel() {
  const { checks, runChecks, notify } = useApp();
  const healthSummary = summarizeHealth(checks);
  const [dbStats, setDbStats] = useState<DbStatsResponse | null>(null);
  const [dbLoading, setDbLoading] = useState(true);
  const [cleaning, setCleaning] = useState<string | null>(null);

  const loadDbStats = useCallback(async () => {
    setDbLoading(true);
    try {
      const stats = await api.getDbStats();
      setDbStats(stats);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load database stats");
      setDbStats(null);
    } finally {
      setDbLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    loadDbStats();
  }, [loadDbStats]);

  const runCleanup = async (
    key: string,
    scope: "observability" | "sessions" | "slack_cache" | "all",
    olderThanDays?: number,
  ) => {
    setCleaning(key);
    try {
      const result = await api.cleanupDb({
        scope,
        older_than_days: olderThanDays ?? null,
        vacuum: true,
      });
      setDbStats(result.stats);
      const total =
        result.removed.interaction_events +
        result.removed.conversation_sessions +
        result.removed.slack_user_names;
      notify(
        "success",
        total
          ? `Removed ${total} row(s). Database is now ${formatBytes(result.stats.size_bytes)}.`
          : "Nothing to remove.",
      );
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Database cleanup failed");
    } finally {
      setCleaning(null);
    }
  };

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        Health
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Verify connectivity to Slack, Git, JIRA, AWS, Google Workspace, web search, and your configured
        AI provider. Integration cards reflect the latest check results after you run checks here or from
        Integrations → Test connection.
      </Typography.Paragraph>

      <div className="alfred-panel" style={{ marginBottom: 20 }}>
        <Flex vertical gap={16}>
          <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
            <Typography.Text type={healthSummary.failed > 0 ? "danger" : "secondary"}>
              {healthSummary.headline}
              {healthSummary.total > 0
                ? ` · ${healthSummary.ok}/${healthSummary.total} passing`
                : ""}
            </Typography.Text>
            <Button type="primary" onClick={runChecks}>
              Run all checks
            </Button>
          </Flex>

          {!checks ? (
            <Typography.Text type="secondary">No checks run yet.</Typography.Text>
          ) : (
            <HealthChecksTable checks={checks} />
          )}
        </Flex>
      </div>

      <Typography.Title level={5}>Local database</Typography.Title>
      <div className="alfred-panel">
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 12 }}>
          Alfred stores chat sessions, usage telemetry, and Slack display-name cache in{" "}
          <Typography.Text code>.alfred/alfred.db</Typography.Text>. Usage events are the main
          growth driver — safe to trim if the Configure → Usage page feels slow.
        </Typography.Paragraph>

        {dbStats ? (
          <Descriptions size="small" column={1} bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label="File">
              {dbStats.rel_path ?? dbStats.path} · {formatBytes(dbStats.size_bytes)}
            </Descriptions.Item>
            <Descriptions.Item label="Usage events">
              {dbStats.tables.interaction_events.rows} rows
              {dbStats.tables.interaction_events.newest
                ? ` · latest ${formatWhen(dbStats.tables.interaction_events.newest)}`
                : ""}
            </Descriptions.Item>
            <Descriptions.Item label="Chat sessions">
              {dbStats.tables.conversation_sessions.rows} rows
            </Descriptions.Item>
            <Descriptions.Item label="Slack name cache">
              {dbStats.tables.slack_user_names.rows} rows
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
            {dbLoading ? "Loading database stats…" : "Could not load database stats."}
          </Typography.Text>
        )}

        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={loadDbStats} loading={dbLoading}>
            Refresh
          </Button>
          <Popconfirm
            title="Delete usage events older than 30 days?"
            onConfirm={() => runCleanup("usage-30d", "observability", 30)}
          >
            <Button loading={cleaning === "usage-30d"}>
              Trim usage (&gt;30 days)
            </Button>
          </Popconfirm>
          <Popconfirm
            title="Delete all usage / observability events?"
            onConfirm={() => runCleanup("usage-all", "observability")}
          >
            <Button loading={cleaning === "usage-all"}>Clear all usage data</Button>
          </Popconfirm>
          <Popconfirm
            title="Delete all stored chat session history?"
            onConfirm={() => runCleanup("sessions", "sessions")}
          >
            <Button loading={cleaning === "sessions"}>Clear chat sessions</Button>
          </Popconfirm>
          <Popconfirm
            title="Clear Slack display-name cache?"
            onConfirm={() => runCleanup("slack", "slack_cache")}
          >
            <Button loading={cleaning === "slack"}>Clear Slack cache</Button>
          </Popconfirm>
          <Popconfirm
            title="Delete usage events, chat sessions, and Slack cache?"
            onConfirm={() => runCleanup("all", "all")}
          >
            <Button danger icon={<DeleteOutlined />} loading={cleaning === "all"}>
              Clear all local DB data
            </Button>
          </Popconfirm>
        </Space>
      </div>
    </div>
  );
}
