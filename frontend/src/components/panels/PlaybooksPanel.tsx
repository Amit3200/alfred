import {
  DeleteOutlined,
  FileAddOutlined,
  PlusOutlined,
  SaveOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Button,
  Empty,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Space,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import type { UploadProps } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type PlaybookSummary } from "../../api/client";
import { useApp } from "../../context/AppContext";

const { TextArea } = Input;

function triggerSummary(triggers: string[] | undefined): string {
  if (!triggers?.length) return "No triggers";
  if (triggers.length === 1) return triggers[0];
  return `${triggers.length} triggers`;
}

function playbookFolder(filename: string): string {
  const parts = filename.split("/");
  if (parts.length <= 1) return "Root";
  return parts.slice(0, -1).join("/");
}

function playbookLeaf(filename: string): string {
  return filename.split("/").pop() ?? filename;
}

type PlaybookGroup = {
  folder: string;
  items: PlaybookSummary[];
};

function groupPlaybooks(items: PlaybookSummary[]): PlaybookGroup[] {
  const buckets = new Map<string, PlaybookSummary[]>();
  for (const item of items) {
    const folder = playbookFolder(item.filename);
    const list = buckets.get(folder) ?? [];
    list.push(item);
    buckets.set(folder, list);
  }
  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([folder, groupItems]) => ({
      folder,
      items: groupItems.sort((a, b) => a.filename.localeCompare(b.filename)),
    }));
}

export function PlaybooksPanel() {
  const { notify, dataDir } = useApp();
  const [items, setItems] = useState<PlaybookSummary[]>([]);
  const [directory, setDirectory] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [editorLoading, setEditorLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [newFilename, setNewFilename] = useState("");
  const [search, setSearch] = useState("");

  const dirty = content !== savedContent;

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) => {
      const haystack = [
        item.filename,
        item.name ?? "",
        ...(item.triggers ?? []),
        item.mode ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [items, search]);

  const groupedItems = useMemo(() => groupPlaybooks(filteredItems), [filteredItems]);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listPlaybooks();
      setItems(data.playbooks);
      setDirectory(data.directory);
      setSelected((prev) => {
        if (prev && data.playbooks.some((p) => p.filename === prev)) return prev;
        return data.playbooks[0]?.filename ?? null;
      });
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load playbooks");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const loadEditor = useCallback(
    async (filename: string) => {
      setEditorLoading(true);
      try {
        const detail = await api.getPlaybook(filename);
        setContent(detail.content);
        setSavedContent(detail.content);
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Failed to load playbook");
        setContent("");
        setSavedContent("");
      } finally {
        setEditorLoading(false);
      }
    },
    [notify],
  );

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (selected) {
      loadEditor(selected);
    } else {
      setContent("");
      setSavedContent("");
    }
  }, [selected, loadEditor]);

  const selectedMeta = useMemo(
    () => items.find((item) => item.filename === selected) ?? null,
    [items, selected],
  );

  const save = async () => {
    if (!selected || !content.trim()) return;
    setSaving(true);
    try {
      const result = await api.savePlaybook(selected, content);
      setSavedContent(content);
      setItems((prev) =>
        prev.map((item) =>
          item.filename === selected
            ? {
                ...item,
                ...result,
              }
            : item,
        ),
      );
      notify("success", `Saved ${selected}`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const createNew = async (fromExample = false) => {
    const name = newFilename.trim();
    if (!name) {
      notify("error", "Enter a filename");
      return;
    }
    try {
      let body: { filename: string; content?: string } = { filename: name };
      if (fromExample) {
        const example = await api.getPlaybookExample();
        body = { filename: name || example.filename, content: example.content };
      }
      const result = await api.createPlaybook(body.filename, body.content);
      setNewOpen(false);
      setNewFilename("");
      await loadList();
      setSelected(result.filename);
      notify("success", `Created ${result.filename}`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Create failed");
    }
  };

  const remove = async (filename: string) => {
    try {
      await api.deletePlaybook(filename);
      notify("success", `Deleted ${filename}`);
      if (selected === filename) {
        setSelected(null);
        setContent("");
        setSavedContent("");
      }
      await loadList();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Delete failed");
    }
  };

  const uploadProps: UploadProps = {
    accept: ".md,text/markdown,text/plain",
    showUploadList: false,
    multiple: false,
    beforeUpload: async (file) => {
      try {
        const result = await api.uploadPlaybook(file);
        await loadList();
        setSelected(result.filename);
        notify("success", `Uploaded ${result.filename}`);
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Upload failed");
      }
      return false;
    },
  };

  return (
    <div>
      <Typography.Title level={3} className="alfred-page-title">
        Playbooks
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Company-specific Markdown rules stored locally in{" "}
        <Typography.Text code>{directory || `${dataDir}/playbooks`}</Typography.Text>. Alfred keeps a
        compact catalog in memory and loads one matching playbook per request (longest trigger wins).
        Not committed to git.
      </Typography.Paragraph>

      <Flex gap={16} align="stretch" className="alfred-playbooks-layout">
        <div className="alfred-playbooks-list">
          <Flex justify="space-between" align="center" style={{ marginBottom: 12 }}>
            <Typography.Text strong>
              Files {items.length ? `(${filteredItems.length}${search ? ` of ${items.length}` : ""})` : ""}
            </Typography.Text>
            <Space size={4}>
              <Button size="small" icon={<PlusOutlined />} onClick={() => setNewOpen(true)}>
                New
              </Button>
              <Upload {...uploadProps}>
                <Button size="small" icon={<UploadOutlined />}>
                  Upload
                </Button>
              </Upload>
            </Space>
          </Flex>

          <Input
            allowClear
            placeholder="Search name, path, triggers…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ marginBottom: 12 }}
          />

          <div className="alfred-playbooks-list-scroll">
            {loading ? (
              <Typography.Text type="secondary">Loading…</Typography.Text>
            ) : groupedItems.length === 0 ? (
              <Empty description={search ? "No matches" : "No playbooks yet"} />
            ) : (
              groupedItems.map((group) => (
                <div key={group.folder} className="alfred-playbooks-group">
                  <Typography.Text type="secondary" className="alfred-playbooks-group-label">
                    {group.folder}
                  </Typography.Text>
                  <div className="alfred-playbooks-group-items">
                    {group.items.map((item) => {
                      const active = selected === item.filename;
                      return (
                        <div
                          key={item.filename}
                          className={active ? "alfred-playbooks-row-active" : "alfred-playbooks-row"}
                          onClick={() => setSelected(item.filename)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setSelected(item.filename);
                            }
                          }}
                        >
                          <div className="alfred-playbooks-row-main">
                            <Typography.Text strong ellipsis className="alfred-playbooks-row-title">
                              {item.name || playbookLeaf(item.filename)}
                            </Typography.Text>
                            {group.folder !== "Root" ? (
                              <Tooltip title={item.filename}>
                                <Typography.Text type="secondary" ellipsis className="alfred-playbooks-row-path">
                                  {playbookLeaf(item.filename)}
                                </Typography.Text>
                              </Tooltip>
                            ) : null}
                            <div className="alfred-playbooks-row-tags">
                              {item.parse_error ? (
                                <Tag color="error">parse error</Tag>
                              ) : (
                                <>
                                  {item.mode && item.mode !== "conversational" ? (
                                    <Tag color="purple">{item.mode}</Tag>
                                  ) : null}
                                  <Tag>{triggerSummary(item.triggers)}</Tag>
                                  {item.fetch_urls?.length ? (
                                    <Tag color="blue">{item.fetch_urls.length} URL(s)</Tag>
                                  ) : null}
                                </>
                              )}
                            </div>
                          </div>
                          <Popconfirm
                            title={`Delete ${item.filename}?`}
                            onConfirm={(e) => {
                              e?.stopPropagation();
                              remove(item.filename);
                            }}
                            onCancel={(e) => e?.stopPropagation()}
                          >
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              className="alfred-playbooks-row-delete"
                              onClick={(e) => e.stopPropagation()}
                              aria-label={`Delete ${item.filename}`}
                            />
                          </Popconfirm>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="alfred-playbooks-editor">
          {selected ? (
            <>
              <Flex justify="space-between" align="flex-start" wrap="wrap" gap={8} style={{ marginBottom: 12 }}>
                <div className="alfred-playbooks-editor-meta">
                  <Typography.Text strong>{selectedMeta?.name || playbookLeaf(selected)}</Typography.Text>
                  <Tooltip title={selected}>
                    <Typography.Text type="secondary" ellipsis className="alfred-playbooks-editor-path">
                      {selected}
                    </Typography.Text>
                  </Tooltip>
                  <Flex gap={8} wrap="wrap" align="center">
                    {dirty ? <Typography.Text type="warning">unsaved</Typography.Text> : null}
                    {selectedMeta?.updated_at ? (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        Updated {new Date(selectedMeta.updated_at).toLocaleString()}
                      </Typography.Text>
                    ) : null}
                  </Flex>
                </div>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  onClick={save}
                  loading={saving}
                  disabled={!dirty || editorLoading}
                >
                  Save
                </Button>
              </Flex>
              <TextArea
                className="alfred-playbooks-textarea"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                spellCheck={false}
                placeholder={"---\nname: my-playbook\ntriggers:\n  - keyword\n---\n\n# Instructions"}
              />
            </>
          ) : (
            <Empty description="Select or create a playbook" />
          )}
        </div>
      </Flex>

      <Modal
        title="New playbook"
        open={newOpen}
        onCancel={() => {
          setNewOpen(false);
          setNewFilename("");
        }}
        footer={[
          <Button key="cancel" onClick={() => setNewOpen(false)}>
            Cancel
          </Button>,
          <Button key="example" icon={<FileAddOutlined />} onClick={() => createNew(true)}>
            From example
          </Button>,
          <Button key="create" type="primary" onClick={() => createNew(false)}>
            Create blank
          </Button>,
        ]}
      >
        <label className="alfred-field-label">Filename</label>
        <Input
          placeholder="merchant-alerts.md"
          value={newFilename}
          onChange={(e) => setNewFilename(e.target.value)}
          onPressEnter={() => createNew(false)}
        />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          Use letters, numbers, hyphens, and underscores. Saved under your local{" "}
          <Typography.Text code>.alfred/playbooks/</Typography.Text> folder.
        </Typography.Paragraph>
      </Modal>
    </div>
  );
}
