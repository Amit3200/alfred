import { ToolOutlined } from "@ant-design/icons";
import {
  Alert,
  Input,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { Table } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ToolCatalogEntry, type ToolsCatalogResponse } from "../../api/client";
import { useApp } from "../../context/AppContext";

const GOVERNANCE_COLORS: Record<string, string> = {
  read: "default",
  staging: "orange",
  confirm: "red",
  write: "volcano",
};

function governanceLabel(level: string): string {
  switch (level) {
    case "confirm":
      return "Confirm required";
    case "staging":
      return "Write (staging)";
    case "write":
      return "Write";
    default:
      return "Read-only";
  }
}

export function ToolsPanel() {
  const { notify } = useApp();
  const [catalog, setCatalog] = useState<ToolsCatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState<string | "all">("all");
  const [enabledFilter, setEnabledFilter] = useState<"all" | "enabled" | "disabled">("all");

  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getToolsCatalog();
      setCatalog(res);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", `Failed to load tools: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const filteredTools = useMemo(() => {
    const tools = catalog?.tools ?? [];
    const q = search.trim().toLowerCase();
    return tools.filter((t) => {
      if (domainFilter !== "all" && t.domain !== domainFilter) return false;
      if (enabledFilter === "enabled" && !t.enabled) return false;
      if (enabledFilter === "disabled" && t.enabled) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.domain.toLowerCase().includes(q) ||
        (t.skills || []).some((s) => s.toLowerCase().includes(q))
      );
    });
  }, [catalog, search, domainFilter, enabledFilter]);

  const domainOptions = useMemo(
    () =>
      (catalog?.domains ?? []).map((d) => ({
        value: d.name,
        label: `${d.label} (${d.enabled_count}/${d.tool_count})`,
      })),
    [catalog],
  );

  const columns: ColumnsType<ToolCatalogEntry> = [
    {
      title: "Tool",
      dataIndex: "name",
      key: "name",
      render: (name: string) => <Typography.Text code>{name}</Typography.Text>,
      sorter: (a, b) => a.name.localeCompare(b.name),
    },
    {
      title: "Domain",
      dataIndex: "domain_label",
      key: "domain",
      width: 160,
      filters: domainOptions.map((d) => ({ text: d.label, value: d.value })),
      onFilter: (value, record) => record.domain === value,
    },
    {
      title: "Status",
      dataIndex: "enabled",
      key: "enabled",
      width: 100,
      render: (enabled: boolean) =>
        enabled ? <Tag color="success">Enabled</Tag> : <Tag>Disabled</Tag>,
    },
    {
      title: "Access",
      dataIndex: "governance",
      key: "governance",
      width: 140,
      render: (gov: string) => (
        <Tag color={GOVERNANCE_COLORS[gov] || "default"}>{governanceLabel(gov)}</Tag>
      ),
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      ellipsis: true,
    },
    {
      title: "Skills",
      dataIndex: "skills",
      key: "skills",
      width: 200,
      render: (skills: string[]) =>
        skills?.length ? (
          <Space size={[4, 4]} wrap>
            {skills.map((s) => (
              <Tag key={s}>{s}</Tag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: "Requires",
      dataIndex: "integration",
      key: "integration",
      width: 180,
      render: (text: string, row) =>
        row.enabled ? (
          <Typography.Text type="secondary">—</Typography.Text>
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {text}
          </Typography.Text>
        ),
    },
  ];

  const summary = catalog?.summary;

  return (
    <div className="alfred-panel">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            <ToolOutlined style={{ marginRight: 8 }} />
            Tools
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 8 }}>
            All agent tools Alfred can register. Enable integrations in{" "}
            <Typography.Text strong>Integrations</Typography.Text>; scope tools per skill in{" "}
            <Typography.Text strong>Playbooks</Typography.Text>. The tool planner narrows the
            allowlist each turn.
          </Typography.Paragraph>
        </div>

        {summary && (
          <Space size="large" wrap>
            <Statistic title="Total tools" value={summary.total} />
            <Statistic title="Enabled" value={summary.enabled} valueStyle={{ color: "#3f8600" }} />
            <Statistic title="Disabled" value={summary.disabled} />
            <Statistic title="Write tools" value={summary.write_tools} />
            <Statistic title="Domains" value={summary.domain_count} />
          </Space>
        )}

        <Alert
          type="info"
          showIcon
          message="Domain grouping"
          description={
            <>
              Tools like <Typography.Text code>grep_repo</Typography.Text> and{" "}
              <Typography.Text code>read_file</Typography.Text> appear under{" "}
              <strong>Git & repository</strong> because they operate on mirrored repos. Doc search
              tools are under <strong>Repo documentation</strong>. Schedules and company scripts
              are always available when scripts are enabled.
            </>
          }
        />

        <Space wrap style={{ width: "100%" }}>
          <Input.Search
            placeholder="Search tools, skills, descriptions…"
            allowClear
            style={{ minWidth: 280, maxWidth: 400 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            style={{ minWidth: 200 }}
            value={domainFilter}
            onChange={setDomainFilter}
            options={[{ value: "all", label: "All domains" }, ...domainOptions]}
          />
          <Select
            style={{ minWidth: 140 }}
            value={enabledFilter}
            onChange={setEnabledFilter}
            options={[
              { value: "all", label: "All status" },
              { value: "enabled", label: "Enabled only" },
              { value: "disabled", label: "Disabled only" },
            ]}
          />
        </Space>

        <Table
          rowKey="name"
          loading={loading}
          dataSource={filteredTools}
          columns={columns}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          size="middle"
        />
      </Space>
    </div>
  );
}
