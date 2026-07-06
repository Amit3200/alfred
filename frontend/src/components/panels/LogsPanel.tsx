import {
  CopyOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Button,
  Empty,
  Flex,
  Input,
  Radio,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useState, useCallback } from "react";
import { api, type LogEvent } from "../../api/client";
import { useApp } from "../../context/AppContext";

export function LogsPanel() {
  const { notify } = useApp();
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<"all" | "slack" | "git" | "system">("all");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchLogs = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const res = await api.getLogs(search || undefined);
      setLogs(res.logs || []);
    } catch (err: any) {
      notify("error", `Failed to fetch logs: ${err.message || err}`);
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [search, notify]);

  // Initial load and debounced search fetch
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchLogs(true);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, fetchLogs]);

  // Auto-refresh interval (every 10 seconds)
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchLogs(false);
    }, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchLogs]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success("Copied to clipboard!");
  };

  const handleBulkCopy = () => {
    const text = filteredLogs
      .map((log) => `[${log.timestamp || "TRACEBACK"}] [${log.level}] [${log.module}] ${log.message}`)
      .join("\n");
    if (!text) {
      message.warning("No logs to copy");
      return;
    }
    copyToClipboard(text);
  };

  // Filter logs by selected tab category
  const filteredLogs = logs.filter((log) => {
    if (category === "all") return true;
    return log.category === category;
  });

  const getLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case "ERROR":
      case "CRITICAL":
        return "error";
      case "WARNING":
        return "warning";
      case "INFO":
        return "processing";
      case "DEBUG":
      default:
        return "default";
    }
  };

  const columns = [
    {
      title: "Timestamp",
      dataIndex: "timestamp",
      key: "timestamp",
      width: 170,
      render: (text: string) => (
        <Typography.Text type="secondary" style={{ fontSize: "12px", fontFamily: "monospace" }}>
          {text || "—"}
        </Typography.Text>
      ),
    },
    {
      title: "Level",
      dataIndex: "level",
      key: "level",
      width: 90,
      align: "center" as const,
      render: (text: string) => (
        <Tag color={getLevelColor(text)} style={{ fontWeight: "bold" }}>
          {text}
        </Tag>
      ),
    },
    {
      title: "Module",
      dataIndex: "module",
      key: "module",
      width: 180,
      ellipsis: true,
      render: (text: string) => (
        <Typography.Text code style={{ fontSize: "11px" }}>
          {text}
        </Typography.Text>
      ),
    },
    {
      title: "Message",
      dataIndex: "message",
      key: "message",
      render: (text: string) => (
        <Typography.Paragraph
          style={{
            margin: 0,
            fontFamily: "monospace",
            fontSize: "12px",
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
            color: "var(--alfred-text)",
          }}
        >
          {text}
        </Typography.Paragraph>
      ),
    },
    {
      title: "",
      key: "action",
      width: 60,
      align: "center" as const,
      render: (record: LogEvent) => (
        <Button
          type="text"
          icon={<CopyOutlined />}
          size="small"
          onClick={() =>
            copyToClipboard(`[${record.timestamp}] [${record.level}] [${record.module}] ${record.message}`)
          }
          title="Copy log line"
        />
      ),
    },
  ];

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        Server Logs & Events
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Inspect live server logs and exceptions from Slack events, Git reviews, scheduler runs, and internal tasks.
      </Typography.Paragraph>

      <div className="alfred-panel">
        <Flex vertical gap={18} style={{ marginBottom: "20px" }}>
          {/* Controls Bar */}
          <Flex wrap="wrap" justify="space-between" align="center" gap={12}>
            {/* Search and Tabs */}
            <Flex align="center" gap={12} wrap="wrap" style={{ flexGrow: 1, maxWidth: "600px" }}>
              <Input
                placeholder="Search module or message..."
                prefix={<SearchOutlined style={{ color: "var(--alfred-text-muted)" }} />}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ width: "230px" }}
                allowClear
              />
              <Radio.Group
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                optionType="button"
                buttonStyle="solid"
              >
                <Radio.Button value="all">All</Radio.Button>
                <Radio.Button value="slack">Slack Calls</Radio.Button>
                <Radio.Button value="git">Git Calls</Radio.Button>
                <Radio.Button value="system">System</Radio.Button>
              </Radio.Group>
            </Flex>

            {/* Auto Refresh, Copy and Refresh Action buttons */}
            <Space size="middle">
              <Space size="small">
                <Typography.Text type="secondary" style={{ fontSize: "13px" }}>
                  Auto-refresh (10s)
                </Typography.Text>
                <Switch
                  checked={autoRefresh}
                  onChange={(checked) => setAutoRefresh(checked)}
                  size="small"
                />
              </Space>
              <Button icon={<CopyOutlined />} onClick={handleBulkCopy}>
                Copy Visible Logs
              </Button>
              <Button
                type="primary"
                icon={<SyncOutlined spin={loading} />}
                onClick={() => fetchLogs(true)}
              >
                Refresh
              </Button>
            </Space>
          </Flex>
        </Flex>

        <Table
          dataSource={filteredLogs}
          columns={columns}
          rowKey={(record, index) => `${record.timestamp}-${record.module}-${index}`}
          loading={loading}
          locale={{
            emptyText: (
              <Empty
                description="No matching log records found"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
          pagination={{ pageSize: 25, size: "small" }}
          style={{ width: "100%" }}
        />
      </div>
    </div>
  );
}
