import {
  CommentOutlined,
  DeleteOutlined,
  EditOutlined,
  LinkOutlined,
  PlusOutlined,
  SyncOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type SlackBoardBinding,
  type SlackBoardBindingInput,
  type SlackChannelWorkflow,
} from "../../api/client";
import { useApp } from "../../context/AppContext";

const TICKET_SYSTEM_OPTIONS = [
  { value: "ask", label: "Ask (Slack buttons when ambiguous)" },
  { value: "slack_list", label: "Slack List only" },
  { value: "jira", label: "JIRA only" },
];

function countDuplicates(boards: SlackBoardBinding[]) {
  const byChannel = new Map<string, number>();
  const byList = new Map<string, number>();
  for (const row of boards) {
    byChannel.set(row.channel_id, (byChannel.get(row.channel_id) || 0) + 1);
    byList.set(row.list_id, (byList.get(row.list_id) || 0) + 1);
  }
  const duplicateChannels = [...byChannel.entries()].filter(([, n]) => n > 1).map(([id]) => id);
  const duplicateLists = [...byList.entries()].filter(([, n]) => n > 1).map(([id]) => id);
  return { duplicateChannels, duplicateLists };
}

export function SlackBoardsPanel() {
  const { notify } = useApp();
  const [channels, setChannels] = useState<SlackChannelWorkflow[]>([]);
  const [boards, setBoards] = useState<SlackBoardBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [boardModalOpen, setBoardModalOpen] = useState(false);
  const [channelModalOpen, setChannelModalOpen] = useState(false);
  const [quickLinkOpen, setQuickLinkOpen] = useState(false);
  const [editingBoard, setEditingBoard] = useState<SlackBoardBinding | null>(null);
  const [editingChannel, setEditingChannel] = useState<SlackChannelWorkflow | null>(null);
  const [boardForm] = Form.useForm();
  const [channelForm] = Form.useForm();
  const [quickLinkForm] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [repairing, setRepairing] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [ch, bd] = await Promise.all([
        api.listSlackChannelWorkflows(),
        api.listSlackBoardBindings(),
      ]);
      setChannels(ch.channels || []);
      setBoards(bd.boards || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", `Failed to load Slack workflows: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const duplicates = useMemo(() => countDuplicates(boards), [boards]);
  const hasDuplicates =
    duplicates.duplicateChannels.length > 0 || duplicates.duplicateLists.length > 0;

  const openBoardModal = (record?: SlackBoardBinding) => {
    setEditingBoard(record || null);
    boardForm.setFieldsValue(
      record
        ? {
            ...record,
            title_column: record.columns?.title,
            status_column: record.columns?.status,
            details_column: record.columns?.details,
            display_id_column: record.columns?.display_id,
          }
        : {
            board_key: "",
            display_id_prefix: "TS",
            next_display_num: 1,
            default_status: "Not picked",
            enabled: true,
            auto_approve_writes: false,
            title_column: "Name",
            status_column: "Status",
            details_column: "Ticket Details",
            display_id_column: "",
          },
    );
    setBoardModalOpen(true);
  };

  const saveBoard = async () => {
    const values = await boardForm.validateFields();
    setSaving(true);
    try {
      const listId = String(values.list_id || "").trim();
      const channelId = String(values.channel_id || "").trim();
      if (!editingBoard || listId !== editingBoard.list_id) {
        await api.verifySlackBoardListId(listId, channelId);
      }
      const body: SlackBoardBindingInput = {
        board_key: values.board_key,
        list_id: values.list_id,
        channel_id: values.channel_id,
        channel_name: values.channel_name || "",
        list_name: values.list_name || "",
        display_id_prefix: values.display_id_prefix,
        next_display_num: values.next_display_num,
        default_status: values.default_status,
        auto_approve_writes: values.auto_approve_writes,
        enabled: values.enabled,
        columns: {
          title: values.title_column,
          status: values.status_column,
          details: values.details_column,
          display_id: values.display_id_column || "",
        },
      };
      if (editingBoard) {
        await api.updateSlackBoardBinding(editingBoard.id, body);
        notify("success", "Board binding updated.");
      } else {
        await api.createSlackBoardBinding(body);
        notify("success", "Board binding created.");
      }
      setBoardModalOpen(false);
      refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", message);
    } finally {
      setSaving(false);
    }
  };

  const saveQuickLink = async () => {
    const values = await quickLinkForm.validateFields();
    setSaving(true);
    try {
      const channelId = String(values.channel_id || "").trim();
      const listId = String(values.list_id || "").trim();
      await api.verifySlackBoardListId(listId, channelId);
      const existing = boards.filter((b) => b.channel_id === channelId);
      if (existing.length > 0) {
        await api.deleteSlackBoardBindingsForChannel(channelId);
      }
      await api.createSlackBoardBinding({
        board_key: values.board_key || values.channel_name || channelId,
        list_id: listId,
        channel_id: channelId,
        channel_name: values.channel_name || "",
        display_id_prefix: values.display_id_prefix || "TS",
        next_display_num: 1,
        default_status: "Not picked",
        enabled: true,
      });
      notify("success", "Channel linked to Slack List.");
      setQuickLinkOpen(false);
      quickLinkForm.resetFields();
      refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", message);
    } finally {
      setSaving(false);
    }
  };

  const unlinkChannel = async (channelId: string) => {
    try {
      const result = await api.deleteSlackBoardBindingsForChannel(channelId);
      notify("success", `Removed ${result.removed} binding(s) for channel.`);
      refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", message);
    }
  };

  const repairDuplicates = async () => {
    setRepairing(true);
    try {
      const result = await api.dedupeSlackBoardBindings();
      notify(
        "success",
        result.duplicate_rows_removed > 0
          ? `Removed ${result.duplicate_rows_removed} duplicate row(s). ${result.boards} binding(s) remain.`
          : `No duplicate rows found. ${result.boards} binding(s) in database.`,
      );
      refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", message);
    } finally {
      setRepairing(false);
    }
  };

  const openChannelModal = (record?: SlackChannelWorkflow) => {
    setEditingChannel(record || null);
    channelForm.setFieldsValue(
      record || {
        channel_id: "",
        channel_name: "",
        ticket_system: "ask",
        jira_project_key: "",
        enabled: true,
      },
    );
    setChannelModalOpen(true);
  };

  const saveChannel = async () => {
    const values = await channelForm.validateFields();
    setSaving(true);
    try {
      await api.upsertSlackChannelWorkflow(values.channel_id, {
        channel_name: values.channel_name,
        ticket_system: values.ticket_system,
        jira_project_key: values.jira_project_key,
        enabled: values.enabled,
      });
      notify("success", "Channel workflow saved.");
      setChannelModalOpen(false);
      refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      notify("error", message);
    } finally {
      setSaving(false);
    }
  };

  const boardColumns: ColumnsType<SlackBoardBinding> = [
    {
      title: "Channel",
      render: (_, r) => (
        <Space direction="vertical" size={0}>
          <span>{r.channel_name || "—"}</span>
          <Typography.Text type="secondary" code>
            {r.channel_id}
          </Typography.Text>
        </Space>
      ),
    },
    { title: "Board key", dataIndex: "board_key", width: 130 },
    {
      title: "List id",
      dataIndex: "list_id",
      ellipsis: true,
      render: (v: string, r) => (
        <Space direction="vertical" size={0}>
          <Typography.Text code>{v}</Typography.Text>
          {duplicates.duplicateLists.includes(v) && <Tag color="warning">duplicate list</Tag>}
          {duplicates.duplicateChannels.includes(r.channel_id) && (
            <Tag color="warning">duplicate channel</Tag>
          )}
        </Space>
      ),
    },
    {
      title: "Display id",
      width: 110,
      render: (_, r) => `${r.display_id_prefix}-${r.next_display_num}`,
    },
    {
      title: "Active",
      dataIndex: "enabled",
      width: 70,
      render: (v: boolean) => <Tag color={v ? "success" : "default"}>{v ? "yes" : "no"}</Tag>,
    },
    {
      title: "",
      width: 180,
      render: (_, record) => (
        <Space wrap>
          <Button type="link" icon={<EditOutlined />} onClick={() => openBoardModal(record)}>
            Edit
          </Button>
          <Popconfirm
            title={`Unlink all bindings for ${record.channel_id}?`}
            description="Removes every board binding row for this channel."
            onConfirm={() => unlinkChannel(record.channel_id)}
          >
            <Button type="link" icon={<LinkOutlined />}>
              Unlink channel
            </Button>
          </Popconfirm>
          <Popconfirm
            title="Delete this binding row?"
            onConfirm={async () => {
              await api.deleteSlackBoardBinding(record.id);
              notify("success", "Deleted.");
              refresh();
            }}
          >
            <Button type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const channelColumns: ColumnsType<SlackChannelWorkflow> = [
    {
      title: "Channel",
      render: (_, r) => r.channel_name || r.channel_id,
    },
    { title: "Channel id", dataIndex: "channel_id", ellipsis: true },
    {
      title: "Ticket system",
      dataIndex: "ticket_system",
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: "JIRA project", dataIndex: "jira_project_key", width: 120 },
    {
      title: "",
      width: 120,
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openChannelModal(record)} />
          <Popconfirm
            title="Delete channel workflow?"
            onConfirm={async () => {
              await api.deleteSlackChannelWorkflow(record.channel_id);
              notify("success", "Deleted.");
              refresh();
            }}
          >
            <Button type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="alfred-panel">
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Flex justify="space-between" align="center" wrap="wrap" gap="middle">
          <div>
            <Typography.Title level={4} style={{ margin: 0 }}>
              <CommentOutlined /> Slack boards & channels
            </Typography.Title>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              One binding per channel and per List id. Changes apply immediately — no restart.
            </Typography.Paragraph>
          </div>
          <Space wrap>
            {hasDuplicates && (
              <Button
                icon={<WarningOutlined />}
                onClick={repairDuplicates}
                loading={repairing}
                danger
              >
                Remove duplicates
              </Button>
            )}
            <Button icon={<SyncOutlined />} onClick={refresh} loading={loading}>
              Refresh
            </Button>
          </Space>
        </Flex>

        {hasDuplicates && (
          <Alert
            type="warning"
            showIcon
            message="Duplicate bindings detected"
            description={
              <>
                Channels with multiple rows:{" "}
                {duplicates.duplicateChannels.length
                  ? duplicates.duplicateChannels.map((id) => <code key={id}>{id}</code>)
                  : "none"}
                . Lists linked more than once:{" "}
                {duplicates.duplicateLists.length
                  ? duplicates.duplicateLists.map((id) => <code key={id}>{id}</code>)
                  : "none"}
                . Click <strong>Remove duplicates</strong> to keep the newest row per channel and
                List id.
              </>
            }
          />
        )}

        <Alert
          type="info"
          showIcon
          message="In Slack"
          description={
            <>
              Link: <code>@alfred link board to F…</code> · Unlink: <code>@alfred unlink</code> ·
              Config: <code>@alfred show board config</code>
            </>
          }
        />

        <Tabs
          items={[
            {
              key: "boards",
              label: `Board bindings (${boards.length})`,
              children: (
                <>
                  <Space style={{ marginBottom: 12 }} wrap>
                    <Button
                      type="primary"
                      icon={<LinkOutlined />}
                      onClick={() => {
                        quickLinkForm.resetFields();
                        setQuickLinkOpen(true);
                      }}
                    >
                      Link channel to List
                    </Button>
                    <Button icon={<PlusOutlined />} onClick={() => openBoardModal()}>
                      Advanced binding
                    </Button>
                  </Space>
                  <Table
                    rowKey="id"
                    loading={loading}
                    columns={boardColumns}
                    dataSource={boards}
                    pagination={{ pageSize: 10 }}
                  />
                </>
              ),
            },
            {
              key: "channels",
              label: "Channel workflows",
              children: (
                <>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => openChannelModal()}
                    style={{ marginBottom: 12 }}
                  >
                    Add channel workflow
                  </Button>
                  <Table
                    rowKey="channel_id"
                    loading={loading}
                    columns={channelColumns}
                    dataSource={channels}
                    pagination={{ pageSize: 10 }}
                  />
                </>
              ),
            },
          ]}
        />
      </Space>

      <Modal
        title="Link channel to Slack List"
        open={quickLinkOpen}
        onCancel={() => setQuickLinkOpen(false)}
        onOk={saveQuickLink}
        confirmLoading={saving}
        okText="Link"
      >
        <Form form={quickLinkForm} layout="vertical">
          <Form.Item
            name="channel_id"
            label="Slack channel id"
            rules={[{ required: true, message: "Required" }]}
          >
            <Input placeholder="C0BNNSMGG91" />
          </Form.Item>
          <Form.Item name="channel_name" label="Channel name (optional)">
            <Input placeholder="#tmp-board-test" />
          </Form.Item>
          <Form.Item
            name="list_id"
            label="Slack List id"
            rules={[{ required: true, message: "Required" }]}
            extra="Open the Task List tab in Slack, copy the F… id from the browser URL, paste here. Alfred verifies it before saving."
          >
            <Input placeholder="F0BNP40SLV9" />
          </Form.Item>
          <Form.Item name="board_key" label="Board key (optional)">
            <Input placeholder="Auto from channel name if empty" />
          </Form.Item>
          <Form.Item name="display_id_prefix" label="Display id prefix" initialValue="TS">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingBoard ? "Edit board binding" : "New board binding"}
        open={boardModalOpen}
        onCancel={() => setBoardModalOpen(false)}
        onOk={saveBoard}
        confirmLoading={saving}
        width={640}
      >
        <Form form={boardForm} layout="vertical">
          <Form.Item name="channel_id" label="Slack channel id" rules={[{ required: true }]}>
            <Input placeholder="C01234567" disabled={!!editingBoard} />
          </Form.Item>
          <Form.Item name="channel_name" label="Channel name (optional)">
            <Input placeholder="#tech-support" />
          </Form.Item>
          <Form.Item name="board_key" label="Board key" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="list_id" label="Slack List id" rules={[{ required: true }]}>
            <Input placeholder="F0BNP40SLV9" />
          </Form.Item>
          <Form.Item name="list_name" label="List name (optional)">
            <Input placeholder="Task List" />
          </Form.Item>
          <Flex gap="middle">
            <Form.Item name="display_id_prefix" label="Display id prefix" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item name="next_display_num" label="Next number" style={{ flex: 1 }}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
          </Flex>
          <Form.Item name="default_status" label="Default status">
            <Input />
          </Form.Item>
          <Form.Item name="title_column" label="Title column name">
            <Input />
          </Form.Item>
          <Form.Item name="status_column" label="Status column name">
            <Input />
          </Form.Item>
          <Form.Item name="details_column" label="Details column name">
            <Input />
          </Form.Item>
          <Form.Item name="display_id_column" label="Display id column (optional)">
            <Input placeholder="Leave empty to skip writing TS-N to list" />
          </Form.Item>
          <Form.Item name="auto_approve_writes" label="Auto-approve board writes" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingChannel ? "Edit channel workflow" : "New channel workflow"}
        open={channelModalOpen}
        onCancel={() => setChannelModalOpen(false)}
        onOk={saveChannel}
        confirmLoading={saving}
      >
        <Form form={channelForm} layout="vertical">
          <Form.Item name="channel_id" label="Slack channel id" rules={[{ required: true }]}>
            <Input disabled={!!editingChannel} />
          </Form.Item>
          <Form.Item name="channel_name" label="Channel name">
            <Input />
          </Form.Item>
          <Form.Item name="ticket_system" label="Default ticket system">
            <Select options={TICKET_SYSTEM_OPTIONS} />
          </Form.Item>
          <Form.Item name="jira_project_key" label="JIRA project key (optional)">
            <Input placeholder="TS" />
          </Form.Item>
          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
