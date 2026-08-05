import { NodeIndexOutlined } from "@ant-design/icons";
import { Alert, Collapse, Space, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Table } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, type RoutingTraceRecord } from "../../api/client";
import { useApp } from "../../context/AppContext";

function strategyColor(strategy: string): string {
  switch (strategy) {
    case "plan_template":
      return "purple";
    case "rules":
      return "blue";
    case "llm":
      return "orange";
    case "langgraph":
      return "green";
    default:
      return "default";
  }
}

export function RoutingPanel() {
  const { notify } = useApp();
  const [traces, setTraces] = useState<RoutingTraceRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTraces = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getRoutingTraces(50);
      setTraces(res.traces);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", `Failed to load routing traces: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    fetchTraces();
  }, [fetchTraces]);

  const columns: ColumnsType<RoutingTraceRecord> = [
    {
      title: "Time",
      dataIndex: "recorded_at",
      width: 180,
      render: (v: string) => (v ? new Date(v).toLocaleString() : "—"),
    },
    {
      title: "Intent",
      dataIndex: "intent",
      ellipsis: true,
    },
    {
      title: "Skill",
      dataIndex: "skill_name",
      width: 140,
      render: (v: string) => v || "—",
    },
    {
      title: "Strategy",
      dataIndex: "routing_strategy",
      width: 120,
      render: (v: string) => <Tag color={strategyColor(v)}>{v || "—"}</Tag>,
    },
    {
      title: "Route",
      dataIndex: "graph_route",
      width: 90,
      render: (v: string) => v || "—",
    },
    {
      title: "Grounded",
      dataIndex: "grounding_passed",
      width: 90,
      render: (v: boolean) => (
        <Tag color={v ? "success" : "error"}>{v ? "yes" : "no"}</Tag>
      ),
    },
  ];

  return (
    <div className="alfred-panel">
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            <NodeIndexOutlined /> Routing debugger
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            Recent intent → tool plan → skill → LangGraph execution traces. Plan-first routing
            and plan templates replace keyword skill matching for investigations.
          </Typography.Paragraph>
        </div>

        <Alert
          type="info"
          showIcon
          message="Phrase routing is off by default"
          description="Set routing.phrase_routing_enabled: true in config to re-enable keyword/heuristic/BM25 investigation routing."
        />

        <Table
          rowKey="task_id"
          loading={loading}
          columns={columns}
          dataSource={traces}
          pagination={{ pageSize: 15 }}
          expandable={{
            expandedRowRender: (record) => (
              <Collapse
                size="small"
                items={[
                  {
                    key: "plan",
                    label: "Tool plan",
                    children: (
                      <pre style={{ margin: 0, fontSize: 12 }}>
                        {JSON.stringify(record.tool_plan, null, 2) || "—"}
                      </pre>
                    ),
                  },
                  {
                    key: "tools",
                    label: `Scoped tools (${record.scoped_tools?.length ?? 0})`,
                    children: (
                      <Typography.Text code>
                        {(record.scoped_tools || []).join(", ") || "—"}
                      </Typography.Text>
                    ),
                  },
                  {
                    key: "steps",
                    label: `Graph steps (${record.steps?.length ?? 0})`,
                    children: (
                      <pre style={{ margin: 0, fontSize: 12 }}>
                        {JSON.stringify(record.steps, null, 2) || "—"}
                      </pre>
                    ),
                  },
                  {
                    key: "trace",
                    label: `Tool trace (${record.tool_trace?.length ?? 0})`,
                    children: (
                      <pre style={{ margin: 0, fontSize: 12, maxHeight: 240, overflow: "auto" }}>
                        {JSON.stringify(record.tool_trace, null, 2) || "—"}
                      </pre>
                    ),
                  },
                ]}
              />
            ),
          }}
        />
      </Space>
    </div>
  );
}
