---
name: create_pr
description: Phase 1 isolated code changes — plan, implement, test, and open a draft PR
mode: workflow
trigger_keywords:
  - alfred pr
  - create pr
  - create a pr
  - open pr
  - open a pull request
  - make a pr
  - submit pr
  - raise a pr
  - raise pr
  - creating pr
  - creating a pr
  - trigger pr
  - trigger the pr
  - proceed with pr
  - implement and pr
  - write a fix and pr
  - create_pr
allowed_channels:
  - "*"
allowed_tools:
  - git_prepare_branch
  - write_file
  - write_debug_script
  - run_debug_script
  - git_commit
  - git_push_branch
  - create_pull_request
  - grep_repo
  - read_file
  - git_log
  - git_blame
  - list_repos
  - get_pr
requires_thread_context: true
workflow_chain:
  - git_prepare_branch
  - write_file
  - git_commit
  - git_push_branch
  - create_pull_request
use_workflow_chain: true
---

# Objective

Implement **small, non-breaking, Phase 1 changes** in an **isolated session workspace**, then push a feature branch and open a **draft PR**.  
Each Slack thread / UI chat has its own git workspace — never assume another conversation's checkout.

**Requires:** `git.write_enabled: true` in Admin → Integrations.  
**Model routing:** uses **Workflow execution** AI settings (pick a capable coding model separately from investigation).

# Phase 1 scope (strict)

## Allowed

- Additive changes: logging/instrumentation, small bug fixes, read-only debug scripts under `scripts/alfred_debug/`
- New or extended **unit tests** covering business logic and edge cases
- Draft PRs only (`draft: true` on `create_pull_request` unless user explicitly asks otherwise)

## Forbidden

- Breaking API or behavior changes, large refactors, or deletions of production logic
- Direct commits or pushes to `main`, `master`, `production`, or other protected branches
- Modifying infra, lockfiles, CI, Docker, secrets, or `.env` paths (tool-enforced blocklist)
- Force-push, rewriting history, or merging PRs
- Debug scripts that write files, use network, shell=True, or os.system

When unsure, **stop and ask** in the thread rather than guessing.

# When context is missing

If the user sends only `@alfred pr`, `alfred pr`, or similar **without** a concrete task:

1. **Stop** — do not call write tools yet.
2. Ask clarifying questions in the thread:
   - Which repo? (default: `git.main_repo` if configured, e.g. `YourOrg/backend`)
   - What should the PR implement? (problem, expected behavior, tests)
3. Use Slack/thread history when it contains the bug, stack trace, or feature request.
4. After the user replies in the same thread, continue from Step 0 below.

Alfred's workflow gate handles this automatically in Slack/UI chat; the skill reinforces the same behavior inside the agent loop.

# PR plan workflow (follow in order)

## Step 0 — Confirm repo and intent

1. Identify target repo from the user message, thread context, or `git.main_repo` (e.g. `YourOrg/backend`).
2. Use `grep_repo`, `read_file`, and `git_log` to understand existing patterns **before** editing.
3. If the request is ambiguous or high-risk, reply with clarifying questions — do not write yet.

## Step 1 — Pull latest base branch

Call `git_prepare_branch` with:

- `repo` — full slug (`owner/name`)
- `branch_context` — short slug, e.g. `instrument-checkout-handler` or `fix-null-fp-id` (branch becomes `alfred/pr/<slug>`)
- `base_branch` — use `git.default_base_branch` when set; otherwise **omit** so Alfred uses the repo's remote default (`origin/HEAD`, e.g. `dev` for FlexyPe/cipher)

Optional: pass `branch_name` only when you need an explicit `alfred/pr/<slug>` (normally use `branch_context`).

This fetches latest `dev` (or the repo's remote default), **discards any leftover local edits** in the session workspace, and creates a fresh `alfred/pr/<slug>` branch from that base.

## Step 2 — Write the implementation plan (in thread + PR body)

Before editing files, produce a short plan covering:

| Section | Content |
|---------|---------|
| **Problem** | What bug or gap are we addressing? |
| **Approach** | Files to touch and why (cite paths from `read_file` / `grep_repo`) |
| **Instrumentation** | What logs/metrics/traces will be added? |
| **Tests** | New/updated tests — business rules and edge cases |
| **Risks** | What could break; why this stays non-breaking |

Keep the plan in the final PR description.

## Step 3 — Match repo structure and imports

Before `write_file`:

1. Read neighboring files — copy import style, module layout, naming conventions.
2. Place code in the correct package (do not invent new top-level folders without strong reason).
3. Use existing helpers/utilities rather than duplicating logic.
4. Prefer minimal diffs — smallest change that solves the problem.

## Step 4 — Implement + tests

1. Apply changes with `write_file` (small files; one concern per commit if large).
2. Add or update tests in the repo's existing test layout (`tests/`, `*_test.go`, etc.).
3. For data debugging only, use `write_debug_script` + `run_debug_script` (read-only scripts under `scripts/alfred_debug/`).

## Step 5 — Commit, push, open draft PR

1. `git_commit` — conventional message, e.g. `fix(checkout): guard null order_id in handler`
2. `git_push_branch` — push the feature branch (never protected branches)
3. `create_pull_request` with:
   - **title** — concise, conventional
   - **body** — include the plan from Step 2 + test checklist
   - **head** — feature branch name (`alfred/pr/<slug>` from Step 1)
   - **base** — same base used in Step 1
   - **draft** — `true` by default

Alfred tags PRs with GitHub labels `alfred-generated` and, when a plan exists, `alfred-plan` (create these labels in the repo once for filtering).

Reply in Slack with the PR URL and a summary of changes.

# Execution checklist (include in PR body)

```markdown
## Plan
- [ ] Problem statement
- [ ] Files changed and rationale

## Quality
- [ ] Matches repo import/package conventions
- [ ] Instrumentation added where useful
- [ ] Unit tests for business logic
- [ ] Edge cases covered
- [ ] No breaking changes

## Alfred Phase 1
- [ ] Branch created from latest base
- [ ] Draft PR opened
- [ ] Debug scripts (if any) are read-only under scripts/alfred_debug/
```

# Governance rules

- **READ before WRITE** — always inspect code with read tools first.
- **One workspace per thread** — never share branches across conversations.
- **Stop on tool errors** — explain blocklist/validation errors to the user; do not bypass.
- **No scope creep** — if the user asks for infra, migrations, or large refactors, explain Phase 1 limits and offer a plan-only response.
- Cite **file paths and line numbers** when discussing existing code.
- **Confirmation before publish** — on Slack/UI, `git_push_branch` and `create_pull_request` require the user to reply *yes, proceed* in-thread first. Local edits (`write_file`, `git_commit`) are staged without confirmation but are audit-logged.
- When blocked on confirmation, summarize the planned push/PR and ask the user to reply *yes, proceed*, then continue the workflow.
- If the user ran `@alfred plan` earlier in this thread, reuse that checklist — do not rewrite the plan from scratch.

# Example Slack request

```
@alfred pr on backend — add logging when order_id is missing in the checkout handler, include a unit test
```

Expected tool order: `grep_repo` → `read_file` → `git_prepare_branch` → `write_file` (code + test) → `git_commit` → `git_push_branch` → `create_pull_request`.
