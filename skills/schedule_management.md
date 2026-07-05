---
name: schedule_management
description: Manage background scheduled jobs and trigger automations.
mode: workflow
triggers:
  - schedule a
  - list schedules
  - delete schedule
  - toggle schedule
  - schedule job
  - manage schedules
allowed_tools:
  - create_schedule
  - list_schedules
  - toggle_schedule
  - delete_schedule
---

# Objective
Help the user manage, list, activate, deactivate, delete, and configure scheduled automation tasks (cron jobs).

# Guidelines

## First-time Scheduler Flow (Detail Gathering)
When a user requests to schedule a task or "work" (e.g., *"schedule a daily query of grade events"*):
1. **Check for Details**: Verify if the user has provided specific instructions on *what* work should run (e.g., the target channel, what query to execute, what repository to analyze, etc.).
2. **Clarification**: If details are missing or vague, politely ask the user for clarification:
   - *"What specific query or command should this run?"*
   - *"Which channel/repository should this analyze or post to?"*
   - *"Are there specific filters, logs, or metrics you want to extract?"*
3. **Save**: Once the user provides the details, compile those details into a clear set of sequential instructions, then call `create_schedule` with a descriptive name, the cron expression, and the compiled instructions.

## Listing and Managing Schedules
- To list current schedules, use the `list_schedules` tool and present them in a clean, readable table format listing the Job ID, Name, Cron Expression, Target Skill, and active status.
- To disable/enable or delete a schedule, call `toggle_schedule` or `delete_schedule` using the Job ID.
