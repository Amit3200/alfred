import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Button,
  Descriptions,
  Flex,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ContextSuggestion,
  type GitMirrorCleanupScope,
  type GitMirrorsResponse,
  type GitMirrorWorkspace,
  type GraphifyDetailResponse,
  type GraphifySummary,
  type RepoContextStatus,
} from "../../api/client";
import { useApp } from "../../context/AppContext";
import { ChatMarkdown } from "../ChatMarkdown";

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

export function RepoMirrorsPanel() {
  const { notify } = useApp();
  const [data, setData] = useState<GitMirrorsResponse | null>(null);
  const [contextStatus, setContextStatus] = useState<RepoContextStatus | null>(null);
  const [graphifyStatus, setGraphifyStatus] = useState<GraphifyDetailResponse | null>(null);
  const [suggestions, setSuggestions] = useState<ContextSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportContent, setReportContent] = useState("");
  const [reportMeta, setReportMeta] = useState<{ relPath?: string | null; truncated?: boolean }>(
    {},
  );
  const [statsOpen, setStatsOpen] = useState(false);
  const [graphSummary, setGraphSummary] = useState<GraphifySummary | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [mirrors, context] = await Promise.all([
        api.getGitMirrors(),
        api.getRepoContext().catch(() => null),
      ]);
      setData(mirrors);
      setContextStatus(context?.status ?? null);
      setSuggestions(context?.suggestions ?? []);
      if (context?.status?.graphify_enabled) {
        try {
          const graphify = await api.getGraphifyStatus();
          setGraphifyStatus(graphify);
        } catch {
          setGraphifyStatus(context?.status?.graph ?? null);
        }
      } else {
        setGraphifyStatus(null);
      }
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load mirrors");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const runCleanup = async (scope: GitMirrorCleanupScope) => {
    setActing(scope);
    try {
      const result = await api.cleanupGitMirrors(scope);
      const ws = result.removed_workspaces.length;
      const sh = result.removed_shared.length;
      notify(
        "success",
        ws || sh
          ? `Removed ${ws} workspace(s) and ${sh} shared mirror(s).`
          : "Nothing to remove.",
      );
      setData((prev) =>
        prev
          ? {
              ...prev,
              summary: result.summary,
              workspaces: prev.workspaces.filter(
                (w) => !result.removed_workspaces.includes(w.id),
              ),
              shared: prev.shared.filter((s) => !result.removed_shared.includes(s.id)),
            }
          : prev,
      );
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Cleanup failed");
    } finally {
      setActing(null);
    }
  };

  const deleteWorkspace = async (id: string) => {
    setActing(`ws:${id}`);
    try {
      await api.deleteGitWorkspace(id);
      notify("success", `Removed workspace ${id}.`);
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Delete failed");
    } finally {
      setActing(null);
    }
  };

  const deleteShared = async (id: string) => {
    setActing(`sh:${id}`);
    try {
      await api.deleteGitSharedMirror(id);
      notify("success", `Removed shared mirror ${id}.`);
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Delete failed");
    } finally {
      setActing(null);
    }
  };

  const syncShared = async () => {
    setActing("sync");
    try {
      const result = await api.syncGitSharedMirrors();
      if (result.ok) {
        notify(
          "success",
          result.context?.ok
            ? "Shared mirrors synced and main-repo context updated."
            : "Shared mirrors synced.",
        );
      } else {
        notify("error", "Some repos failed to sync — check logs.");
      }
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Sync failed");
    } finally {
      setActing(null);
    }
  };

  const syncMainContext = async () => {
    setActing("sync-main");
    try {
      const result = await api.syncMainRepoContext();
      if (result.ok) {
        notify("success", "Main repo synced and context regenerated.");
      } else {
        notify("error", "Main repo sync failed — check logs.");
      }
      setContextStatus(result.status);
      setSuggestions(result.suggestions ?? []);
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Sync main failed");
    } finally {
      setActing(null);
    }
  };

  const regenerateContext = async () => {
    setActing("context");
    try {
      const result = await api.generateRepoContext();
      if (result.ok) {
        notify("success", "Repo context markdown regenerated.");
      }
      setContextStatus(result.status);
      setSuggestions(result.suggestions ?? []);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Context generation failed");
    } finally {
      setActing(null);
    }
  };

  const refreshSuggestions = async () => {
    setActing("suggestions");
    try {
      const result = await api.generateContextSuggestions();
      setSuggestions(result.suggestions ?? []);
      notify("success", "Playbook suggestions updated.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Suggestion generation failed");
    } finally {
      setActing(null);
    }
  };

  const approveSuggestion = async (id: string) => {
    setActing(`approve:${id}`);
    try {
      const result = await api.approveContextSuggestion(id);
      notify("success", `Created playbook ${result.filename}.`);
      setSuggestions((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Approve failed");
    } finally {
      setActing(null);
    }
  };

  const dismissSuggestion = async (id: string) => {
    setActing(`dismiss:${id}`);
    try {
      await api.dismissContextSuggestion(id);
      setSuggestions((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Dismiss failed");
    } finally {
      setActing(null);
    }
  };

  const rebuildGraphify = async () => {
    setActing("graphify-rebuild");
    try {
      const result = await api.rebuildGraphify();
      setGraphifyStatus(result.status);
      setContextStatus((prev) =>
        prev ? { ...prev, graph: result.status } : prev,
      );
      if (result.ok) {
        notify(
          "success",
          `Graph rebuilt — ${result.status.node_count ?? "?"} nodes · ${result.status.edge_count ?? "?"} edges.`,
        );
      } else {
        notify("error", result.result.error ?? "Graphify rebuild failed");
      }
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Graphify rebuild failed");
    } finally {
      setActing(null);
    }
  };

  const viewGraphReport = async () => {
    setActing("graphify-report");
    try {
      const report = await api.getGraphifyReport();
      if (!report.present) {
        notify("error", "Graph report not found — rebuild the graph first.");
        return;
      }
      setReportContent(report.content);
      setReportMeta({ relPath: report.rel_path, truncated: report.truncated });
      setReportOpen(true);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load graph report");
    } finally {
      setActing(null);
    }
  };

  const viewGraphStats = async () => {
    setActing("graphify-stats");
    try {
      const summary = await api.getGraphifySummary();
      if (!summary.present) {
        notify("error", "Graph not found — rebuild the graph first.");
        return;
      }
      setGraphSummary(summary);
      setStatsOpen(true);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load graph stats");
    } finally {
      setActing(null);
    }
  };

  const graph = graphifyStatus ?? contextStatus?.graph;

  const summary = data?.summary;
  const workspaceColumns: ColumnsType<GitMirrorWorkspace> = [
    {
      title: "Session",
      dataIndex: "session_key",
      render: (value: string | undefined, row) => value || row.id,
    },
    {
      title: "Repos",
      dataIndex: "repos",
      render: (repos: string[]) => (repos?.length ? repos.join(", ") : "—"),
    },
    {
      title: "Last used",
      dataIndex: "last_used_at",
      render: (v: string) => formatWhen(v),
    },
    {
      title: "Size",
      dataIndex: "size_bytes",
      render: (v: number) => formatBytes(v || 0),
    },
    {
      title: "",
      key: "actions",
      width: 90,
      render: (_, row) => (
        <Popconfirm
          title="Remove this workspace checkout?"
          onConfirm={() => deleteWorkspace(row.id)}
        >
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            loading={acting === `ws:${row.id}`}
          />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        Repo mirrors
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Local git checkouts used for PR review and code search. Each chat/thread gets its
        own workspace under <Typography.Text code>.alfred/repos/workspaces/</Typography.Text>.
        Shared mirrors warm-cache configured repos.
      </Typography.Paragraph>

      {!data?.enabled ? (
        <div className="alfred-panel">
          <Typography.Text type="secondary">
            Git integration is disabled. Enable it under Integrations to use repo mirrors.
          </Typography.Text>
        </div>
      ) : (
        <>
          <div className="alfred-panel" style={{ marginBottom: 20 }}>
            <Flex wrap="wrap" gap={24} align="center" justify="space-between">
              <div>
                <Typography.Text strong>Disk usage</Typography.Text>
                <div>
                  <Typography.Text>
                    {formatBytes(summary?.total_bytes || 0)} total —{" "}
                    {summary?.workspaces_count ?? 0} workspace(s),{" "}
                    {summary?.shared_count ?? 0} shared
                  </Typography.Text>
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  TTL {summary?.mirror_ttl_hours ?? 24}h · max{" "}
                  {summary?.mirror_max_workspaces ?? 32} workspaces · refresh every{" "}
                  {summary?.mirror_refresh_minutes ?? 30} min
                </Typography.Text>
              </div>
              <Space wrap>
                <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
                  Refresh
                </Button>
                <Button onClick={() => runCleanup("expired")} loading={acting === "expired"}>
                  Cleanup expired
                </Button>
                <Popconfirm
                  title="Remove all session workspaces?"
                  onConfirm={() => runCleanup("workspaces")}
                >
                  <Button danger loading={acting === "workspaces"}>
                    Clear workspaces
                  </Button>
                </Popconfirm>
                <Popconfirm
                  title="Remove all shared mirrors?"
                  onConfirm={() => runCleanup("shared")}
                >
                  <Button danger loading={acting === "shared"}>
                    Clear shared
                  </Button>
                </Popconfirm>
                <Popconfirm
                  title="Remove ALL local mirrors (workspaces + shared)?"
                  onConfirm={() => runCleanup("all")}
                >
                  <Button danger type="primary" loading={acting === "all"}>
                    Clear all
                  </Button>
                </Popconfirm>
                <Button onClick={syncShared} loading={acting === "sync"}>
                  Sync shared
                </Button>
              </Space>
            </Flex>
          </div>

          <div className="alfred-panel" style={{ marginBottom: 20 }}>
            <Typography.Title level={5} style={{ marginTop: 0 }}>
              Main repo context
            </Typography.Title>
            {contextStatus?.configured ? (
              <>
                <Typography.Paragraph style={{ marginBottom: 8 }}>
                  <Typography.Text strong>{contextStatus.main_repo}</Typography.Text>
                  {summary?.main_repo && contextStatus.main_repo !== summary.main_repo ? (
                    <Typography.Text type="secondary"> (resolved from config)</Typography.Text>
                  ) : null}
                </Typography.Paragraph>
                <Typography.Text type="secondary" style={{ fontSize: 12, display: "block" }}>
                  Generated {formatWhen(contextStatus.generated_at)} · HEAD{" "}
                  {contextStatus.head_sha ? `${contextStatus.head_sha.slice(0, 8)}…` : "—"} · files:{" "}
                  {contextStatus.files.length ? contextStatus.files.join(", ") : "none yet"}
                </Typography.Text>
                {!contextStatus.mirror_present ? (
                  <Typography.Paragraph type="warning" style={{ marginTop: 8, marginBottom: 8 }}>
                    Shared mirror missing — sync main repo first.
                  </Typography.Paragraph>
                ) : null}
              </>
            ) : (
              <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
                Set <Typography.Text code>git.main_repo</Typography.Text> under Integrations, then
                sync to build <Typography.Text code>.alfred/context/</Typography.Text> markdown for
                basic codebase questions.
              </Typography.Paragraph>
            )}
            <Space wrap style={{ marginTop: 12 }}>
              <Button
                type="primary"
                onClick={syncMainContext}
                loading={acting === "sync-main"}
                disabled={!contextStatus?.configured}
              >
                Sync main + build context
              </Button>
              <Button
                onClick={regenerateContext}
                loading={acting === "context"}
                disabled={!contextStatus?.configured || !contextStatus.mirror_present}
              >
                Regenerate context
              </Button>
              <Button
                onClick={refreshSuggestions}
                loading={acting === "suggestions"}
                disabled={!contextStatus?.configured || !contextStatus.mirror_present}
              >
                Refresh playbook suggestions
              </Button>
            </Space>

            {suggestions.length > 0 ? (
              <div style={{ marginTop: 16 }}>
                <Typography.Text strong>Suggested playbooks</Typography.Text>
                <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
                  Approve to write into <Typography.Text code>.alfred/playbooks/</Typography.Text>.
                  Edit under Configure → Playbooks after approval.
                </Typography.Paragraph>
                {suggestions.map((item) => (
                  <div
                    key={item.id}
                    className="alfred-panel"
                    style={{ marginBottom: 8, padding: "12px 16px" }}
                  >
                    <Typography.Text strong>{item.title}</Typography.Text>
                    <div>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        → {item.playbook_filename}
                      </Typography.Text>
                    </div>
                    <Typography.Paragraph style={{ marginBottom: 8, fontSize: 13 }}>
                      {item.description}
                    </Typography.Paragraph>
                    <Space>
                      <Button
                        size="small"
                        type="primary"
                        loading={acting === `approve:${item.id}`}
                        onClick={() => approveSuggestion(item.id)}
                      >
                        Approve → playbook
                      </Button>
                      <Button
                        size="small"
                        loading={acting === `dismiss:${item.id}`}
                        onClick={() => dismissSuggestion(item.id)}
                      >
                        Dismiss
                      </Button>
                    </Space>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {contextStatus?.graphify_enabled ? (
            <div className="alfred-panel" style={{ marginBottom: 20 }}>
              <Flex wrap="wrap" gap={8} align="center" justify="space-between">
                <Typography.Title level={5} style={{ margin: 0 }}>
                  Graphify knowledge graph
                </Typography.Title>
                <Space wrap size={[4, 4]}>
                  <Tag color="blue">Enabled</Tag>
                  {graph?.available ? (
                    <Tag color="green">CLI {graph.version ?? "ready"}</Tag>
                  ) : (
                    <Tag color="warning">CLI missing</Tag>
                  )}
                  {graph?.present ? (
                    <Tag color="success">Graph built</Tag>
                  ) : (
                    <Tag>Not built</Tag>
                  )}
                </Space>
              </Flex>
              <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 12 }}>
                Structural index for the shared main-repo mirror. Rebuild uses the cached checkout
                under <Typography.Text code>.alfred/repos/shared/</Typography.Text> without
                re-syncing git. Large repos may take up to{" "}
                {graph?.extract_timeout_minutes ?? 120} minutes on Kimi — use{" "}
                <Typography.Text code>tail -f .alfred/alfred.log</Typography.Text> to watch progress.
              </Typography.Paragraph>

              {!graph?.available ? (
                <Typography.Paragraph type="warning" style={{ marginBottom: 12 }}>
                  {graph?.install_hint ??
                    "Install Graphify in the project venv: uv sync --extra graphify"}
                </Typography.Paragraph>
              ) : null}

              <Descriptions size="small" column={1} bordered style={{ marginBottom: 12 }}>
                <Descriptions.Item label="Repo">
                  {graph?.repo || contextStatus.main_repo || "—"}
                </Descriptions.Item>
                <Descriptions.Item label="Graph">
                  {graph?.present
                    ? `${graph.node_count ?? "?"} nodes · ${graph.edge_count ?? "?"} edges${
                        graph.graph_bytes ? ` · ${formatBytes(graph.graph_bytes)}` : ""
                      }`
                    : "Not built yet"}
                </Descriptions.Item>
                <Descriptions.Item label="Report">
                  {graph?.report_present
                    ? `GRAPH_REPORT.md${
                        graph.report_bytes ? ` · ${formatBytes(graph.report_bytes)}` : ""
                      }`
                    : graph?.present
                      ? "Summary only (fast extract skips clustering)"
                      : "Not built yet"}
                </Descriptions.Item>
                <Descriptions.Item label="Output dir">
                  {graph?.out_rel_path ? (
                    <Typography.Text code>{graph.out_rel_path}</Typography.Text>
                  ) : (
                    "—"
                  )}
                </Descriptions.Item>
                {graph?.extract_running ? (
                  <Descriptions.Item label="Extract status">
                    <Typography.Text type="warning">
                      Running since {formatWhen(graph.extract_started_at)}
                      {graph.extract_pid ? ` · pid ${graph.extract_pid}` : ""}
                    </Typography.Text>
                  </Descriptions.Item>
                ) : null}
                <Descriptions.Item label="Last built">
                  {formatWhen(graph?.built_at)}
                </Descriptions.Item>
                <Descriptions.Item label="LLM backend">
                  {graph?.llm_ready
                    ? `${graph.llm_provider ?? graph.llm_backend ?? "configured"}${
                        graph.llm_model ? ` · ${graph.llm_model}` : ""
                      }`
                    : "No API key — add under Configure → Secrets"}
                </Descriptions.Item>
                {graph?.last_error ? (
                  <Descriptions.Item label="Last error">
                    <Typography.Text type="danger">{graph.last_error}</Typography.Text>
                  </Descriptions.Item>
                ) : null}
              </Descriptions>

              <Space wrap>
                <Button
                  type="primary"
                  onClick={rebuildGraphify}
                  loading={acting === "graphify-rebuild"}
                  disabled={
                    graph?.extract_running ||
                    !graph?.available ||
                    !graph?.llm_ready ||
                    !contextStatus.mirror_present ||
                    !contextStatus.configured
                  }
                >
                  Rebuild graph
                </Button>
                <Button
                  onClick={viewGraphReport}
                  loading={acting === "graphify-report"}
                  disabled={!graph?.present}
                >
                  {graph?.report_present ? "View report" : "View summary"}
                </Button>
                <Button
                  onClick={viewGraphStats}
                  loading={acting === "graphify-stats"}
                  disabled={!graph?.present}
                >
                  View graph stats
                </Button>
              </Space>
              {!contextStatus.mirror_present ? (
                <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                  Sync the main repo first — Graphify reads from the shared mirror.
                </Typography.Paragraph>
              ) : null}
            </div>
          ) : null}

          <Typography.Title level={5}>Session workspaces</Typography.Title>
          <Table
            className="alfred-panel"
            size="small"
            rowKey="id"
            loading={loading}
            dataSource={data?.workspaces ?? []}
            columns={workspaceColumns}
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            locale={{ emptyText: "No workspace checkouts yet." }}
          />

          <Typography.Title level={5} style={{ marginTop: 24 }}>
            Shared cache
          </Typography.Title>
          <Table
            className="alfred-panel"
            size="small"
            rowKey="id"
            loading={loading}
            dataSource={data?.shared ?? []}
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            locale={{ emptyText: "No shared mirrors. Use Sync shared or alfred git sync." }}
            columns={[
              {
                title: "Repo",
                dataIndex: "repo",
                render: (value: string) => {
                  const isMain =
                    summary?.main_repo && value.toLowerCase() === summary.main_repo.toLowerCase();
                  return isMain ? (
                    <>
                      {value}{" "}
                      <Typography.Text type="secondary">(main)</Typography.Text>
                    </>
                  ) : (
                    value
                  );
                },
              },
              {
                title: "Size",
                dataIndex: "size_bytes",
                render: (v: number) => formatBytes(v || 0),
              },
              {
                title: "HEAD",
                dataIndex: "head_sha",
                render: (v: string | null) => (v ? `${v.slice(0, 8)}…` : "—"),
              },
              {
                title: "",
                key: "actions",
                width: 90,
                render: (_, row) => (
                  <Popconfirm
                    title="Remove this shared mirror?"
                    onConfirm={() => deleteShared(row.id)}
                  >
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      loading={acting === `sh:${row.id}`}
                    />
                  </Popconfirm>
                ),
              },
            ]}
          />
        </>
      )}

      <Modal
        title="Graphify report"
        open={reportOpen}
        onCancel={() => setReportOpen(false)}
        footer={[
          <Button key="close" onClick={() => setReportOpen(false)}>
            Close
          </Button>,
        ]}
        width={860}
      >
        {reportMeta.relPath ? (
          <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 12 }}>
            {reportMeta.relPath}
            {reportMeta.truncated ? " · truncated for display" : ""}
          </Typography.Text>
        ) : null}
        <div className="alfred-panel" style={{ maxHeight: "70vh", overflow: "auto", padding: 16 }}>
          <ChatMarkdown content={reportContent || "_Empty report._"} />
        </div>
      </Modal>

      <Modal
        title="Graphify stats"
        open={statsOpen}
        onCancel={() => setStatsOpen(false)}
        footer={[
          <Button key="close" onClick={() => setStatsOpen(false)}>
            Close
          </Button>,
        ]}
        width={760}
      >
        {graphSummary ? (
          <>
            <Descriptions size="small" column={2} bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="Nodes">{graphSummary.node_count}</Descriptions.Item>
              <Descriptions.Item label="Edges">{graphSummary.edge_count}</Descriptions.Item>
            </Descriptions>
            {Object.keys(graphSummary.node_kinds).length > 0 ? (
              <>
                <Typography.Text strong>Node kinds</Typography.Text>
                <div style={{ marginBottom: 16, marginTop: 8 }}>
                  {Object.entries(graphSummary.node_kinds).map(([kind, count]) => (
                    <Tag key={kind} style={{ marginBottom: 4 }}>
                      {kind}: {count}
                    </Tag>
                  ))}
                </div>
              </>
            ) : null}
            <Typography.Text strong>Most connected nodes</Typography.Text>
            <Table
              size="small"
              style={{ marginTop: 8 }}
              rowKey="id"
              pagination={false}
              dataSource={graphSummary.top_nodes}
              columns={[
                { title: "Node", dataIndex: "label", ellipsis: true },
                { title: "Degree", dataIndex: "degree", width: 90 },
              ]}
              locale={{ emptyText: "No node stats available." }}
            />
            {graphSummary.sample_edges.length > 0 ? (
              <>
                <Typography.Text strong style={{ display: "block", marginTop: 16 }}>
                  Sample edges
                </Typography.Text>
                <Table
                  size="small"
                  style={{ marginTop: 8 }}
                  rowKey={(row) => `${row.source}-${row.target}-${row.kind}`}
                  pagination={false}
                  dataSource={graphSummary.sample_edges}
                  columns={[
                    { title: "Source", dataIndex: "source", ellipsis: true },
                    { title: "Target", dataIndex: "target", ellipsis: true },
                    { title: "Kind", dataIndex: "kind", width: 120 },
                  ]}
                />
              </>
            ) : null}
          </>
        ) : (
          <Typography.Text type="secondary">No graph stats loaded.</Typography.Text>
        )}
      </Modal>
    </div>
  );
}
