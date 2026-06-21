# Domain playbooks

Playbooks teach Alfred how **your company** formats answers and maps fields — without hard-coding that logic in Python.

Alfred loads Markdown files from **`.alfred/playbooks/*.md`** at runtime. Copy and edit the example below; add more files as you grow.

## Do not commit company playbooks

Playbooks are **company-specific** (alert bots, merchant fields, Athena tables, internal naming). They live under **`.alfred/playbooks/`**, which is inside **`.alfred/`** — that entire directory is **gitignored** and must stay local.

| Location | Commit? |
|----------|---------|
| `docs/playbooks/example-*.md` | Yes — generic examples only |
| `.alfred/playbooks/*.md` | **No** — your production playbooks |
| `skills/*.md` | Yes — generic skills shipped with Alfred |

On ECS/EC2, store playbooks on the persistent volume (EFS/EBS), not in the git repo.

## File format

Each playbook is a Markdown file with optional YAML front matter:

```markdown
---
name: slack-summaries
triggers:
  - summarize
  - takeaway
  - duplicate
  - merchant
channels: []   # optional Slack channel IDs; empty = all channels
---

# Slack channel summaries

When the user asks for a summary or takeaways from channel history:

- Use **every** matching bot message in the fetched window — do not skip rows.
- For tabular data, output a fenced code block with aligned columns.
- Quote timestamps exactly as shown in context.
- If data is outside the readable window, say so — never invent dates or IDs.
```

## Investigation playbooks

For domain data sources (Athena tables, event dumps, internal APIs), use **`mode: investigation`** and **`allowed_tools`**:

```yaml
---
name: grade_events
description: Query checkout events in Athena
mode: investigation
triggers:
  - grade events
  - checkout events
allowed_tools:
  - grade_events_query
requires_thread_context: false
---
```

Document **where to query** (database, table, S3, region, partitions) and **what to query** (which filters/IDs for which user questions). Generic AWS skills live in `skills/aws_query.md`; table-specific rules belong here.

## Triggers

A playbook is included when **any** trigger string appears in the user's message (case-insensitive). Use short, distinctive keywords.

## Channels (optional)

Set `channels: ["C01234567"]` to limit a playbook to specific Slack channels. Omit or use `[]` for global playbooks.

## Live web sources (optional)

```yaml
fetch_urls:
  - https://example.com
fetch_ttl_minutes: 60
```

Alfred fetches each URL when the playbook matches, caches under `.alfred/cache/playbook_urls/`, and appends a **Live web sources** section to the prompt. Only `https://` URLs are allowed.

## Getting started

1. Create `.alfred/playbooks/` if it does not exist.
2. Copy `example-slack-summaries.md` from this folder into `.alfred/playbooks/`.
3. Add investigation playbooks for your Athena tables, alert formats, and internal naming.
4. Restart Alfred — playbooks are read on each request.

## Adapters vs playbooks

- **Playbooks** (this folder): Markdown instructions for the model — no code deploy needed.
- **Adapters** (future / custom code): Python modules for structured integrations. Prefer playbooks first.
