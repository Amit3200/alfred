import {
  CopyOutlined,
  DeleteOutlined,
  ExportOutlined,
  EyeOutlined,
  ReloadOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Empty,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd";
import type { UploadProps } from "antd";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  getArtifactActorLabel,
  type ArtifactSummary,
} from "../../api/client";
import { useApp } from "../../context/AppContext";

function formatWhen(value?: string | number) {
  if (value === undefined || value === null || value === "") return "—";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function slugShareUrl(slug: string) {
  return `${window.location.origin}/artifacts/s/${slug}`;
}

function shaShareUrl(sha256: string) {
  return `${window.location.origin}/artifacts/sha/${sha256}`;
}

export function ArtifactsPanel() {
  const { notify } = useApp();
  const [items, setItems] = useState<ArtifactSummary[]>([]);
  const [actorLabel, setActorLabel] = useState(getArtifactActorLabel());
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [detailsSlug, setDetailsSlug] = useState<string | null>(null);
  const [versions, setVersions] = useState<ArtifactSummary[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listMyArtifacts();
      setItems(res.artifacts);
      setActorLabel(res.actor.label);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load slides");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const copyText = async (url: string, ok = "Share link copied") => {
    try {
      await navigator.clipboard.writeText(url);
      notify("success", ok);
    } catch {
      notify("error", url);
    }
  };

  const openDetails = async (row: ArtifactSummary) => {
    setDetailsSlug(row.slug);
    setDetailsLoading(true);
    try {
      const meta = await api.getArtifactMeta(row.slug);
      setVersions(meta.versions);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load versions");
      setVersions([]);
    } finally {
      setDetailsLoading(false);
    }
  };

  const refreshDetails = async (currentSlug: string) => {
    const meta = await api.getArtifactMeta(currentSlug);
    setVersions(meta.versions);
    await load();
  };

  const deleteVersion = async (row: ArtifactSummary) => {
    setDeleting(row.sha256);
    try {
      const result = await api.deleteArtifactVersion(row.slug, row.sha256);
      notify("success", result.slug_removed ? "Presentation deleted" : "Version deleted");
      if (result.slug_removed) {
        setDetailsSlug(null);
        setVersions([]);
        await load();
      } else if (detailsSlug) {
        await refreshDetails(detailsSlug);
      }
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  const uploadProps: UploadProps = {
    accept: ".html,text/html",
    showUploadList: false,
    beforeUpload: async (file) => {
      if (!slug.trim()) {
        notify("error", "Enter a slug before uploading");
        return false;
      }
      setUploading(true);
      try {
        await api.uploadArtifactFile(slug.trim(), title.trim(), file);
        notify("success", "Presentation uploaded");
        setUploadOpen(false);
        setSlug("");
        setTitle("");
        await load();
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
      return false;
    },
  };

  return (
    <div className="alfred-settings-page">
      <Flex justify="space-between" align="flex-start" wrap="gap">
        <div>
          <Typography.Title level={3} className="alfred-page-title">
            HTML slides
          </Typography.Title>
          <Typography.Paragraph className="alfred-page-desc">
            Latest version per slug. Open <strong>View details</strong> for older SHAs,
            upload times, share links, and delete. Share URLs stay public.
          </Typography.Paragraph>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
            Upload HTML
          </Button>
        </Space>
      </Flex>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={`Viewing uploads for ${actorLabel}`}
        description="Identity comes from your admin login username. Slack uploads use the requester's Slack user ID via X-Alfred-Actor-Key. Scheduled decks (for example daily-metrics) are shared with all admins."
      />

      <div className="alfred-panel alfred-artifacts-table">
        <Table
          rowKey={(row) => row.slug}
          loading={loading}
          dataSource={items}
          locale={{ emptyText: <Empty description="No slides uploaded yet" /> }}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          size="small"
          columns={[
            {
              title: "Slug",
              dataIndex: "slug",
              render: (value: string) => <Typography.Text code>{value}</Typography.Text>,
            },
            {
              title: "Title",
              dataIndex: "title",
              render: (value: string) => value || "—",
            },
            {
              title: "Updated",
              dataIndex: "uploaded_at_iso",
              render: (_, row) => formatWhen(row.uploaded_at_iso || row.uploaded_at),
            },
            {
              title: "Versions",
              dataIndex: "version_count",
              width: 100,
              render: (value: number | undefined) => value ?? 1,
            },
            {
              title: "",
              key: "actions",
              render: (_, row) => (
                <Space wrap>
                  <Button
                    size="small"
                    icon={<ExportOutlined />}
                    href={row.slug_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open
                  </Button>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => void copyText(slugShareUrl(row.slug))}
                  >
                    Copy link
                  </Button>
                  <Button size="small" icon={<EyeOutlined />} onClick={() => void openDetails(row)}>
                    View details
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </div>

      <Modal
        title={detailsSlug ? `Versions — ${detailsSlug}` : "Versions"}
        open={Boolean(detailsSlug)}
        onCancel={() => {
          setDetailsSlug(null);
          setVersions([]);
        }}
        footer={null}
        width={820}
        destroyOnClose
      >
        <Table
          rowKey={(row) => row.sha256}
          loading={detailsLoading}
          dataSource={versions}
          pagination={false}
          size="small"
          locale={{ emptyText: <Empty description="No versions" /> }}
          columns={[
            {
              title: "SHA",
              dataIndex: "sha256",
              render: (value: string, row) => (
                <Space>
                  <Typography.Text code copyable={{ text: value }}>
                    {value.slice(0, 8)}…
                  </Typography.Text>
                  {row.is_latest ? <Tag color="blue">latest</Tag> : null}
                </Space>
              ),
            },
            {
              title: "Uploaded",
              dataIndex: "uploaded_at_iso",
              render: (_, row) => formatWhen(row.uploaded_at_iso || row.uploaded_at),
            },
            {
              title: "Title",
              dataIndex: "title",
              ellipsis: true,
              render: (value: string) => value || "—",
            },
            {
              title: "",
              key: "actions",
              width: 112,
              render: (_, row) => {
                const openHref = row.is_latest ? row.slug_url : row.sha_url;
                const share = row.is_latest ? slugShareUrl(row.slug) : shaShareUrl(row.sha256);
                return (
                  <Space size={2} wrap={false}>
                    <Button
                      type="text"
                      size="small"
                      icon={<ExportOutlined />}
                      href={openHref}
                      target="_blank"
                      rel="noreferrer"
                      title="Open"
                      aria-label="Open"
                    />
                    <Button
                      type="text"
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => void copyText(share)}
                      title="Copy link"
                      aria-label="Copy link"
                    />
                    <Popconfirm
                      title="Delete this version?"
                      description={
                        row.is_latest
                          ? "This is the latest. The previous SHA becomes the live slug URL."
                          : "Removes this SHA. The live slug URL is unchanged."
                      }
                      okText="Delete"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => void deleteVersion(row)}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        loading={deleting === row.sha256}
                        title="Delete"
                        aria-label="Delete"
                      />
                    </Popconfirm>
                  </Space>
                );
              },
            },
          ]}
        />
      </Modal>

      <Modal
        title="Upload HTML presentation"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Typography.Text type="secondary">Slug (stable share URL)</Typography.Text>
            <Input
              placeholder="daily-metrics"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
            />
          </div>
          <div>
            <Typography.Text type="secondary">Title</Typography.Text>
            <Input
              placeholder="Daily metrics"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <Upload {...uploadProps}>
            <Button type="primary" icon={<UploadOutlined />} loading={uploading} block>
              Select .html file
            </Button>
          </Upload>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            Re-uploading the same slug creates a new version. Latest is served at{" "}
            <Typography.Text code>/artifacts/s/&lt;slug&gt;</Typography.Text>. Older SHAs stay at{" "}
            <Typography.Text code>/artifacts/sha/&lt;sha256&gt;</Typography.Text>.
          </Typography.Paragraph>
        </Space>
      </Modal>
    </div>
  );
}
