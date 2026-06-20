# Domain playbooks

Playbooks teach Alfred how **your company** formats answers and maps fields — without hard-coding that logic in Python.

Alfred loads Markdown files from **`.alfred/playbooks/*.md`** at runtime. Copy and edit the example below; add more files as you grow.

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
  - threshold
channels: []   # optional Slack channel IDs; empty = all channels
---

# Slack channel summaries

When the user asks for a summary or takeaways from channel history:

- Use **every** matching bot message in the fetched window — do not skip rows.
- For tabular data (merchants, orders, thresholds), output a fenced code block:

\`\`\`
Date       | Source | Item           | Value
2026-06-17 | AlertsBot | ExampleStore | $2,506,059.00
\`\`\`

- Quote timestamps exactly as shown in context.
- For ack/reactions, use the display names provided in context.
- If data is outside the readable window, say so — never invent dates or IDs.
```

## Triggers

A playbook is included when **any** trigger string appears in the user's message (case-insensitive).

Use short, distinctive keywords (`duplicate`, `merchant`, `deploy`) rather than full sentences.

## Channels (optional)

Set `channels: ["C01234567"]` to limit a playbook to specific Slack channels. Omit or use `[]` for global playbooks.

## Getting started

1. Create `.alfred/playbooks/` if it does not exist.
2. Copy `example-slack-summaries.md` from this folder into `.alfred/playbooks/`.
3. Rename and edit for your alert bots, field names, and formatting rules.
4. Restart Alfred (or save config) — playbooks are read on each request.

## Adapters vs playbooks

- **Playbooks** (this folder): Markdown instructions for the model — no code deploy needed.
- **Adapters** (future / custom code): Python modules for structured integrations. Prefer playbooks first; add adapters only when you need deterministic parsing or external APIs.
