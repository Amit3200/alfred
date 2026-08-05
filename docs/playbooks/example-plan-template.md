---
name: redirect_report
type: plan_template
description: Run redirect metrics script and publish to Google Sheet
triggers:
  - redirect metrics
  - redirection report
plan_template:
  goal: Build redirect metrics report
  intent_class: template.redirect_report
  steps:
    - tool: run_company_script
      purpose: collect redirect metrics
      args:
        script: redirect_metrics
    - tool: google_create_sheet
      purpose: create spreadsheet for results
    - tool: google_write_sheet
      purpose: write metrics rows
---

# Redirect report plan template

This file is an **example plan template** — copy into `.alfred/playbooks/` locally.

When a user message matches a trigger, the tool planner uses this structured plan
instead of keyword skill routing or LLM planning.

Link the script in `.alfred/scripts/redirect_metrics/script.yaml` and add matching
`triggers:` there for script-specific routing.
