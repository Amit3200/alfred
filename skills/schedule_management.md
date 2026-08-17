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
  - update schedule
  - edit schedule
allowed_tools:
  - create_schedule
  - list_schedules
  - toggle_schedule
  - delete_schedule
  - update_schedule
  - list_company_scripts
  - read_company_script_file
  - write_company_script_file
  - create_company_script_package
  - run_company_script
allowed_capabilities:
  - schedule.write.create
  - schedule.read.list
  - schedule.write.toggle
  - schedule.write.delete
  - schedule.write.update
workflow_chain:
  - list_schedules
  - create_schedule
---

# Objective
Help the user manage, list, activate, deactivate, delete, update, and configure scheduled automation tasks (cron jobs).

# Guidelines

## Scripts + accuracy
When the job should run the same query or report every time, **create or update** a package under  
**`.alfred/scripts/`** using `create_company_script_package` and `write_company_script_file`, then  
reference it by name in the schedule instructions (e.g. *"run company script `checkout/daily_report`  
with yesterday's date"*). Generated schedule playbooks include `run_company_script` for execution.

If a suitable script already exists, use `list_company_scripts` / `read_company_script_file` instead of  
recreating it. Admins can review and edit packages anytime in **Configure → Scripts**.

## First-time Scheduler Flow (Detail Gathering)
When a user requests to schedule a task or "work" (e.g., *"schedule a daily Athena summary"*):
1. **Check for Details**: Verify if the user has provided specific instructions on *what* work should run (e.g., what query to execute, what repository to analyze, etc.).
2. **Clarification**: If details are missing or vague, politely ask the user for clarification.
3. **Target Channel ID**: When the user requests to post/report the results to "this channel" or the current channel, always extract the current channel ID from the task/message metadata (e.g., `C...` or `D...`) and pass it as the `channel_id` parameter to the `create_schedule` or `update_schedule` tool. Do not leave it empty/None if the user expects it to post to their current location.
4. **Save**: Call `create_schedule` with a descriptive name, the cron expression, the current channel's ID as `channel_id`, and the compiled instructions.

## Listing, Updating, and Managing Schedules
- To list current schedules, use the `list_schedules` tool.
- To update an existing schedule (e.g. changing its target channel, cron pattern, or instructions), call `update_schedule` using the `job_id`.
- To disable/enable or delete a schedule, call `toggle_schedule` or `delete_schedule` using the `job_id`.
