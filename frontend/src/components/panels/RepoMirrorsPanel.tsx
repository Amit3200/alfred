import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Flex, Popconfirm, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type GitMirrorCleanupScope,
  type GitMirrorsResponse,
  type GitMirrorWorkspace,
} from "../../api/client";
import { useApp } from "../../context/AppContext";

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
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const mirrors = await api.getGitMirrors();
      setData(mirrors);
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
        notify("success", "Shared mirrors synced.");
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
              { title: "Repo", dataIndex: "repo" },
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
    </div>
  );
}
