import {
  DeleteOutlined,
  CalendarOutlined,
  PlayCircleOutlined,
  EditOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Button,
  Empty,
  Flex,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Modal,
  Form,
  Input,
  Select,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, type ScheduledJob } from "../../api/client";
import { useApp } from "../../context/AppContext";

export function SchedulesPanel() {
  const { notify } = useApp();
  const [schedules, setSchedules] = useState<ScheduledJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null);
  const [form] = Form.useForm();
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listSchedules();
      setSchedules(res.schedules || []);
    } catch (err: any) {
      notify("error", `Failed to load scheduled jobs: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    fetchSchedules();
  }, [fetchSchedules]);

  const handleToggle = async (jobId: string, checked: boolean) => {
    try {
      await api.toggleSchedule(jobId, checked);
      notify("success", `Successfully ${checked ? "enabled" : "disabled"} schedule.`);
      setSchedules((prev) =>
        prev.map((job) =>
          job.id === jobId ? { ...job, status: checked ? "active" : "inactive" } : job
        )
      );
    } catch (err: any) {
      notify("error", `Failed to update schedule status: ${err.message || err}`);
    }
  };

  const handleTrigger = async (jobId: string) => {
    try {
      await api.triggerSchedule(jobId);
      notify("success", "Successfully triggered schedule on demand.");
      fetchSchedules();
    } catch (err: any) {
      notify("error", `Failed to trigger schedule: ${err.message || err}`);
    }
  };

  const handleDelete = async (jobId: string) => {
    try {
      await api.deleteSchedule(jobId);
      notify("success", "Successfully deleted scheduled job.");
      setSchedules((prev) => prev.filter((job) => job.id !== jobId));
    } catch (err: any) {
      notify("error", `Failed to delete schedule: ${err.message || err}`);
    }
  };

  const handleEditClick = async (record: ScheduledJob) => {
    try {
      setLoading(true);
      const detail = await api.getSchedule(record.id);
      setEditingJob(detail);
      form.setFieldsValue({
        name: detail.name,
        cron_expression: detail.cron_expression,
        channel_id: detail.channel_id || "",
        instructions: detail.instructions || "",
        timezone: detail.timezone || "Asia/Kolkata",
      });
      setEditModalOpen(true);
    } catch (err: any) {
      notify("error", `Failed to load schedule details: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  };

  const handleEditSave = async () => {
    if (!editingJob) return;
    try {
      const values = await form.validateFields();
      setSavingEdit(true);
      await api.updateSchedule(editingJob.id, {
        name: values.name,
        cron_expression: values.cron_expression,
        channel_id: values.channel_id || null,
        instructions: values.instructions,
        timezone: values.timezone,
      });
      notify("success", "Successfully updated scheduled job.");
      setEditModalOpen(false);
      setEditingJob(null);
      form.resetFields();
      fetchSchedules();
    } catch (err: any) {
      notify("error", `Failed to save changes: ${err.message || err}`);
    } finally {
      setSavingEdit(false);
    }
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (text: string, record: ScheduledJob) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong style={{ fontSize: "14px" }}>
            {text}
          </Typography.Text>
          {record.description && (
            <Typography.Text type="secondary" style={{ fontSize: "12px" }}>
              {record.description}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: "Cron Expression",
      dataIndex: "cron_expression",
      key: "cron_expression",
      render: (text: string, record: ScheduledJob) => (
        <Space size="small">
          <Tag icon={<CalendarOutlined />} color="default" style={{ padding: "2px 8px" }}>
            <code>{text}</code>
          </Tag>
          <Tag color="blue">{record.timezone || "Asia/Kolkata"}</Tag>
        </Space>
      ),
    },
    {
      title: "Target Skill",
      dataIndex: "skill_name",
      key: "skill_name",
      render: (text: string) => (
        <Typography.Text code style={{ color: "var(--alfred-primary)" }}>
          {text}
        </Typography.Text>
      ),
    },
    {
      title: "Slack Destination",
      dataIndex: "channel_id",
      key: "channel_id",
      render: (text: string | null) => (
        <Typography.Text type={text ? "success" : "secondary"}>
          {text ? `#${text}` : "None"}
        </Typography.Text>
      ),
    },
    {
      title: "Last Run Status",
      key: "last_run",
      render: (record: ScheduledJob) => {
        if (!record.last_run_at) {
          return <Typography.Text type="secondary">—</Typography.Text>;
        }
        const dateStr = new Date(record.last_run_at * 1000).toLocaleString();
        let color = "default";
        if (record.last_run_status === "success") color = "success";
        if (record.last_run_status === "failed") color = "error";
        if (record.last_run_status === "triggered") color = "processing";

        return (
          <Space size="small">
            <Tag color={color} style={{ textTransform: "capitalize" }}>
              {record.last_run_status}
            </Tag>
            <Typography.Text type="secondary" style={{ fontSize: "12px" }}>
              {dateStr}
            </Typography.Text>
          </Space>
        );
      },
    },
    {
      title: "Active",
      dataIndex: "status",
      key: "status",
      align: "center" as const,
      render: (status: string, record: ScheduledJob) => (
        <Switch
          checked={status === "active"}
          onChange={(checked) => handleToggle(record.id, checked)}
          size="small"
        />
      ),
    },
    {
      title: "Action",
      key: "action",
      align: "center" as const,
      render: (record: ScheduledJob) => (
        <Space size="middle">
          <Popconfirm
            title="Trigger Job"
            description="Are you sure you want to run this scheduled job right now on demand?"
            onConfirm={() => handleTrigger(record.id)}
            okText="Yes"
            cancelText="No"
          >
            <Button
              type="text"
              icon={<PlayCircleOutlined style={{ color: "var(--alfred-primary, #1890ff)" }} />}
              size="small"
              title="Run job on demand"
            />
          </Popconfirm>
          <Button
            type="text"
            icon={<EditOutlined />}
            size="small"
            onClick={() => handleEditClick(record)}
            title="Edit scheduled job"
          />
          <Popconfirm
            title="Delete Schedule"
            description="Are you sure you want to delete this scheduled job? This will also delete the associated custom skill playbook file."
            onConfirm={() => handleDelete(record.id)}
            okText="Yes"
            cancelText="No"
          >
            <Button type="text" danger icon={<DeleteOutlined />} size="small" title="Delete scheduled job" />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        Schedules
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Manage background cron tasks, auto-generated playbooks, and execution history. Note: All cron expressions evaluate in the job's specified timezone (Default: Asia/Kolkata / IST).
      </Typography.Paragraph>

      <div className="alfred-panel">
        <Flex justify="space-between" align="center" style={{ marginBottom: "24px" }}>
          <div>
            <Typography.Title level={4} style={{ margin: 0, color: "var(--alfred-text)" }}>
              Scheduled Automations
            </Typography.Title>
            <Typography.Text type="secondary">
              List of configured active and inactive recurring jobs.
            </Typography.Text>
          </div>
          <Button
            type="primary"
            icon={<SyncOutlined />}
            onClick={fetchSchedules}
            loading={loading}
          >
            Refresh
          </Button>
        </Flex>

        <Table
          dataSource={schedules}
          columns={columns}
          rowKey="id"
          loading={loading}
          locale={{
            emptyText: (
              <Empty
                description="No scheduled automations found"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
        />
      </div>

      <Modal
        title="Edit Scheduled Job"
        open={editModalOpen}
        onOk={handleEditSave}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingJob(null);
          form.resetFields();
        }}
        confirmLoading={savingEdit}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="Job Name"
            rules={[{ required: true, message: "Please enter a job name" }]}
          >
            <Input placeholder="e.g. daily_grade_report" />
          </Form.Item>

          <Form.Item
            name="cron_expression"
            label="Cron Expression"
            rules={[{ required: true, message: "Please enter a cron pattern" }]}
            help="Standard 5-field cron pattern (e.g. '0 9 * * 1-5' or '*/10 * * * *')"
          >
            <Input placeholder="e.g. 0 9 * * 1-5" />
          </Form.Item>

          <Form.Item
            name="channel_id"
            label="Slack Destination (Channel ID)"
            help="Slack channel ID to post results (e.g. C0123456789). Leave blank to disable."
          >
            <Input placeholder="e.g. C0123456789" />
          </Form.Item>

          <Form.Item
            name="timezone"
            label="Execution Timezone"
            rules={[{ required: true, message: "Please select a timezone" }]}
            help="The timezone used to evaluate the cron expression. Default is Asia/Kolkata (IST)."
          >
            <Select
              options={[
                { label: "Asia/Kolkata (IST)", value: "Asia/Kolkata" },
                { label: "Coordinated Universal Time (UTC)", value: "UTC" },
                { label: "America/New_York (EST/EDT)", value: "America/New_York" },
                { label: "Europe/London (GMT/BST)", value: "Europe/London" },
                { label: "Asia/Singapore (SGT)", value: "Asia/Singapore" },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="instructions"
            label="Objective / Instructions"
            rules={[{ required: true, message: "Please enter playbook instructions" }]}
          >
            <Input.TextArea
              rows={8}
              placeholder="What this scheduled playbook job should perform..."
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
