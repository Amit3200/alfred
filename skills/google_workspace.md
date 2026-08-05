---
name: google_workspace
description: Read/write Google Sheets and read/create/append Google Docs
mode: investigation
trigger_keywords:
  - google sheet
  - google sheets
  - spreadsheet
  - google doc
  - google docs
  - gsheet
allowed_channels:
  - "*"
allowed_tools:
  - google_create_sheet
  - google_read_sheet
  - google_write_sheet
  - google_append_sheet
  - google_read_doc
  - google_create_doc
  - google_append_doc
requires_thread_context: false
---

# Google Workspace (Sheets + Docs)

Use when the user asks about Google Sheets or Google Docs data, or wants to update/create documents.

## Setup

- Admin → **Secrets**: paste or upload OAuth client JSON (or service account key).
- OAuth clients: Admin → **Integrations** → Google → **Connect Google** once.
- Share sheets/docs with the OAuth Google account or service account email.

## Sheets

1. Extract `spreadsheet_id` from the URL: `https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit`
2. **Read** → `google_read_sheet` with A1 range (e.g. `Sheet1!A1:Z100`).
3. **Create new** → `google_create_sheet` with title and optional `headers` / `rows`.
4. **Overwrite cells** → `google_write_sheet` with `rows` array (or legacy JSON string in `values`).
5. **Add rows** → `google_append_sheet` with anchor range (e.g. `Sheet1!A1`).

## Docs

1. Extract `document_id` from the URL: `https://docs.google.com/document/d/{document_id}/edit`
2. **Read** → `google_read_doc`.
3. **New doc** → `google_create_doc` with title and optional `body_text`.
4. **Append** → `google_append_doc` with plain text.

Summarize sheet/doc content for the user; do not dump huge tables verbatim unless asked.

## Rules

- When Google is connected (see **Google Workspace context** in the system prompt), you **have** access — never say you cannot use Sheets or Docs.
- Always use the Google tools for real data; never invent spreadsheet rows, doc links, or metrics from memory or prior assistant turns that claimed otherwise.
- If the user asks whether Google access is working, confirm connection status from context and offer to read or update a specific sheet/doc.
