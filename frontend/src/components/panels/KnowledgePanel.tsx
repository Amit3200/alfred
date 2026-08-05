import {
  BookOutlined,
  CloudSyncOutlined,
  DeleteOutlined,
  NodeIndexOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Flex,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type GitRepoProfile,
  type KnowledgeBaseEntry,
  type KnowledgeBasesResponse,
} from "../../api/client";
import { useApp } from "../../context/AppContext";

const ROLE_OPTIONS = [
  { value: "docs", label: "Docs — support knowledge base" },
  { value: "code", label: "Code — investigation / main codebase" },
  { value: "scripts", label: "Scripts — metrics & automation source" },
];

const TAG_SUGGESTIONS = [
  "handbook",
  "support",
  "tech",
  "playbook",
  "runbook",
  "cipher",
  "code",
  "integrations",
];

function formatWhen(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function repoSourceLabel(source?: string, org?: string | null): string {
  if (source === "org" && org) return `Loaded ${org} repos from GitHub/GitLab.`;
  if (source === "user") return "Loaded your accessible repos from GitHub/GitLab.";
  if (source === "configured") return "Using configured repos allowlist only.";
  return "Set Org and git token (Secrets) to load repos from GitHub.";
}

function repoSelectOptions(repos: string[], exclude: Set<string>) {
  const seen = new Set<string>();
  const options: { value: string; label: string }[] = [];
  for (const repo of repos) {
    const value = repo.trim();
    if (!value || seen.has(value.toLowerCase()) || exclude.has(value.toLowerCase())) continue;
    seen.add(value.toLowerCase());
    options.push({ value, label: value });
  }
  return options.sort((a, b) => a.label.localeCompare(b.label));
}

export function KnowledgePanel() {
  const { config, updateConfig, saveConfig, notify } = useApp();
  const [status, setStatus] = useState<KnowledgeBasesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [newRepo, setNewRepo] = useState("");
  const [availableRepos, setAvailableRepos] = useState<string[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [reposSource, setReposSource] = useState<string>("configured");
  const [reposOrg, setReposOrg] = useState<string | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);

  const profiles = config?.git.repo_profiles ?? [];

  const examples = useMemo(() => {
    const org = config?.git.default_org?.trim() || "your-org";
    const main = config?.git.main_repo?.trim() || `${org}/main-app`;
    const docs = profiles.find((p) => p.role === "docs")?.repo || `${org}/docs`;
    return { org, main, docs };
  }, [config?.git.default_org, config?.git.main_repo, profiles]);

  const loadAvailableRepos = useCallback(async () => {
    if (!config?.git.enabled) {
      setAvailableRepos([]);
      setReposError(null);
      return;
    }
    setLoadingRepos(true);
    try {
      const data = await api.getAvailableGitRepos();
      setAvailableRepos(data.repos ?? []);
      setReposSource(data.source ?? "configured");
      setReposOrg(data.org ?? null);
      setReposError(data.error ?? null);
    } catch (err) {
      setAvailableRepos(config.git.repos ?? []);
      setReposError(err instanceof Error ? err.message : "Failed to load repos");
    } finally {
      setLoadingRepos(false);
    }
  }, [config?.git.enabled, config?.git.repos]);

  useEffect(() => {
    void loadAvailableRepos();
  }, [loadAvailableRepos, config?.git.default_org, config?.git.provider]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await api.getKnowledgeBases());
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load knowledge bases");
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const upsertProfile = (repo: string, patch: Partial<GitRepoProfile>) => {
    if (!config) return;
    const existing = profiles.find((item) => item.repo === repo);
    const nextProfiles = existing
      ? profiles.map((item) => (item.repo === repo ? { ...item, ...patch } : item))
      : [...profiles, { repo, role: "docs" as const, doc_index: true, graphify: true, tags: [], ...patch }];
    const repoSet = new Set(config.git.repos);
    repoSet.add(repo);
    updateConfig({
      git: {
        ...config.git,
        repo_profiles: nextProfiles,
        repos: Array.from(repoSet),
      },
    });
  };

  const addRepo = () => {
    const repo = newRepo.trim();
    if (!repo) return;
    upsertProfile(repo, { role: "docs", doc_index: true, graphify: true });
    setNewRepo("");
  };

  const removeRepo = (repo: string) => {
    if (!config) return;
    if (repo === config.git.main_repo) {
      notify("error", "Cannot remove the main codebase repo. Change it under Integrations first.");
      return;
    }
    updateConfig({
      git: {
        ...config.git,
        repo_profiles: profiles.filter((item) => item.repo !== repo),
        repos: config.git.repos.filter((item) => item !== repo),
      },
    });
    notify("success", `Removed ${repo}. Click Save settings to persist.`);
  };

  const addedRepoKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const profile of profiles) {
      keys.add(profile.repo.toLowerCase());
    }
    for (const entry of status?.repos ?? []) {
      keys.add(entry.repo.toLowerCase());
    }
    if (config?.git.main_repo) {
      keys.add(config.git.main_repo.toLowerCase());
    }
    return keys;
  }, [profiles, status?.repos, config?.git.main_repo]);

  const repoPickerOptions = useMemo(
    () => repoSelectOptions(availableRepos, addedRepoKeys),
    [availableRepos, addedRepoKeys],
  );

  const saveProfiles = async () => {
    setActing("save");
    try {
      await saveConfig();
      notify("success", "Knowledge repo settings saved.");
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Save failed");
    } finally {
      setActing(null);
    }
  };

  const runAction = async (repo: string, action: "sync" | "index" | "graphify") => {
    setActing(`${action}:${repo}`);
    try {
      if (action === "sync") {
        await api.syncKnowledgeRepo(repo);
      } else if (action === "index") {
        await api.rebuildKnowledgeIndex(repo);
      } else {
        await api.rebuildKnowledgeGraph(repo);
      }
      notify("success", `${action} completed for ${repo}`);
      await load();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : `${action} failed`);
    } finally {
      setActing(null);
    }
  };

  const rows = useMemo(() => {
    const fromStatus = status?.repos ?? [];
    const byRepo = new Map(fromStatus.map((row) => [row.repo, row]));
    for (const profile of profiles) {
      if (!byRepo.has(profile.repo)) {
        byRepo.set(profile.repo, {
          repo: profile.repo,
          role: profile.role,
          doc_index: profile.doc_index ?? profile.role === "docs",
          graphify: profile.graphify ?? profile.role === "docs",
          tags: profile.tags ?? [],
          mirror_present: false,
          doc: { indexed: false, chunk_count: 0, generated_at: null, head_sha: null },
          graph: { present: false, node_count: 0, edge_count: 0 },
          is_main_repo: profile.repo === config?.git.main_repo,
        });
      }
    }
    return Array.from(byRepo.values());
  }, [status, profiles, config?.git.main_repo]);

  const columns: ColumnsType<KnowledgeBaseEntry> = [
    {
      title: "Repository",
      dataIndex: "repo",
      render: (repo: string, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{repo}</Typography.Text>
          {row.is_main_repo ? <Tag color="blue">Main codebase</Tag> : null}
        </Space>
      ),
    },
    {
      title: "Role",
      dataIndex: "role",
      width: 200,
      render: (_role, row) => (
        <Select
          size="small"
          style={{ width: "100%" }}
          value={profiles.find((p) => p.repo === row.repo)?.role ?? row.role}
          options={ROLE_OPTIONS}
          onChange={(role) => {
            const defaults =
              role === "docs"
                ? { doc_index: true, graphify: true }
                : { doc_index: false, graphify: false };
            upsertProfile(row.repo, { role, ...defaults });
          }}
        />
      ),
    },
    {
      title: "Doc index",
      width: 110,
      render: (_, row) => {
        const profile = profiles.find((p) => p.repo === row.repo);
        const checked = profile?.doc_index ?? row.doc_index;
        return (
          <Switch
            size="small"
            checked={Boolean(checked)}
            onChange={(v) => upsertProfile(row.repo, { doc_index: v })}
          />
        );
      },
    },
    {
      title: "Graphify",
      width: 100,
      render: (_, row) => {
        const profile = profiles.find((p) => p.repo === row.repo);
        const checked = profile?.graphify ?? row.graphify;
        return (
          <Switch
            size="small"
            checked={Boolean(checked)}
            disabled={!status?.graphify_enabled}
            onChange={(v) => upsertProfile(row.repo, { graphify: v })}
          />
        );
      },
    },
    {
      title: "Tags",
      width: 220,
      render: (_, row) => {
        const profile = profiles.find((p) => p.repo === row.repo);
        const tags = profile?.tags ?? row.tags ?? [];
        return (
          <Select
            mode="tags"
            size="small"
            style={{ width: "100%" }}
            placeholder="handbook, playbook…"
            value={tags}
            options={TAG_SUGGESTIONS.map((tag) => ({ value: tag, label: tag }))}
            onChange={(next) => upsertProfile(row.repo, { tags: next })}
          />
        );
      },
    },
    {
      title: "Mirror",
      width: 90,
      render: (_, row) =>
        row.mirror_present ? <Tag color="green">Synced</Tag> : <Tag>Missing</Tag>,
    },
    {
      title: "Docs",
      width: 120,
      render: (_, row) =>
        row.doc.indexed ? (
          <Typography.Text type="secondary">{row.doc.chunk_count} chunks</Typography.Text>
        ) : (
          <Typography.Text type="secondary">Not indexed</Typography.Text>
        ),
    },
    {
      title: "Graph",
      width: 110,
      render: (_, row) =>
        row.graph.present ? (
          <Typography.Text type="secondary">{row.graph.node_count} nodes</Typography.Text>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: "Updated",
      width: 150,
      render: (_, row) => (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {formatWhen(row.doc.generated_at)}
        </Typography.Text>
      ),
    },
    {
      title: "Actions",
      width: 300,
      render: (_, row) => (
        <Space wrap size={4}>
          <Button
            size="small"
            icon={<CloudSyncOutlined />}
            loading={acting === `sync:${row.repo}`}
            onClick={() => void runAction(row.repo, "sync")}
          >
            Sync
          </Button>
          <Button
            size="small"
            icon={<SearchOutlined />}
            loading={acting === `index:${row.repo}`}
            onClick={() => void runAction(row.repo, "index")}
          >
            Index
          </Button>
          <Button
            size="small"
            icon={<NodeIndexOutlined />}
            disabled={!status?.graphify_enabled}
            loading={acting === `graphify:${row.repo}`}
            onClick={() => void runAction(row.repo, "graphify")}
          >
            Graph
          </Button>
          <Popconfirm
            title={`Remove ${row.repo}?`}
            description="Removes from knowledge config. Save settings to persist. Delete the mirror under Repo mirrors if needed."
            okText="Remove"
            okButtonProps={{ danger: true }}
            onConfirm={() => removeRepo(row.repo)}
            disabled={row.is_main_repo}
          >
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              disabled={row.is_main_repo}
              title={row.is_main_repo ? "Main codebase cannot be removed here" : "Remove repo"}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="alfred-panel">
      <Flex justify="space-between" align="start" wrap gap={12} style={{ marginBottom: 16 }}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            <BookOutlined style={{ marginRight: 8 }} />
            Knowledge bases
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 720 }}>
            Mirror repositories, build doc indexes and Graphify graphs for support Q&amp;A in Chat
            and Slack. Example: <Typography.Text code>{examples.docs}</Typography.Text> for docs,{" "}
            <Typography.Text code>{examples.main}</Typography.Text> for code investigation.
          </Typography.Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          Refresh status
        </Button>
      </Flex>

      {!config?.git.enabled ? (
        <Alert
          type="warning"
          showIcon
          message="Git integration is disabled"
          description="Enable Git under Integrations and add a token in Secrets before syncing knowledge repos."
          style={{ marginBottom: 16 }}
        />
      ) : null}

      {!status?.graphify_enabled ? (
        <Alert
          type="info"
          showIcon
          message="Graphify is off"
          description="Enable Graphify under Integrations to build knowledge graphs. Doc BM25 search works without Graphify."
          style={{ marginBottom: 16 }}
        />
      ) : null}

      <div
        className="alfred-settings-action"
        style={{ marginBottom: 16, padding: 12, borderRadius: 8, alignItems: "center" }}
      >
        <Flex gap={8} wrap align="center" style={{ width: "100%" }}>
          <Select
            showSearch
            allowClear
            placeholder={
              config?.git.enabled
                ? config.git.default_org
                  ? "Select repo from GitHub…"
                  : "Set Org under Integrations to load repos"
                : "Enable Git integration first"
            }
            style={{ minWidth: 280, flex: 1 }}
            loading={loadingRepos}
            disabled={!config?.git.enabled}
            value={newRepo || undefined}
            options={repoPickerOptions}
            optionFilterProp="label"
            onChange={(value) => setNewRepo(value ?? "")}
          />
          <Button
            icon={<ReloadOutlined />}
            loading={loadingRepos}
            disabled={!config?.git.enabled}
            onClick={() => void loadAvailableRepos()}
            title="Reload repos from GitHub/GitLab"
          >
            Load repos
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!newRepo.trim()}
            onClick={() => addRepo()}
          >
            Add repo
          </Button>
          <Button loading={acting === "save"} onClick={() => void saveProfiles()}>
            Save settings
          </Button>
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>
          {repoSourceLabel(reposSource, reposOrg)}
          {reposError ? (
            <Typography.Text type="warning" style={{ display: "block" }}>
              {reposError}
            </Typography.Text>
          ) : null}
        </Typography.Text>
      </div>

      <Table
        rowKey="repo"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
        locale={{ emptyText: `Add a repo above (e.g. ${examples.docs}) and save settings.` }}
      />

      <Typography.Paragraph type="secondary" style={{ marginTop: 16, fontSize: 12 }}>
        Scripts for scheduled metrics live in{" "}
        <Typography.Text code>scripts.remote.repo</Typography.Text> (e.g.{" "}
        <Typography.Text code>{examples.org}/dailyscripts</Typography.Text>) — configure under
        Integrations → Scripts repo, then use Scripts and Schedules panels.
      </Typography.Paragraph>
    </div>
  );
}
