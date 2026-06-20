---
name: slack-summaries
triggers:
  - summarize
  - summary
  - takeaway
  - takeaways
  - recap
  - duplicate
  - merchant
  - threshold
  - alert
channels: []
---

# Slack channel summaries

When summarizing channel or thread history:

1. **Completeness** — Include every relevant bot/app message in the fetched window. Do not summarize down to a partial list unless the user asked for "top N".
2. **Tables** — For multi-row data (merchants, orders, alerts with values), use a fenced code block with aligned columns:

```
Date       | Source | Item    | Value          | Notes
2026-06-17 | AlertsBot | ExampleStore | $2,500,000.00  | threshold crossed
```

3. **Grounding** — Use only timestamps, names, and values from the Slack context block. Never invent years, user IDs, or amounts.
4. **Reactions** — When asked who acknowledged something, cite the reaction display names from context.
5. **Window limits** — If the answer is not in the fetched range, state the window searched (e.g. last 30 days) and stop.

Replace this file in `.alfred/playbooks/` with your company's alert field names and formatting preferences.
