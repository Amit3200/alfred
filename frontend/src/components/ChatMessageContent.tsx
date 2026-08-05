import type { ReactNode } from "react";
import { ChatMarkdown } from "./ChatMarkdown";

export type ReplyMeta = {
  confidence: number;
  relevancy: "high" | "medium" | "low" | "not_found" | "unverified";
  classification?: string;
  strategy?: string;
};

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
    | "google_sheet"
    | "google_doc"
    | "doc_answer"
    | "doc_search";
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

function readReplyMeta(payload?: ResponsePayload | null): ReplyMeta | null {
  const raw = payload?.data?.reply_meta;
  if (!raw || typeof raw !== "object") return null;
  const confidence = Number((raw as ReplyMeta).confidence);
  const relevancy = String((raw as ReplyMeta).relevancy || "");
  if (!Number.isFinite(confidence) || !relevancy) return null;
  return raw as ReplyMeta;
}

function relevancyLabel(value: ReplyMeta["relevancy"]): string {
  switch (value) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
    case "not_found":
      return "Not found";
    default:
      return "Unverified";
  }
}

function ReplyMetaFooter({ meta }: { meta: ReplyMeta }) {
  const confidencePct = Math.round(Math.max(0, Math.min(1, meta.confidence)) * 100);
  const parts = [
    `Confidence: ${confidencePct}%`,
    `Relevancy: ${relevancyLabel(meta.relevancy)}`,
  ];
  if (meta.classification) {
    parts.push(meta.classification);
  }
  return (
    <div className="alfred-reply-meta" aria-label="Answer confidence and relevancy">
      {parts.join(" · ")}
    </div>
  );
}

export function ChatMessageContent({ content, payload }: Props) {
  const replyMeta = readReplyMeta(payload);
  let body: ReactNode;

  if (!payload) {
    body = <ChatMarkdown content={content} />;
  } else {
    switch (payload.kind) {
      case "pr_list":
        body = <PrListView data={payload.data} />;
        break;
      case "pr_detail":
        body = <PrDetailView data={payload.data} />;
        break;
      case "repo_list":
        body = <RepoListView data={payload.data} />;
        break;
      case "error":
        body = <div className="alfred-chat-error">{String(payload.data.message || content)}</div>;
        break;
      case "doc_answer":
      case "doc_search":
        body = (
          <DocAnswerView
            content={String(payload.data.text || content)}
            payload={payload.data}
          />
        );
        break;
      case "athena_query":
      case "cloudwatch_query":
      case "cloudwatch_log_groups":
        body = <AwsQueryView kind={payload.kind} data={payload.data} content={content} />;
        break;
      case "text":
      default:
        body = <ChatMarkdown content={String(payload.data.text || content)} />;
        break;
    }
  }

  return (
    <>
      {body}
      {replyMeta ? <ReplyMetaFooter meta={replyMeta} /> : null}
    </>
  );
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

function DocAnswerView({
  content,
  payload,
}: {
  content: string;
  payload: Record<string, unknown>;
}) {
  const docPath = String(payload.doc_path || "");
  const repo = String(payload.repo || "");
  return (
    <div className="alfred-doc-answer">
      {docPath ? (
        <div className="alfred-doc-answer-source">
          Source: <code>{docPath}</code>
          {repo ? <> ({repo})</> : null}
        </div>
      ) : null}
      <ChatMarkdown content={content} />
    </div>
  );
}

function payloadLooksLikeAnalysis(content: string): boolean {
  const lower = content.toLowerCase();
  return !lower.startsWith("athena `");
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
        <div className="alfred-aws-query-analysis">
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
