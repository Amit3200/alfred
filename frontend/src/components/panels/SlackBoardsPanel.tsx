import {
  CommentOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SyncOutlined,
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
import { useCallback, useEffect, useState } from "react";
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

export function SlackBoardsPanel() {
  const { notify } = useApp();
  const [channels, setChannels] = useState<SlackChannelWorkflow[]>([]);
  const [boards, setBoards] = useState<SlackBoardBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [boardModalOpen, setBoardModalOpen] = useState(false);
  const [channelModalOpen, setChannelModalOpen] = useState(false);
  const [editingBoard, setEditingBoard] = useState<SlackBoardBinding | null>(null);
  const [editingChannel, setEditingChannel] = useState<SlackChannelWorkflow | null>(null);
  const [boardForm] = Form.useForm();
  const [channelForm] = Form.useForm();
  const [saving, setSaving] = useState(false);

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
            board_key: "bugs-tracker",
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
      render: (_, r) => r.channel_name || r.channel_id,
    },
    { title: "Board key", dataIndex: "board_key", width: 140 },
    { title: "List id", dataIndex: "list_id", ellipsis: true },
    {
      title: "Display id",
      width: 120,
      render: (_, r) => `${r.display_id_prefix}-${r.next_display_num}`,
    },
    { title: "Status", dataIndex: "default_status", width: 110 },
    {
      title: "Active",
      dataIndex: "enabled",
      width: 80,
      render: (v: boolean) => <Tag color={v ? "success" : "default"}>{v ? "yes" : "no"}</Tag>,
    },
    {
      title: "",
      width: 120,
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openBoardModal(record)} />
          <Popconfirm
            title="Delete this board binding?"
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
              Runtime configuration stored in Alfred&apos;s database — no restart required.
            </Typography.Paragraph>
          </div>
          <Button icon={<SyncOutlined />} onClick={refresh} loading={loading}>
            Refresh
          </Button>
        </Flex>

        <Alert
          type="info"
          showIcon
          message="In Slack"
          description={
            <>
              Link a channel: <code>@alfred link board to F0123…</code> · Show config:{" "}
              <code>@alfred show board config</code> · Set prefix:{" "}
              <code>@alfred set display prefix TS</code> · Ticket system:{" "}
              <code>@alfred set ticket system ask|slack|jira</code>
            </>
          }
        />

        <Tabs
          items={[
            {
              key: "boards",
              label: "Board bindings",
              children: (
                <>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => openBoardModal()}
                    style={{ marginBottom: 12 }}
                  >
                    Add board binding
                  </Button>
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
            <Input placeholder="F01234567" />
          </Form.Item>
          <Form.Item name="list_name" label="List name (optional)">
            <Input placeholder="Bugs tracker" />
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
