import {
  CopyOutlined,
  ExportOutlined,
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
  Space,
  Table,
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

function shareUrl(slug: string) {
  return `${window.location.origin}/artifacts/s/${slug}`;
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

  const copyLink = async (item: ArtifactSummary) => {
    const url = shareUrl(item.slug);
    try {
      await navigator.clipboard.writeText(url);
      notify("success", "Share link copied");
    } catch {
      notify("error", url);
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
            Upload and manage your HTML slide decks. You only see presentations you
            uploaded — share links remain public for anyone with the URL.
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
        description="Identity comes from your admin login username. Slack uploads use the requester's Slack user ID via X-Alfred-Actor-Key."
      />

      <div className="alfred-panel alfred-artifacts-table">
        <Table
          rowKey={(row) => row.uuid}
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
            title: "SHA",
            dataIndex: "sha256",
            render: (value: string) => (
              <Typography.Text code copyable={{ text: value }}>
                {value.slice(0, 8)}…
              </Typography.Text>
            ),
          },
          {
            title: "",
            key: "actions",
            render: (_, row) => (
              <Space>
                <Button
                  size="small"
                  icon={<ExportOutlined />}
                  href={row.slug_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open
                </Button>
                <Button size="small" icon={<CopyOutlined />} onClick={() => void copyLink(row)}>
                  Copy link
                </Button>
              </Space>
            ),
          },
        ]}
        />
      </div>

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
              placeholder="redirection-2025"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
            />
          </div>
          <div>
            <Typography.Text type="secondary">Title</Typography.Text>
            <Input
              placeholder="Redirection review 2025"
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
            Re-uploading the same slug creates a new version. Only you can update slugs you
            own. Latest version is served at{" "}
            <Typography.Text code>/artifacts/s/&lt;slug&gt;</Typography.Text>.
          </Typography.Paragraph>
        </Space>
      </Modal>
    </div>
  );
}
