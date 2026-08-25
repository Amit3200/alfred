---
name: connector_management
description: Pull WhatsApp chats, tickets, and tasks from Periskope (and other inbound connectors) and summarize groups. Replicate work onto Slack Lists or JIRA using existing Alfred tools when asked.
mode: investigation
trigger_keywords:
  - periskope
  - whatsapp
  - whatsapp group
  - whatsapp ticket
  - connector
  - daily summary
  - group summary
allowed_channels:
  - "*"
allowed_capabilities:
  - connector.read.list
  - connector.read.chats
  - connector.read.tickets
  - connector.read.tasks
  - connector.read.messages
  - connector.read.poll
  - slack_write.create
  - jira.write.create
allowed_tools:
  - connector_list
  - connector_list_chats
  - connector_list_tickets
  - connector_list_tasks
  - connector_get_messages
  - connector_poll
  - slack_board_create_task
  - jira_create_issue
---

# Connector / Periskope

Inbound connectors (first: **Periskope**) pull WhatsApp work into Alfred. Do **not** invent a second ticketing system — use Slack Lists and JIRA tools that already exist.

## Read first

1. `connector_list` if the source is unclear.
2. `connector_list_chats` for groups (`chat_id` ending `@g.us`).
3. `connector_list_tickets` / `connector_list_tasks` for Periskope work items.
4. `connector_get_messages` for WhatsApp history. `chat_id` is optional. For a daily summary across groups, omit `chat_id` and pass `start_time` / `end_time` (YYYY-MM-DD or `22nd August`). That hits `GET /chats/messages` (the only Periskope list endpoint that supports a date window). Then summarize **per chat_id** — do not dump every line.
5. `connector_list_chats` to attach human names to those `chat_id`s.
6. `connector_poll` to pull tickets/tasks over REST **without a webhook**. Default is preview only. Set `replicate=true` only when the user wants Slack List / JIRA cards created from that pull.

## Summaries

When asked to summarize a group, fetch messages for the requested window, then write a short Slack-ready digest: themes, open questions, ticket ids, owners. Do not dump every line.

## Creating Alfred work

- Webhook replica uses the Slack channel configured in Integrations → Periskope. Tickets and tasks land on the Slack List bound to that channel.
- Slack List: `slack_board_create_task` (one card per Periskope ticket/task).
- JIRA: `jira_create_issue` only if the user asked for JIRA or `ticket_create_target` is jira/both.
- Prefer the live webhook replica when the user only wants items that already landed on the board.

## Do not

- Create extra cards from Alfred confirmation metadata.
- Subscribe to or treat every WhatsApp `message.created` as a ticket.
- Send WhatsApp messages unless the user explicitly asks later (send is not in this skill).
