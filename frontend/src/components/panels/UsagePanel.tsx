import { Button, Col, Row, Select, Table, Tooltip, Typography } from "antd";
import { ArrowDownOutlined, ArrowUpOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type ObservabilityEvent,
  type ObservabilitySummary,
  type ObservabilityTimeseries,
} from "../../api/client";

type Preset = "24h" | "7d" | "30d" | "month";
type Bucket = "hour" | "day" | "month";
const EVENTS_PAGE_SIZE = 20;

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function formatCostUsd(value: number | null | undefined): string {
  const amount = value ?? 0;
  if (amount <= 0) return "$0.00";
  if (amount >= 1) return `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (amount >= 0.01) return `$${amount.toFixed(2)}`;
  return `$${amount.toFixed(4)}`;
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

function UsageLineChart({
  title,
  points,
  metric,
  bucket,
}: {
  title: string;
  points: ObservabilityTimeseries["points"];
  metric: "llm_calls" | "tool_calls";
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

  // Calculate SVG dimensions
  const svgWidth = 500;
  const svgHeight = 160;
  const paddingLeft = 45;
  const paddingRight = 20;
  const paddingTop = 15;
  const paddingBottom = 25;
  
  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;

  // Generate points coordinates
  const coords = points.map((point, index) => {
    const value = point[metric] ?? 0;
    const x = paddingLeft + (points.length > 1 ? (index / (points.length - 1)) * chartWidth : chartWidth / 2);
    const y = paddingTop + chartHeight - (value / scaleMax) * chartHeight;
    return { x, y, value, period: point.period };
  });

  // Generate SVG path for line
  let linePath = "";
  if (coords.length > 0) {
    linePath = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 1; i < coords.length; i++) {
      linePath += ` L ${coords[i].x} ${coords[i].y}`;
    }
  }

  // Generate SVG path for filled area underneath
  let areaPath = "";
  if (coords.length > 0) {
    areaPath = `${linePath} L ${coords[coords.length - 1].x} ${paddingTop + chartHeight} L ${coords[0].x} ${paddingTop + chartHeight} Z`;
  }

  return (
    <div className="alfred-usage-chart-panel">
      <div className="alfred-usage-chart-header" style={{ marginBottom: 16 }}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          {title}
        </Typography.Title>
        <Typography.Text type="secondary" className="alfred-usage-chart-total">
          Total {formatNumber(total)}
        </Typography.Text>
      </div>
      <div className="alfred-usage-chart-body-svg" style={{ position: "relative", width: "100%" }}>
        <svg width="100%" height={svgHeight} viewBox={`0 0 ${svgWidth} ${svgHeight}`} style={{ overflow: "visible" }}>
          <defs>
            <linearGradient id={`${metric}-grad`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--alfred-accent)" stopOpacity="0.25" />
              <stop offset="100%" stopColor="var(--alfred-accent)" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines & Y Axis labels */}
          {ticks.map((tick) => {
            const y = paddingTop + chartHeight - (tick / scaleMax) * chartHeight;
            return (
              <g key={tick}>
                <text
                  x={paddingLeft - 10}
                  y={y + 4}
                  textAnchor="end"
                  fill="var(--alfred-text-muted)"
                  style={{ fontSize: 10, fontFamily: "var(--alfred-font)" }}
                >
                  {formatNumber(tick)}
                </text>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={svgWidth - paddingRight}
                  y2={y}
                  stroke="var(--alfred-border-subtle)"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
              </g>
            );
          })}

          {/* X Axis Labels */}
          {coords.map((c, index) => {
            const shouldShowLabel = 
              coords.length <= 7 || 
              index === 0 || 
              index === coords.length - 1 || 
              index === Math.floor(coords.length / 2);

            if (!shouldShowLabel) return null;
            return (
              <text
                key={c.period}
                x={c.x}
                y={svgHeight - 5}
                textAnchor="middle"
                fill="var(--alfred-text-muted)"
                style={{ fontSize: 9.5, fontFamily: "var(--alfred-font)" }}
              >
                {formatPeriod(c.period, bucket)}
              </text>
            );
          })}

          {/* Area Path */}
          {areaPath && (
            <path d={areaPath} fill={`url(#${metric}-grad)`} />
          )}

          {/* Line Path */}
          {linePath && (
            <path
              d={linePath}
              stroke="var(--alfred-accent)"
              strokeWidth="2.5"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Interactive dots */}
          {coords.map((c) => (
            <g key={c.period}>
              <circle
                cx={c.x}
                cy={c.y}
                r="4"
                fill="var(--alfred-surface)"
                stroke="var(--alfred-accent)"
                strokeWidth="2.5"
                style={{ cursor: "pointer" }}
              />
              <Tooltip title={`${formatPeriod(c.period, bucket)}: ${formatNumber(c.value)}`}>
                <circle
                  cx={c.x}
                  cy={c.y}
                  r="12"
                  fill="transparent"
                  style={{ cursor: "pointer" }}
                />
              </Tooltip>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}

function TokenStackedBarChart({
  points,
  bucket,
}: {
  points: ObservabilityTimeseries["points"];
  bucket: Bucket;
}) {
  const totals = useMemo(
    () => points.map((point) => (point.prompt_tokens ?? 0) + (point.completion_tokens ?? 0)),
    [points],
  );
  const inputTotal = useMemo(
    () => points.reduce((sum, point) => sum + (point.prompt_tokens ?? 0), 0),
    [points],
  );
  const outputTotal = useMemo(
    () => points.reduce((sum, point) => sum + (point.completion_tokens ?? 0), 0),
    [points],
  );
  const costTotal = useMemo(
    () => points.reduce((sum, point) => sum + (point.estimated_cost_usd ?? 0), 0),
    [points],
  );
  const max = useMemo(() => Math.max(...totals, 0), [totals]);
  const ticks = useMemo(() => niceTicks(max), [max]);
  const scaleMax = ticks[ticks.length - 1] || 1;

  if (!points.length) {
    return (
      <div className="alfred-usage-chart-panel">
        <Typography.Title level={5}>Tokens (input / output)</Typography.Title>
        <Typography.Text type="secondary">No data for this range.</Typography.Text>
      </div>
    );
  }

  return (
    <div className="alfred-usage-chart-panel">
      <div className="alfred-usage-chart-header">
        <Typography.Title level={5} style={{ margin: 0 }}>
          Tokens (input / output)
        </Typography.Title>
        <Typography.Text type="secondary" className="alfred-usage-chart-total">
          {formatNumber(inputTotal)} in · {formatNumber(outputTotal)} out · {formatCostUsd(costTotal)} est.
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
              const input = point.prompt_tokens ?? 0;
              const output = point.completion_tokens ?? 0;
              const total = input + output;
              return (
                <div key={point.period} className="alfred-usage-bar-wrap">
                  <span className="alfred-usage-bar-value">{formatNumber(total)}</span>
                  <div className="alfred-usage-bar-track alfred-usage-bar-track-stacked">
                    <div
                      className="alfred-usage-bar-stack"
                      style={{
                        height: `${Math.max(total > 0 ? 6 : 0, scaleMax > 0 ? (total / scaleMax) * 100 : 0)}%`,
                      }}
                      title={`${formatPeriod(point.period, bucket)}: ${formatNumber(input)} in / ${formatNumber(output)} out`}
                    >
                      <div
                        className="alfred-usage-bar alfred-usage-bar-output"
                        style={{ height: total > 0 ? `${(output / total) * 100}%` : "0%" }}
                      />
                      <div
                        className="alfred-usage-bar alfred-usage-bar-input"
                        style={{ height: total > 0 ? `${(input / total) * 100}%` : "0%" }}
                      />
                    </div>
                  </div>
                  <span className="alfred-usage-bar-label">{formatPeriod(point.period, bucket)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="alfred-usage-token-legend">
        <span className="alfred-usage-token-legend-item">
          <span className="alfred-usage-token-legend-swatch alfred-usage-bar-input" /> Input
        </span>
        <span className="alfred-usage-token-legend-item">
          <span className="alfred-usage-token-legend-swatch alfred-usage-bar-output" /> Output
        </span>
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
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPage, setEventsPage] = useState(1);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [filterOptions, setFilterOptions] = useState<{
    sources: string[];
    users: string[];
    models: string[];
    tool_categories: string[];
  }>({ sources: [], users: [], models: [], tool_categories: [] });

  const [checkpoints, setCheckpoints] = useState<any[]>([]);
  const [checkpointsLoading, setCheckpointsLoading] = useState(false);

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
    setCheckpointsLoading(true);
    try {
      const [summaryRes, seriesRes, filtersRes, checkpointsRes] = await Promise.all([
        api.observabilitySummary(query),
        api.observabilityTimeseries(query),
        api.observabilityFilters("30d"),
        api.observabilityCheckpoints(),
      ]);
      setSummary(summaryRes.summary);
      setTimeseries(seriesRes.timeseries);
      setFilterOptions(filtersRes);
      setCheckpoints(checkpointsRes.checkpoints || []);
    } finally {
      setLoading(false);
      setCheckpointsLoading(false);
    }
  }, [query]);

  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const eventsRes = await api.observabilityEvents({
        ...query,
        limit: EVENTS_PAGE_SIZE,
        offset: (eventsPage - 1) * EVENTS_PAGE_SIZE,
      });
      setEvents(eventsRes.events);
      setEventsTotal(eventsRes.total);
    } finally {
      setEventsLoading(false);
    }
  }, [query, eventsPage]);

  useEffect(() => {
    setEventsPage(1);
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

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
  const byPlanEntries = useMemo(
    () => Object.entries(summary?.by_plan ?? {}).sort((a, b) => b[1] - a[1]),
    [summary],
  );
  const byPlanTokensEntries = useMemo(
    () => Object.entries(summary?.by_plan_tokens ?? {}).sort((a, b) => b[1] - a[1]),
    [summary],
  );

  const checkpointColumns = [
    {
      title: "Timestamp",
      dataIndex: "timestamp",
      key: "timestamp",
      render: (value: number) => new Date(value * 1000).toLocaleString(),
      width: 170,
    },
    {
      title: "Task ID",
      dataIndex: "task_id",
      key: "task_id",
      width: 150,
      render: (val: string) => <span style={{ fontFamily: "monospace", fontSize: 12 }}>{val}</span>,
    },
    {
      title: "Checkpoint Stage",
      dataIndex: "checkpoint",
      key: "checkpoint",
      width: 160,
    },
    {
      title: "Target / Engine",
      dataIndex: "function_name",
      key: "function_name",
      width: 160,
      render: (val: string) => {
        if (val === "react") return <span style={{ color: "var(--alfred-accent)", fontWeight: "bold" }}>Standard ReAct</span>;
        if (val === "hermes") return <span style={{ color: "#bd93f9", fontWeight: "bold" }}>Nous Hermes Loop</span>;
        return val;
      }
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (val: string) => {
        if (val === "started") return <span style={{ color: "var(--alfred-accent)" }}>Started</span>;
        if (val === "completed") return <span style={{ color: "#50fa7b" }}>Completed</span>;
        if (val === "error") return <span style={{ color: "#ff5555", fontWeight: "bold" }}>Failed</span>;
        return val;
      }
    },
    {
      title: "Diagnostic Notes",
      dataIndex: "error",
      key: "error",
      render: (_: any, row: any) => {
        if (row.error) {
          return (
            <Tooltip title={row.error_stacktrace}>
              <span style={{ color: "#ff5555", cursor: "help" }}>{row.error} (Hover for traceback)</span>
            </Tooltip>
          );
        }
        return <span style={{ color: "var(--alfred-text-muted)" }}>None</span>;
      }
    }
  ];

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
      key: "tokens",
      width: 150,
      render: (_: unknown, row: ObservabilityEvent) =>
        row.event_type === "llm_call"
          ? `${formatNumber(row.prompt_tokens || 0)} in / ${formatNumber(row.completion_tokens || 0)} out`
          : "—",
    },
    {
      title: "Est. cost",
      key: "estimated_cost_usd",
      width: 90,
      render: (_: unknown, row: ObservabilityEvent) =>
        row.event_type === "llm_call" ? formatCostUsd(row.estimated_cost_usd) : "—",
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
        Track AI calls, token usage, estimated cost, tools, and who triggered them. Slack users show
        display names when the bot token can resolve them; add manual aliases in{" "}
        <Typography.Text code>observability.user_labels</Typography.Text> in config.yaml. Cost uses
        approximate per-model rates — override via{" "}
        <Typography.Text code>observability.model_pricing</Typography.Text>.
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

      <div className="alfred-stats-section" style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: "0 0 12px 0", color: "var(--alfred-text)" }}>
          Task Execution & Success
        </Typography.Title>
        <div className="alfred-stat-grid-5" style={{ marginBottom: 20 }}>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Tasks Invoked</div>
            <div className="alfred-stat-value">{formatNumber(summary?.total_tasks ?? 0)}</div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Successful Tasks</div>
            <div className="alfred-stat-value" style={{ color: "var(--alfred-status-ok)" }}>
              {formatNumber(summary?.successful_tasks ?? 0)}
            </div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Success Rate</div>
            <div className="alfred-stat-value">
              {summary?.total_tasks ? `${Math.round(((summary.successful_tasks ?? 0) / summary.total_tasks) * 100)}%` : "—"}
            </div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Plan Events</div>
            <div className="alfred-stat-value">{formatNumber(summary?.plan_events ?? 0)}</div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">User Feedback</div>
            <div className="alfred-stat-value" style={{ fontSize: 20, display: "flex", gap: 12, alignItems: "center", marginTop: 4 }}>
              <span style={{ color: "var(--alfred-status-ok)", display: "flex", alignItems: "center", gap: 4 }}>
                <ArrowUpOutlined style={{ fontSize: 18 }} /> {formatNumber(summary?.feedback_good ?? 0)}
              </span>
              <span style={{ color: "var(--alfred-status-fail)", display: "flex", alignItems: "center", gap: 4 }}>
                <ArrowDownOutlined style={{ fontSize: 18 }} /> {formatNumber(summary?.feedback_bad ?? 0)}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="alfred-stats-section" style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: "0 0 12px 0", color: "var(--alfred-text)" }}>
          AI Consumption & Costs
        </Typography.Title>
        <div className="alfred-stat-grid-5" style={{ marginBottom: 20 }}>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">LLM Calls</div>
            <div className="alfred-stat-value">{formatNumber(summary?.llm_calls ?? 0)}</div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Tool Calls</div>
            <div className="alfred-stat-value">{formatNumber(summary?.tool_calls ?? 0)}</div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Total Tokens</div>
            <div className="alfred-stat-value" style={{ fontSize: 22 }}>
              {formatNumber(summary?.total_tokens ?? 0)}
              <div style={{ fontSize: 11, color: "var(--alfred-text-muted)", fontWeight: "normal", marginTop: 2 }}>
                {formatNumber(summary?.prompt_tokens ?? 0)} in · {formatNumber(summary?.completion_tokens ?? 0)} out
              </div>
            </div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Est. Cost</div>
            <div className="alfred-stat-value">{formatCostUsd(summary?.estimated_cost_usd)}</div>
          </div>
          <div className="alfred-stat-card">
            <div className="alfred-stat-label">Unique Users</div>
            <div className="alfred-stat-value">{formatNumber(byUserEntries.length)}</div>
          </div>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} lg={8}>
          <div className="alfred-panel alfred-usage-chart-card">
            <UsageLineChart
              title="LLM calls"
              points={timeseries?.points ?? []}
              metric="llm_calls"
              bucket={bucket}
            />
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="alfred-panel alfred-usage-chart-card">
            <UsageLineChart
              title="Tool calls"
              points={timeseries?.points ?? []}
              metric="tool_calls"
              bucket={bucket}
            />
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="alfred-panel alfred-usage-chart-card">
            <TokenStackedBarChart points={timeseries?.points ?? []} bucket={bucket} />
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

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} md={12}>
          <BreakdownChart title="By plan (tokens)" entries={byPlanTokensEntries} />
        </Col>
        <Col xs={24} md={12}>
          <BreakdownChart title="By plan (calls)" entries={byPlanEntries} />
        </Col>
      </Row>

      <div className="alfred-panel" style={{ marginBottom: 20 }}>
        <Typography.Title level={5}>Task execution timeline (checkpoints)</Typography.Title>
        <Table
          size="small"
          rowKey={(row) => `${row.timestamp}-${row.task_id}-${row.checkpoint}-${row.function_name}`}
          loading={checkpointsLoading}
          columns={checkpointColumns}
          dataSource={checkpoints}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          scroll={{ x: 960 }}
        />
      </div>

      <div className="alfred-panel">
        <Typography.Title level={5}>Recent interactions</Typography.Title>
        <Table
          size="small"
          rowKey={(row) =>
            `${row.recorded_at}-${row.event_type}-${row.task_id || ""}-${row.tool_name || row.model || ""}`
          }
          loading={eventsLoading}
          columns={columns}
          dataSource={events}
          pagination={{
            current: eventsPage,
            pageSize: EVENTS_PAGE_SIZE,
            total: eventsTotal,
            showSizeChanger: false,
            hideOnSinglePage: true,
            showTotal: (total) => `${total.toLocaleString()} interactions`,
            onChange: (page) => setEventsPage(page),
          }}
          scroll={{ x: 960 }}
        />
      </div>
    </div>
  );
}
