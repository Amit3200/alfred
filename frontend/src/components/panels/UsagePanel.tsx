import { Button, Col, Row, Select, Table, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type ObservabilityEvent,
  type ObservabilitySummary,
  type ObservabilityTimeseries,
} from "../../api/client";

type Preset = "24h" | "7d" | "30d" | "month";
type Bucket = "hour" | "day" | "month";

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

function formatPeriod(period: string, bucket: Bucket): string {
  if (bucket === "hour") {
    const date = new Date(period.replace(" ", "T") + ":00:00Z");
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" });
    }
  }
  if (bucket === "day") {
    const date = new Date(period + "T00:00:00Z");
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }
  }
  if (bucket === "month" && /^\d{4}-\d{2}$/.test(period)) {
    const [year, month] = period.split("-");
    const date = new Date(Number(year), Number(month) - 1, 1);
    return date.toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }
  return period.replace("T", " ");
}

function niceTicks(max: number): number[] {
  if (max <= 0) return [0];
  if (max <= 4) return Array.from({ length: max + 1 }, (_, index) => index);
  const step = max <= 10 ? 2 : max <= 50 ? 10 : max <= 200 ? 25 : Math.ceil(max / 4 / 10) * 10;
  const ticks: number[] = [0];
  for (let value = step; value < max; value += step) ticks.push(value);
  if (ticks[ticks.length - 1] !== max) ticks.push(max);
  return ticks;
}

function UsageBarChart({
  title,
  points,
  metric,
  bucket,
}: {
  title: string;
  points: ObservabilityTimeseries["points"];
  metric: "llm_calls" | "tool_calls" | "total_tokens";
  bucket: Bucket;
}) {
  const values = useMemo(() => points.map((point) => point[metric] ?? 0), [points, metric]);
  const max = useMemo(() => Math.max(...values, 0), [values]);
  const total = useMemo(() => values.reduce((sum, value) => sum + value, 0), [values]);
  const ticks = useMemo(() => niceTicks(max), [max]);
  const scaleMax = ticks[ticks.length - 1] || 1;

  if (!points.length) {
    return (
      <div className="alfred-usage-chart-panel">
        <Typography.Title level={5}>{title}</Typography.Title>
        <Typography.Text type="secondary">No data for this range.</Typography.Text>
      </div>
    );
  }

  return (
    <div className="alfred-usage-chart-panel">
      <div className="alfred-usage-chart-header">
        <Typography.Title level={5} style={{ margin: 0 }}>
          {title}
        </Typography.Title>
        <Typography.Text type="secondary" className="alfred-usage-chart-total">
          Total {formatNumber(total)}
        </Typography.Text>
      </div>
      <div className="alfred-usage-chart-body">
        <div className="alfred-usage-y-axis">
          {[...ticks].reverse().map((tick) => (
            <span key={tick}>{formatNumber(tick)}</span>
          ))}
        </div>
        <div className="alfred-usage-plot">
          <div className="alfred-usage-grid">
            {ticks.map((tick) => (
              <div
                key={tick}
                className="alfred-usage-grid-line"
                style={{ bottom: `${(tick / scaleMax) * 100}%` }}
              />
            ))}
          </div>
          <div className="alfred-usage-bars">
            {points.map((point) => {
              const value = point[metric] ?? 0;
              const height = scaleMax > 0 ? (value / scaleMax) * 100 : 0;
              return (
                <div key={point.period} className="alfred-usage-bar-wrap">
                  <span className="alfred-usage-bar-value">{formatNumber(value)}</span>
                  <div className="alfred-usage-bar-track">
                    <div
                      className="alfred-usage-bar"
                      style={{ height: `${Math.max(value > 0 ? 6 : 0, height)}%` }}
                      title={`${formatPeriod(point.period, bucket)}: ${formatNumber(value)}`}
                    />
                  </div>
                  <span className="alfred-usage-bar-label">{formatPeriod(point.period, bucket)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function BreakdownChart({
  title,
  entries,
}: {
  title: string;
  entries: Array<[string, number]>;
}) {
  const max = Math.max(1, ...entries.map(([, value]) => value));

  if (!entries.length) {
    return (
      <div className="alfred-panel">
        <Typography.Title level={5}>{title}</Typography.Title>
        <Typography.Text type="secondary">No data for this range.</Typography.Text>
      </div>
    );
  }

  return (
    <div className="alfred-panel">
      <Typography.Title level={5}>{title}</Typography.Title>
      <div className="alfred-usage-breakdown">
        {entries.map(([label, value]) => (
          <div key={label} className="alfred-usage-breakdown-row">
            <div className="alfred-usage-breakdown-label">{label}</div>
            <div className="alfred-usage-breakdown-bar-wrap">
              <div
                className="alfred-usage-breakdown-bar"
                style={{ width: `${Math.max(4, (value / max) * 100)}%` }}
              />
            </div>
            <div className="alfred-usage-breakdown-value">{formatNumber(value)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function UserCell({ row }: { row: ObservabilityEvent }) {
  const primary = row.user_display_name || row.user_label || row.user_id || "unknown";
  const secondary =
    row.user_id && row.user_id !== primary && row.user_id !== row.user_display_name
      ? row.user_id
      : undefined;
  return (
    <div className="alfred-usage-user-cell">
      <span>{primary}</span>
      {secondary ? (
        <Typography.Text type="secondary" className="alfred-usage-user-sub">
          {secondary}
        </Typography.Text>
      ) : null}
    </div>
  );
}

export function UsagePanel() {
  const [preset, setPreset] = useState<Preset>("7d");
  const [bucket, setBucket] = useState<Bucket>("day");
  const [source, setSource] = useState<string | undefined>();
  const [user, setUser] = useState<string | undefined>();
  const [model, setModel] = useState<string | undefined>();
  const [eventType, setEventType] = useState<"llm_call" | "tool_call" | undefined>();
  const [toolCategory, setToolCategory] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [timeseries, setTimeseries] = useState<ObservabilityTimeseries | null>(null);
  const [events, setEvents] = useState<ObservabilityEvent[]>([]);
  const [filterOptions, setFilterOptions] = useState<{
    sources: string[];
    users: string[];
    models: string[];
    tool_categories: string[];
  }>({ sources: [], users: [], models: [], tool_categories: [] });

  const query = useMemo(
    () => ({
      preset,
      bucket,
      source,
      user,
      model,
      event_type: eventType,
      tool_category: toolCategory,
    }),
    [preset, bucket, source, user, model, eventType, toolCategory],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryRes, seriesRes, eventsRes, filtersRes] = await Promise.all([
        api.observabilitySummary(query),
        api.observabilityTimeseries(query),
        api.observabilityEvents({ ...query, limit: 50 }),
        api.observabilityFilters("30d"),
      ]);
      setSummary(summaryRes.summary);
      setTimeseries(seriesRes.timeseries);
      setEvents(eventsRes.events);
      setFilterOptions(filtersRes);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const byUserEntries = useMemo(
    () => Object.entries(summary?.by_user ?? {}).sort((a, b) => b[1] - a[1]),
    [summary],
  );
  const bySourceEntries = useMemo(
    () => Object.entries(summary?.by_source ?? {}).sort((a, b) => b[1] - a[1]),
    [summary],
  );
  const byModelEntries = useMemo(
    () => Object.entries(summary?.by_model ?? {}).sort((a, b) => b[1] - a[1]),
    [summary],
  );

  const columns = [
    {
      title: "Time",
      dataIndex: "recorded_at",
      key: "recorded_at",
      render: (value: string) => formatWhen(value),
      width: 170,
    },
    {
      title: "Type",
      dataIndex: "event_type",
      key: "event_type",
      width: 90,
    },
    {
      title: "Source",
      dataIndex: "source",
      key: "source",
      width: 80,
    },
    {
      title: "User",
      key: "user",
      width: 150,
      render: (_: unknown, row: ObservabilityEvent) => <UserCell row={row} />,
    },
    {
      title: "Model / Tool",
      key: "detail",
      render: (_: unknown, row: ObservabilityEvent) =>
        row.event_type === "llm_call"
          ? `${row.provider || "?"} · ${row.model || "?"}`
          : `${row.tool_category || "?"} · ${row.tool_name || "?"}`,
    },
    {
      title: "Tokens",
      dataIndex: "total_tokens",
      key: "total_tokens",
      width: 90,
      render: (value: number, row: ObservabilityEvent) =>
        row.event_type === "llm_call" ? formatNumber(value || 0) : "—",
    },
    {
      title: "Kind",
      dataIndex: "call_kind",
      key: "call_kind",
      width: 110,
    },
  ];

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        Usage & observability
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Track AI calls, token usage, tools, and who triggered them. Slack users show display names
        when the bot token can resolve them; add manual aliases in{" "}
        <Typography.Text code>observability.user_labels</Typography.Text> in config.yaml.
      </Typography.Paragraph>

      <div className="alfred-panel" style={{ marginBottom: 20 }}>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">Range</label>
            <Select
              style={{ width: "100%" }}
              value={preset}
              onChange={setPreset}
              options={[
                { value: "24h", label: "Last 24 hours" },
                { value: "7d", label: "Last 7 days" },
                { value: "30d", label: "Last 30 days" },
                { value: "month", label: "This month" },
              ]}
            />
          </Col>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">Granularity</label>
            <Select
              style={{ width: "100%" }}
              value={bucket}
              onChange={setBucket}
              options={[
                { value: "hour", label: "Per hour" },
                { value: "day", label: "Per day" },
                { value: "month", label: "Per month" },
              ]}
            />
          </Col>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">Source</label>
            <Select
              allowClear
              style={{ width: "100%" }}
              placeholder="All sources"
              value={source}
              onChange={setSource}
              options={filterOptions.sources.map((value) => ({ value, label: value }))}
            />
          </Col>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">User</label>
            <Select
              allowClear
              style={{ width: "100%" }}
              placeholder="All users"
              value={user}
              onChange={setUser}
              options={filterOptions.users.map((value) => ({ value, label: value }))}
            />
          </Col>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">Model</label>
            <Select
              allowClear
              style={{ width: "100%" }}
              placeholder="All models"
              value={model}
              onChange={setModel}
              options={filterOptions.models.map((value) => ({ value, label: value }))}
            />
          </Col>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">Event type</label>
            <Select
              allowClear
              style={{ width: "100%" }}
              placeholder="All events"
              value={eventType}
              onChange={setEventType}
              options={[
                { value: "llm_call", label: "LLM calls" },
                { value: "tool_call", label: "Tool calls" },
              ]}
            />
          </Col>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">Tool category</label>
            <Select
              allowClear
              style={{ width: "100%" }}
              placeholder="All categories"
              value={toolCategory}
              onChange={setToolCategory}
              options={filterOptions.tool_categories.map((value) => ({ value, label: value }))}
            />
          </Col>
          <Col xs={24} md={6} style={{ display: "flex", alignItems: "flex-end" }}>
            <Button type="primary" onClick={() => void load()} loading={loading}>
              Refresh
            </Button>
          </Col>
        </Row>
      </div>

      <div className="alfred-stat-grid" style={{ marginBottom: 20 }}>
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">LLM calls</div>
          <div className="alfred-stat-value">{formatNumber(summary?.llm_calls ?? 0)}</div>
        </div>
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">Tool calls</div>
          <div className="alfred-stat-value">{formatNumber(summary?.tool_calls ?? 0)}</div>
        </div>
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">Total tokens</div>
          <div className="alfred-stat-value">{formatNumber(summary?.total_tokens ?? 0)}</div>
        </div>
        <div className="alfred-stat-card">
          <div className="alfred-stat-label">Unique users</div>
          <div className="alfred-stat-value">{formatNumber(byUserEntries.length)}</div>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} lg={8}>
          <div className="alfred-panel alfred-usage-chart-card">
            <UsageBarChart
              title="LLM calls"
              points={timeseries?.points ?? []}
              metric="llm_calls"
              bucket={bucket}
            />
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="alfred-panel alfred-usage-chart-card">
            <UsageBarChart
              title="Tool calls"
              points={timeseries?.points ?? []}
              metric="tool_calls"
              bucket={bucket}
            />
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="alfred-panel alfred-usage-chart-card">
            <UsageBarChart
              title="Tokens"
              points={timeseries?.points ?? []}
              metric="total_tokens"
              bucket={bucket}
            />
          </div>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} md={12}>
          <BreakdownChart title="By user" entries={byUserEntries} />
        </Col>
        <Col xs={24} md={12}>
          <BreakdownChart title="By source" entries={bySourceEntries} />
        </Col>
      </Row>

      {byModelEntries.length > 0 ? (
        <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
          <Col xs={24}>
            <BreakdownChart title="By model" entries={byModelEntries} />
          </Col>
        </Row>
      ) : null}

      <div className="alfred-panel">
        <Typography.Title level={5}>Recent interactions</Typography.Title>
        <Table
          size="small"
          rowKey={(row) =>
            `${row.recorded_at}-${row.event_type}-${row.task_id || ""}-${row.tool_name || row.model || ""}`
          }
          loading={loading}
          columns={columns}
          dataSource={events}
          pagination={false}
          scroll={{ x: 960 }}
        />
      </div>
    </div>
  );
}
