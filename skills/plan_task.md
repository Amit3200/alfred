---
name: plan_task
description: Create a standalone execution plan checklist from thread or chat context
mode: workflow
trigger_keywords:
  - alfred plan
  - create a plan
  - create plan
  - plan for
  - plan to
  - write a plan
  - execution plan
  - task plan
allowed_channels:
  - "*"
allowed_tools: []
requires_thread_context: true
---

# Objective

Produce a **standalone execution plan** (markdown checklist) for the user's task.  
Do **not** run write tools or open PRs — planning only.

**Model routing:** uses **Workflow execution** AI settings in Admin → AI.

# When context is missing

If the user says only `@alfred plan` or `alfred plan` with no task description:

1. Ask what they want planned (goal, constraints, success criteria).
2. Optionally ask which repo applies if git is enabled and `git.main_repo` is not enough.
3. Wait for their reply in the same thread — Alfred will continue the plan flow.

Use Slack/thread history when present (errors, stack traces, linked PRs).

# Plan contents (required sections)

Under `# Task Plan`, include checkboxes for:

| Area | Examples |
|------|----------|
| **Discovery** | Read relevant files, grep symbols, confirm assumptions |
| **Approach** | Steps to implement or investigate |
| **Instrumentation** | Logs/metrics/traces to add |
| **Tests** | Unit/integration cases, edge cases |
| **Validation** | How to verify before PR |
| **Risks** | What could break; mitigations |

End with **Open questions** if anything is still unclear.

# After the plan

- Save to `.alfred/plans/plan_<task_id>.md`
- Reply with the plan summary and file path
- Offer: "Reply `@alfred pr` when ready to implement" if the task is code-related — Alfred reuses this thread's saved plan checklist for the PR workflow.

# Governance

- Do not invent file paths — use discovery steps when unknown
- Ground the plan in provided Slack/thread context
- Keep plans actionable and ordered

# Example

```
@alfred plan add order_id null guard in checkout handler with unit test
```

```
alfred plan
→ Alfred asks what to plan
→ User: "instrument duplicate order detection in backend"
→ Alfred returns checklist saved to .alfred/plans/
```
