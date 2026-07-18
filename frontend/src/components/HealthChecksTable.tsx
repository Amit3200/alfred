import { Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  type HealthCheck,
  serviceLabel,
  sortHealthCheckEntries,
} from "../health";

function StatusTag({ check }: { check: HealthCheck }) {
  if (check.skipped) {
    return <Tag className="alfred-health-tag">skipped</Tag>;
  }
  if (check.ok) {
    return (
      <Tag color="success" className="alfred-health-tag">
        ok
      </Tag>
    );
  }
  return (
    <Tag color="error" className="alfred-health-tag">
      fail
    </Tag>
  );
}

type Row = { key: string; service: string; check: HealthCheck };

type HealthChecksTableProps = {
  checks: Record<string, HealthCheck>;
  compact?: boolean;
};

export function HealthChecksTable({ checks, compact = false }: HealthChecksTableProps) {
  const data: Row[] = sortHealthCheckEntries(checks).map(([key, check]) => ({
    key,
    service: serviceLabel(key),
    check,
  }));

  const columns: ColumnsType<Row> = [
    {
      title: "Service",
      dataIndex: "service",
      key: "service",
      width: compact ? 120 : 160,
      render: (service: string) => <span className="alfred-health-service">{service}</span>,
    },
    {
      title: "Status",
      key: "status",
      width: 100,
      render: (_, row) => <StatusTag check={row.check} />,
    },
    {
      title: "Details",
      key: "message",
      render: (_, row) => (
        <span className="alfred-health-message">{row.check.message ?? "—"}</span>
      ),
    },
  ];

  return (
    <Table
      className="alfred-health-table"
      columns={columns}
      dataSource={data}
      pagination={false}
      size={compact ? "small" : "middle"}
      rowKey="key"
    />
  );
}

export type { HealthCheck };
export { serviceLabel };
export { statusLabel } from "../health";
