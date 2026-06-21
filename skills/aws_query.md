---
name: aws_query
description: Query AWS datasets with Athena and pull logs from CloudWatch by service or log group
mode: investigation
trigger_keywords:
  - athena
  - cloudwatch
  - log group
  - logs for
  - query logs
  - pull logs
  - service logs
  - error logs
  - production logs
  - aws logs
  - run query on
allowed_channels:
  - "*"
allowed_tools:
  - athena_query
  - cloudwatch_query
  - list_cloudwatch_log_groups
requires_thread_context: false
---

# Objective

Answer questions about production data and logs using read-only AWS tools.

Company-specific Athena tables (e.g. event dumps) belong in **`.alfred/playbooks/`** — not bundled skills. When a domain playbook matches, use its configured tools.

# Execution steps

1. For **log questions**, identify the service name or log group.
   - If unknown, run `list_cloudwatch_log_groups` with the service name or `/ecs/` prefix.
   - Prefer `service_name` when `aws.log_group_map` is configured; otherwise pass `log_group`.
2. For **CloudWatch Logs Insights**, use a focused query:
   - Example: `fields @timestamp, @message | filter @message like /error/i | sort @timestamp desc | limit 50`
   - Default time window is the last hour unless the user specifies otherwise (`1h`, `24h`, ISO timestamps).
3. For **Athena**, write SQL against `aws.athena_database`.
   - Keep queries read-only (`SELECT` only).
   - Always include `LIMIT 200` unless the user explicitly requests full data.

# Response format

- Lead with a one-sentence answer.
- Show a compact table of the most relevant rows (the system renders structured results).
- If access is denied, quote the permission error and list the IAM actions needed — do not guess credentials.

# Governance

- READ-ONLY — never mutate AWS resources.
- Only use services listed in `aws.allowed_services`.
- Do not expose access keys or secret values in replies.
