import {
  DeleteOutlined,
  CalendarOutlined,
  PlayCircleOutlined,
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
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, type ScheduledJob } from "../../api/client";
import { useApp } from "../../context/AppContext";

export function SchedulesPanel() {
  const { notify } = useApp();
  const [schedules, setSchedules] = useState<ScheduledJob[]>([]);
  const [loading, setLoading] = useState(true);

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

  const handleDelete = async (jobId: string) => {
    try {
      await api.deleteSchedule(jobId);
      notify("success", "Successfully deleted scheduled job.");
      setSchedules((prev) => prev.filter((job) => job.id !== jobId));
    } catch (err: any) {
      notify("error", `Failed to delete schedule: ${err.message || err}`);
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
      render: (text: string) => (
        <Tag icon={<CalendarOutlined />} color="default" style={{ padding: "2px 8px" }}>
          <code>{text}</code>
        </Tag>
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
        <Popconfirm
          title="Delete Schedule"
          description="Are you sure you want to delete this scheduled job? This will also delete the associated custom skill playbook file."
          onConfirm={() => handleDelete(record.id)}
          okText="Yes"
          cancelText="No"
        >
          <Button type="text" danger icon={<DeleteOutlined />} size="small" />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div style={{ padding: "24px", background: "var(--alfred-bg-component, #ffffff)", borderRadius: "8px" }}>
      <Flex justify="space-between" align="center" style={{ marginBottom: "24px" }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Scheduled Automations
          </Typography.Title>
          <Typography.Text type="secondary">
            Manage background cron tasks and auto-generated playbook executions.
          </Typography.Text>
        </div>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
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
  );
}
