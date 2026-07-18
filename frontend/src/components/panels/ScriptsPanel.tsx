import {
  DeleteOutlined,
  FileAddOutlined,
  PlusOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import {
  Button,
  Empty,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ScriptPackageSummary } from "../../api/client";
import { useApp } from "../../context/AppContext";

const { TextArea } = Input;

const RUNTIME_OPTIONS = [
  { value: "python3", label: "Python 3" },
  { value: "bash", label: "Bash" },
  { value: "sh", label: "Shell" },
  { value: "node", label: "Node.js" },
  { value: "deno", label: "Deno" },
  { value: "go", label: "Go" },
  { value: "custom", label: "Custom command" },
];

function packageFolder(name: string): string {
  const parts = name.split("/");
  if (parts.length <= 1) return "Root";
  return parts.slice(0, -1).join("/");
}

function packageLeaf(name: string): string {
  return name.split("/").pop() ?? name;
}

function fullFilePath(pkg: ScriptPackageSummary, file: string): string {
  return `${pkg.relative_path}/${file}`.replace(/\/+/g, "/");
}

type PackageGroup = {
  folder: string;
  items: ScriptPackageSummary[];
};

function groupPackages(items: ScriptPackageSummary[]): PackageGroup[] {
  const buckets = new Map<string, ScriptPackageSummary[]>();
  for (const item of items) {
    const folder = packageFolder(item.name);
    const list = buckets.get(folder) ?? [];
    list.push(item);
    buckets.set(folder, list);
  }
  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([folder, groupItems]) => ({
      folder,
      items: groupItems.sort((a, b) => a.name.localeCompare(b.name)),
    }));
}

export function ScriptsPanel() {
  const { notify, dataDir } = useApp();
  const [packages, setPackages] = useState<ScriptPackageSummary[]>([]);
  const [directory, setDirectory] = useState("");
  const [exampleAvailable, setExampleAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedPackage, setSelectedPackage] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [editorLoading, setEditorLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [newPackagePath, setNewPackagePath] = useState("");
  const [newRuntime, setNewRuntime] = useState("python3");
  const [newEntry, setNewEntry] = useState("main.py");
  const [newDescription, setNewDescription] = useState("Company script package");
  const [addFileOpen, setAddFileOpen] = useState(false);
  const [newFilePath, setNewFilePath] = useState("");

  const dirty = content !== savedContent;

  const filteredPackages = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return packages;
    return packages.filter((item) => {
      const haystack = [item.name, item.description ?? "", item.runtime, item.entry, ...(item.files ?? [])]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [packages, search]);

  const groupedPackages = useMemo(() => groupPackages(filteredPackages), [filteredPackages]);

  const selectedMeta = useMemo(
    () => packages.find((item) => item.name === selectedPackage) ?? null,
    [packages, selectedPackage],
  );

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listScripts();
      setPackages(data.packages);
      setDirectory(data.directory);
      setExampleAvailable(data.example_available);
      setSelectedPackage((prev) => {
        if (prev && data.packages.some((pkg) => pkg.name === prev)) return prev;
        return data.packages[0]?.name ?? null;
      });
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load scripts");
      setPackages([]);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const loadEditor = useCallback(
    async (relativePath: string) => {
      setEditorLoading(true);
      try {
        const detail = await api.getScriptFile(relativePath);
        setContent(detail.content);
        setSavedContent(detail.content);
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Failed to load file");
        setContent("");
        setSavedContent("");
      } finally {
        setEditorLoading(false);
      }
    },
    [notify],
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedMeta) {
      setSelectedFile(null);
      setContent("");
      setSavedContent("");
      return;
    }
    const preferred =
      selectedMeta.files.find((file) => file === "script.yaml" || file === "alfred.script.yaml") ??
      selectedMeta.files.find((file) => file === selectedMeta.entry) ??
      selectedMeta.files[0] ??
      null;
    if (preferred) {
      setSelectedFile(fullFilePath(selectedMeta, preferred));
    } else {
      setSelectedFile(null);
    }
  }, [selectedMeta]);

  useEffect(() => {
    if (selectedFile) {
      void loadEditor(selectedFile);
    } else {
      setContent("");
      setSavedContent("");
    }
  }, [selectedFile, loadEditor]);

  const save = async () => {
    if (!selectedFile) return;
    setSaving(true);
    try {
      await api.saveScriptFile(selectedFile, content);
      setSavedContent(content);
      notify("success", `Saved ${selectedFile}`);
      await loadList();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const createPackage = async (fromExample = false) => {
    const path = newPackagePath.trim().replace(/^\/+|\/+$/g, "");
    if (!path) {
      notify("error", "Enter a package path (e.g. checkout/daily_report)");
      return;
    }
    try {
      if (fromExample && exampleAvailable) {
        const example = await api.getScriptExample();
        const targetPath = path || example.package_path;
        await api.createScriptPackage({
          package_path: targetPath,
          runtime: "python3",
          description: "Example daily error rollup",
          entry: "main.py",
        });
        for (const [rel, fileContent] of Object.entries(example.files)) {
          const fullPath = `${targetPath}/${rel}`.replace(/\/+/g, "/");
          await api.saveScriptFile(fullPath, fileContent);
        }
        setNewOpen(false);
        setNewPackagePath("");
        await loadList();
        setSelectedPackage(targetPath);
        notify("success", `Created ${targetPath} from example`);
        return;
      }

      const result = await api.createScriptPackage({
        package_path: path,
        runtime: newRuntime,
        description: newDescription.trim() || "Company script package",
        entry: newEntry.trim() || "main.py",
      });
      setNewOpen(false);
      setNewPackagePath("");
      await loadList();
      setSelectedPackage(result.package.name);
      notify("success", `Created ${result.package.name}`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Create failed");
    }
  };

  const addFile = async () => {
    if (!selectedMeta) return;
    const rel = newFilePath.trim().replace(/^\/+/, "");
    if (!rel) {
      notify("error", "Enter a file path relative to the package");
      return;
    }
    const fullPath = fullFilePath(selectedMeta, rel);
    try {
      await api.createScriptFile(fullPath);
      setAddFileOpen(false);
      setNewFilePath("");
      await loadList();
      setSelectedFile(fullPath);
      notify("success", `Added ${rel}`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Add file failed");
    }
  };

  const removePackage = async (name: string) => {
    try {
      await api.deleteScriptPackage(name);
      notify("success", `Deleted ${name}`);
      if (selectedPackage === name) {
        setSelectedPackage(null);
        setSelectedFile(null);
      }
      await loadList();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Delete failed");
    }
  };

  const removeFile = async (relativePath: string) => {
    try {
      await api.deleteScriptPath(relativePath);
      notify("success", `Deleted ${relativePath}`);
      if (selectedFile === relativePath) {
        setSelectedFile(null);
      }
      await loadList();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div>
      <Typography.Title level={3} className="alfred-page-title">
        Scripts
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Company script packages under{" "}
        <Typography.Text code>{directory || `${dataDir}/scripts`}</Typography.Text>. Each package has a{" "}
        <Typography.Text code>script.yaml</Typography.Text> manifest, one entry point, and optional helper
        files. Referenced from playbooks via <Typography.Text code>scripts:</Typography.Text> and invoked with{" "}
        <Typography.Text code>run_company_script</Typography.Text>.
      </Typography.Paragraph>

      <Flex gap={8} wrap="wrap" style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setNewOpen(true)}>
          New package
        </Button>
        {selectedMeta ? (
          <Button icon={<FileAddOutlined />} onClick={() => setAddFileOpen(true)}>
            Add file
          </Button>
        ) : null}
        <Input.Search
          allowClear
          placeholder="Search packages…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ width: 260 }}
        />
      </Flex>

      <Flex gap={16} align="stretch" className="alfred-playbooks-layout">
        <div className="alfred-playbooks-list">
          <Typography.Text strong style={{ display: "block", marginBottom: 8 }}>
            Packages
          </Typography.Text>
          <div className="alfred-playbooks-list-scroll">
            {loading ? (
              <Typography.Text type="secondary">Loading…</Typography.Text>
            ) : groupedPackages.length === 0 ? (
              <Empty description={search ? "No matches" : "No script packages yet"} />
            ) : (
              groupedPackages.map((group) => (
                <div key={group.folder} className="alfred-playbooks-group">
                  <Typography.Text type="secondary" className="alfred-playbooks-group-label">
                    {group.folder}
                  </Typography.Text>
                  <div className="alfred-playbooks-group-items">
                    {group.items.map((item) => {
                      const active = item.name === selectedPackage;
                      return (
                        <div
                          key={item.name}
                          className={active ? "alfred-playbooks-row-active" : "alfred-playbooks-row"}
                          onClick={() => setSelectedPackage(item.name)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") setSelectedPackage(item.name);
                          }}
                        >
                          <div className="alfred-playbooks-row-main">
                            <Typography.Text strong ellipsis className="alfred-playbooks-row-title">
                              {packageLeaf(item.name)}
                            </Typography.Text>
                            {item.name.includes("/") ? (
                              <Typography.Text type="secondary" ellipsis className="alfred-playbooks-row-path">
                                {item.name}
                              </Typography.Text>
                            ) : null}
                            <div className="alfred-playbooks-row-tags">
                              <Tag>{item.runtime}</Tag>
                              {item.file_count > 1 ? <Tag>{item.file_count} files</Tag> : null}
                              {item.kind === "legacy" ? <Tag>legacy</Tag> : null}
                            </div>
                          </div>
                          <Popconfirm
                            title={`Delete package ${item.name}?`}
                            onConfirm={(event) => {
                              event?.stopPropagation();
                              void removePackage(item.name);
                            }}
                            onPopupClick={(event) => event.stopPropagation()}
                          >
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              className="alfred-playbooks-row-delete"
                              onClick={(event) => event.stopPropagation()}
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
          {!selectedMeta ? (
            <Empty description="Select a package" />
          ) : (
            <>
              <Flex justify="space-between" align="flex-start" wrap="wrap" gap={8} style={{ marginBottom: 12 }}>
                <div className="alfred-playbooks-editor-meta">
                  <Typography.Text strong>{selectedMeta.name}</Typography.Text>
                  <Typography.Text type="secondary" className="alfred-playbooks-editor-path">
                    entry {selectedMeta.entry} · {selectedMeta.description || "No description"}
                  </Typography.Text>
                  {selectedMeta.args.length > 0 ? (
                    <div className="alfred-playbooks-row-tags" style={{ marginTop: 6 }}>
                      {selectedMeta.args.map((arg) => (
                        <Tag key={arg.name}>
                          {arg.name}
                          {arg.required ? " *" : ""}
                        </Tag>
                      ))}
                    </div>
                  ) : null}
                </div>
                <Space wrap>
                  <Button
                    type="primary"
                    icon={<SaveOutlined />}
                    disabled={!selectedFile || !dirty || editorLoading}
                    loading={saving}
                    onClick={() => void save()}
                  >
                    Save
                  </Button>
                </Space>
              </Flex>

              <Flex gap={12} align="stretch" className="alfred-scripts-editor-split">
                <div className="alfred-scripts-file-list">
                  <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
                    Files
                  </Typography.Text>
                  {selectedMeta.files.map((file) => {
                    const fullPath = fullFilePath(selectedMeta, file);
                    const active = fullPath === selectedFile;
                    const isEntry = file === selectedMeta.entry;
                    const isManifest = file === "script.yaml" || file === "alfred.script.yaml";
                    return (
                      <div
                        key={file}
                        className={active ? "alfred-scripts-file-row-active" : "alfred-scripts-file-row"}
                        onClick={() => setSelectedFile(fullPath)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") setSelectedFile(fullPath);
                        }}
                      >
                        <Flex justify="space-between" align="center" gap={8}>
                          <div style={{ minWidth: 0 }}>
                            <Typography.Text ellipsis style={{ display: "block" }}>
                              {file}
                            </Typography.Text>
                            <Space size={4}>
                              {isManifest ? <Tag color="blue">manifest</Tag> : null}
                              {isEntry ? <Tag color="green">entry</Tag> : null}
                            </Space>
                          </div>
                          {!isEntry && !isManifest ? (
                            <Popconfirm
                              title={`Delete ${file}?`}
                              onConfirm={(event) => {
                                event?.stopPropagation();
                                void removeFile(fullPath);
                              }}
                              onPopupClick={(event) => event.stopPropagation()}
                            >
                              <Button
                                type="text"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={(event) => event.stopPropagation()}
                              />
                            </Popconfirm>
                          ) : null}
                        </Flex>
                      </div>
                    );
                  })}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  {selectedFile ? (
                    <>
                      <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
                        {selectedFile}
                      </Typography.Text>
                      <TextArea
                        value={content}
                        onChange={(event) => setContent(event.target.value)}
                        autoSize={{ minRows: 22, maxRows: 40 }}
                        className="alfred-playbooks-textarea"
                        spellCheck={false}
                        disabled={editorLoading}
                      />
                    </>
                  ) : (
                    <Empty description="No files in package" />
                  )}
                </div>
              </Flex>
            </>
          )}
        </div>
      </Flex>

      <Modal
        title="New script package"
        open={newOpen}
        onCancel={() => setNewOpen(false)}
        footer={[
          exampleAvailable ? (
            <Button key="example" onClick={() => void createPackage(true)}>
              From example
            </Button>
          ) : null,
          <Button key="cancel" onClick={() => setNewOpen(false)}>
            Cancel
          </Button>,
          <Button key="create" type="primary" onClick={() => void createPackage(false)}>
            Create
          </Button>,
        ]}
      >
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          <div>
            <Typography.Text>Package path</Typography.Text>
            <Input
              placeholder="checkout/daily_report"
              value={newPackagePath}
              onChange={(event) => setNewPackagePath(event.target.value)}
            />
          </div>
          <div>
            <Typography.Text>Runtime</Typography.Text>
            <Select
              style={{ width: "100%" }}
              options={RUNTIME_OPTIONS}
              value={newRuntime}
              onChange={setNewRuntime}
            />
          </div>
          <div>
            <Typography.Text>Entry file</Typography.Text>
            <Input value={newEntry} onChange={(event) => setNewEntry(event.target.value)} />
          </div>
          <div>
            <Typography.Text>Description</Typography.Text>
            <Input value={newDescription} onChange={(event) => setNewDescription(event.target.value)} />
          </div>
        </Space>
      </Modal>

      <Modal
        title="Add file to package"
        open={addFileOpen}
        onCancel={() => setAddFileOpen(false)}
        onOk={() => void addFile()}
        okText="Add"
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          Path relative to <Typography.Text code>{selectedMeta?.name ?? "package"}</Typography.Text>, e.g.{" "}
          <Typography.Text code>lib/helpers.py</Typography.Text>
        </Typography.Paragraph>
        <Input
          placeholder="lib/helpers.py"
          value={newFilePath}
          onChange={(event) => setNewFilePath(event.target.value)}
        />
      </Modal>
    </div>
  );
}
