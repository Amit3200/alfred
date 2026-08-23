/** Shared health-check metadata and helpers — keep in sync with backend.health.run_all_checks. */

export type HealthCheck = {
  ok?: boolean;
  skipped?: boolean;
  message?: string;
  running?: boolean;
};

/** Order returned by GET /api/health/checks (slack_ingress appended at runtime). */
export const HEALTH_CHECK_ORDER = [
  "slack",
  "slack_ingress",
  "git",
  "aws",
  "jira",
  "google",
  "web_search",
  "periskope",
  "ai",
] as const;

export type HealthCheckKey = (typeof HEALTH_CHECK_ORDER)[number];

export const SERVICE_LABELS: Record<string, string> = {
  slack: "Slack",
  slack_ingress: "Slack ingress",
  git: "Git",
  aws: "AWS",
  jira: "JIRA",
  google: "Google Workspace",
  web_search: "Web search",
  periskope: "Periskope",
  ai: "AI",
};

/** Integrations panel card id → health check key(s). */
export const INTEGRATION_HEALTH_KEYS: Record<string, string | string[]> = {
  slack: ["slack", "slack_ingress"],
  git: "git",
  aws: "aws",
  jira: "jira",
  google: "google",
  web_search: "web_search",
  periskope: "periskope",
};

export type HealthStatusKind = "inactive" | "unknown" | "skipped" | "ok" | "warn" | "fail";

export type IntegrationHealth = {
  kind: HealthStatusKind;
  label: string;
};

export function serviceLabel(key: string): string {
  return SERVICE_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function statusLabel(check: HealthCheck): string {
  if (check.skipped) return "skipped";
  return check.ok ? "ok" : "fail";
}

export function healthCheckSortIndex(key: string): number {
  const index = HEALTH_CHECK_ORDER.indexOf(key as HealthCheckKey);
  return index === -1 ? HEALTH_CHECK_ORDER.length + 1 : index;
}

export function sortHealthCheckEntries(
  checks: Record<string, HealthCheck>,
): [string, HealthCheck][] {
  return Object.entries(checks).sort(
    ([a], [b]) => healthCheckSortIndex(a) - healthCheckSortIndex(b),
  );
}

export function summarizeHealth(checks: Record<string, HealthCheck> | null): {
  total: number;
  ok: number;
  failed: number;
  skipped: number;
  headline: string;
} {
  if (!checks) {
    return { total: 0, ok: 0, failed: 0, skipped: 0, headline: "Not checked" };
  }
  const entries = Object.values(checks);
  const skipped = entries.filter((c) => c.skipped).length;
  const active = entries.filter((c) => !c.skipped);
  const ok = active.filter((c) => c.ok).length;
  const failed = active.filter((c) => !c.ok).length;
  const total = active.length;
  let headline = "Not checked";
  if (total > 0) {
    if (failed === 0) headline = "All checks passed";
    else if (ok === 0) headline = "Checks failing";
    else headline = `${failed} check${failed === 1 ? "" : "s"} failing`;
  }
  return { total, ok, failed, skipped, headline };
}

function resolveCheckKeys(integrationKey: string): string[] {
  const mapped = INTEGRATION_HEALTH_KEYS[integrationKey];
  if (!mapped) return [];
  return Array.isArray(mapped) ? mapped : [mapped];
}

export function integrationHealth(
  checks: Record<string, HealthCheck> | null,
  integrationKey: string,
  enabled: boolean,
): IntegrationHealth {
  if (!enabled) {
    return { kind: "inactive", label: "Inactive" };
  }
  const keys = resolveCheckKeys(integrationKey);
  if (!keys.length || !checks) {
    return { kind: "unknown", label: "Active" };
  }

  const relevant = keys.map((key) => checks[key]).filter(Boolean) as HealthCheck[];
  if (!relevant.length) {
    return { kind: "unknown", label: "Active" };
  }

  const active = relevant.filter((c) => !c.skipped);
  if (!active.length) {
    return { kind: "skipped", label: "Skipped" };
  }

  const failures = active.filter((c) => !c.ok);
  if (failures.length === active.length) {
    return { kind: "fail", label: "Issue" };
  }
  if (failures.length > 0) {
    return { kind: "warn", label: "Partial" };
  }
  return { kind: "ok", label: "Healthy" };
}

export function integrationDotClass(kind: HealthStatusKind, enabled: boolean): string {
  if (!enabled) return "disabled";
  switch (kind) {
    case "ok":
      return "enabled health-ok";
    case "fail":
      return "health-fail";
    case "warn":
      return "health-warn";
    case "skipped":
      return "health-warn";
    default:
      return "enabled";
  }
}
