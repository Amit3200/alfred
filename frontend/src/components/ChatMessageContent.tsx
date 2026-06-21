import { ChatMarkdown } from "./ChatMarkdown";

export type ResponsePayload = {
  kind:
    | "text"
    | "pr_list"
    | "pr_detail"
    | "repo_list"
    | "error"
    | "code_grep"
    | "file_content"
    | "git_log"
    | "git_blame"
    | "git_show"
    | "jira_list"
    | "jira_detail"
    | "jira_action"
    | "athena_query"
    | "cloudwatch_query"
    | "cloudwatch_log_groups"
    | "grade_events_query";
  data: Record<string, unknown>;
};

export type PullRequestItem = {
  number: number;
  title: string;
  state: string;
  repo: string;
  author: string;
  url: string;
  draft?: boolean;
};

type Props = {
  content: string;
  payload?: ResponsePayload | null;
};

export function ChatMessageContent({ content, payload }: Props) {
  if (!payload) {
    return <ChatMarkdown content={content} />;
  }

  switch (payload.kind) {
    case "pr_list":
      return <PrListView data={payload.data} />;
    case "pr_detail":
      return <PrDetailView data={payload.data} />;
    case "repo_list":
      return <RepoListView data={payload.data} />;
    case "error":
      return <div className="alfred-chat-error">{String(payload.data.message || content)}</div>;
    case "grade_events_query":
      return <GradeEventsQueryView data={payload.data} content={content} />;
    case "athena_query":
    case "cloudwatch_query":
    case "cloudwatch_log_groups":
      return <AwsQueryView kind={payload.kind} data={payload.data} content={content} />;
    case "text":
    default:
      return <ChatMarkdown content={String(payload.data.text || content)} />;
  }
}

function PrListView({ data }: { data: Record<string, unknown> }) {
  const prs = (data.prs as PullRequestItem[]) || [];
  const state = String(data.state || "open");

  if (!prs.length) {
    return <p className="alfred-chat-empty-result">No {state} pull requests found.</p>;
  }

  const byRepo = prs.reduce<Record<string, PullRequestItem[]>>((acc, pr) => {
    const short = pr.repo?.split("/").pop() || pr.repo || "unknown";
    (acc[short] ||= []).push(pr);
    return acc;
  }, {});

  const stateLabel = state === "open" || state === "closed" ? state : "matching";

  return (
    <div className="alfred-pr-list">
      <div className="alfred-pr-list-header">
        {prs.length} {stateLabel} PR{prs.length !== 1 ? "s" : ""}
      </div>
      {Object.keys(byRepo)
        .sort()
        .map((repo) => (
          <section key={repo} className="alfred-pr-repo">
            <h4 className="alfred-pr-repo-name">{repo}</h4>
            <ul className="alfred-pr-items">
              {byRepo[repo]
                .sort((a, b) => b.number - a.number)
                .map((pr) => (
                  <li key={`${pr.repo}-${pr.number}`}>
                    <a href={pr.url} target="_blank" rel="noopener noreferrer" className="alfred-pr-link">
                      #{pr.number} {pr.title}
                    </a>
                    {pr.draft && <span className="alfred-pr-draft">draft</span>}
                  </li>
                ))}
            </ul>
          </section>
        ))}
    </div>
  );
}

function PrDetailView({ data }: { data: Record<string, unknown> }) {
  const pr = (data.pr as Record<string, unknown>) || {};
  const repo = String(pr.repo || "");
  const repoShort = repo.split("/").pop() || repo;
  const url = String(pr.url || "");

  return (
    <div className="alfred-pr-detail">
      <div className="alfred-pr-detail-repo">PR in {repoShort}</div>
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="alfred-pr-detail-title">
          #{String(pr.number)} {String(pr.title || "Untitled")}
        </a>
      ) : (
        <div className="alfred-pr-detail-title">
          #{String(pr.number)} {String(pr.title || "Untitled")}
        </div>
      )}
      <div className="alfred-pr-detail-meta">
        {[pr.state, pr.author ? `by ${pr.author}` : null, pr.draft ? "draft" : null]
          .filter(Boolean)
          .join(" · ")}
      </div>
      {pr.head && pr.base ? (
        <div className="alfred-pr-detail-branches">
          <code>{String(pr.head)}</code> → <code>{String(pr.base)}</code>
        </div>
      ) : null}
      {pr.body ? <div className="alfred-pr-detail-body">{String(pr.body).slice(0, 400)}</div> : null}
    </div>
  );
}

function RepoListView({ data }: { data: Record<string, unknown> }) {
  const repos = (data.repos as string[]) || [];
  if (!repos.length) {
    return <p className="alfred-chat-empty-result">No repositories configured or accessible.</p>;
  }
  return (
    <ul className="alfred-repo-list">
      {repos.map((repo) => (
        <li key={repo}>
          <code>{repo}</code>
        </li>
      ))}
    </ul>
  );
}

function formatEventTimestamp(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "—";
  const numeric = Number(trimmed);
  if (!Number.isNaN(numeric) && numeric > 1_000_000_000_000) {
    return new Date(numeric).toISOString().replace("T", " ").replace(".000Z", " UTC");
  }
  return trimmed;
}

function shortValue(value: string, max = 12): string {
  if (!value || value === "—") return "—";
  if (value.length <= max + 1) return value;
  return `${value.slice(0, max)}…`;
}

function GradeEventsQueryView({
  data,
  content,
}: {
  data: Record<string, unknown>;
  content: string;
}) {
  const rows = (data.rows as Record<string, string>[]) || [];
  const guardrails = (data.guardrails as Record<string, unknown>) || {};
  const rowCount = Number(data.row_count ?? rows.length);
  const window = String(guardrails.time_window || "").replace(/_/g, " ");
  const limit = guardrails.limit;
  const showAnalysis =
    content.trim().length > 0 && !content.includes("```") && payloadLooksLikeAnalysis(content);

  if (!rows.length) {
    return (
      <div className="alfred-grade-events">
        {showAnalysis ? (
          <div className="alfred-grade-events-analysis">
            <ChatMarkdown content={content} />
          </div>
        ) : null}
        <p className="alfred-chat-empty-result">{content || "No matching grade events."}</p>
      </div>
    );
  }

  return (
    <div className="alfred-grade-events">
      <div className="alfred-grade-events-meta">
        <span className="alfred-grade-events-meta-title">grade_events</span>
        <span>
          {rowCount} row{rowCount === 1 ? "" : "s"}
          {window ? ` · ${window}` : ""}
          {limit != null ? ` · limit ${String(limit)}` : ""}
        </span>
      </div>
      {showAnalysis ? (
        <div className="alfred-grade-events-analysis">
          <ChatMarkdown content={content} />
        </div>
      ) : null}
      <div className="alfred-grade-events-list">
        {rows.slice(0, 25).map((row, index) => (
          <article key={index} className="alfred-grade-event-card">
            <header className="alfred-grade-event-header">
              <code className="alfred-grade-event-kind">{row.kind || "event"}</code>
              <time className="alfred-grade-event-time">{formatEventTimestamp(String(row.timestamp || ""))}</time>
            </header>
            <dl className="alfred-grade-event-fields">
              {[
                ["category", row.category],
                ["environment", row.environment],
                ["platform", row.platform],
                ["merchant_id", row.merchant_id],
                ["session_id", row.session_id],
                ["fp_id", row.fp_id],
                ["source", row.source],
                ["error", row.error || "none"],
              ].map(([label, value]) => (
                <div key={label} className="alfred-grade-event-field">
                  <dt>{label}</dt>
                  <dd title={String(value || "")}>{shortValue(String(value || "—"), label === "fp_id" ? 18 : 14)}</dd>
                </div>
              ))}
            </dl>
            {row.data ? (
              <details className="alfred-grade-event-data">
                <summary>data payload</summary>
                <pre>{truncateJson(String(row.data), 1200)}</pre>
              </details>
            ) : null}
          </article>
        ))}
      </div>
      {rows.length > 25 ? (
        <p className="alfred-chat-empty-result">… and {rows.length - 25} more row(s)</p>
      ) : null}
    </div>
  );
}

function payloadLooksLikeAnalysis(content: string): boolean {
  const lower = content.toLowerCase();
  return !lower.startsWith("grade_events `") && !lower.startsWith("athena `");
}

function truncateJson(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}

function AwsQueryView({
  kind,
  data,
  content,
}: {
  kind: string;
  data: Record<string, unknown>;
  content: string;
}) {
  if (kind === "cloudwatch_log_groups") {
    const groups = (data.groups as string[]) || [];
    if (!groups.length) {
      return <p className="alfred-chat-empty-result">No log groups found.</p>;
    }
    return (
      <ul className="alfred-repo-list">
        {groups.map((group) => (
          <li key={group}>
            <code>{group}</code>
          </li>
        ))}
      </ul>
    );
  }

  const rows = (data.rows as Record<string, string>[]) || [];
  const columns =
    (data.columns as string[]) || (rows[0] ? Object.keys(rows[0]) : []);

  if (!rows.length) {
    return <p className="alfred-chat-empty-result">{content || "No rows returned."}</p>;
  }

  return (
    <div className="alfred-aws-query">
      {content && payloadLooksLikeAnalysis(content) ? (
        <div className="alfred-grade-events-analysis">
          <ChatMarkdown content={content} />
        </div>
      ) : null}
      <div className="alfred-aws-table-wrap">
        <table className="alfred-aws-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 25).map((row, index) => (
              <tr key={index}>
                {columns.map((col) => (
                  <td key={col} title={String(row[col] ?? "")}>
                    {String(row[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 25 ? (
        <p className="alfred-chat-empty-result">… and {rows.length - 25} more row(s)</p>
      ) : null}
    </div>
  );
}
