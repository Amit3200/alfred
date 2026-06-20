================================================================================
ENGINEERING BLUEPRINT: GOVERNED DEVOPS AGENT (V1 LOCAL ARCHITECTURE)
================================================================================
Target Runtime: Python 3.10+
Architecture: Single-process, event-driven, local-first (Zero-Ops)
Goal: An autonomous agent triggered via CLI/Slack/Git that dynamically loads
      skills from Markdown files and executes local shell/API commands securely.
================================================================================

1. CORE ARCHITECTURAL PRINCIPLES (V1)
--------------------------------------------------------------------------------
- Zero-Ops Dependency: No cloud infra required on day one. State is stored in 
  SQLite; context search uses local keyword/BM25 indexing or an embedded vector DB.
- Loose Coupling via Abstractions: All major subsystems (Queue, Storage, LLM, Index) 
  must be implemented behind Python Abstract Base Classes (ABCs) to allow direct 
  migration to cloud variants (e.g., SQS, PostgreSQL, Pinecone) later.
- Strict Governance: The LLM cannot execute raw actions arbitrarily; it can only 
  execute tools explicitly declared and authorized by the matched Markdown skill file.

2. COMPONENT SPECIFICATIONS
--------------------------------------------------------------------------------
A. Interface & Ingestion Layer
   - CLI Module: A simple terminal entrypoint (`python main.py exec <command>`) 
     for quick local iteration and local Git hook integration.
   - Webhook Server: A lightweight FastAPI instance that listens for incoming 
     payloads from Slack (Slash commands/events) or GitLab/GitHub webhooks.
   - Event Sanitizer: Extracts the raw user intent string, author ID, and channel source.

B. Task Router & Local Queue (SQLite-backed)
   - Abstract Base Class: `BaseQueue` with methods `push(task)`, `pop()`, `ack(task_id)`.
   - V1 Implementation: Uses a background worker thread polling a thread-safe 
     in-memory queue (`queue.Queue`) backed by an SQLite table (`tasks`) for crash-resilience.
   - Purpose: Instantly returns a HTTP 200 "Acknowledged" to Slack/Git to avoid timeouts, 
     then passes the job off to the async execution loop.

C. Index-Driven Context Engine
   - Directory Watcher: Monitors a local directory (e.g., `./skills/*.md`).
   - Parsing Engine: Extracts YAML Front-Matter from the top of the MD files to read 
     metadata fields (triggers, permissions, channel locks).
   - In-Memory Matcher: For V1, a simple TF-IDF or BM25 text matcher (or local ChromaDB) 
     compares the user query against the metadata fields/descriptions to pull the 
     EXACT single Markdown skill file required for the execution. 
   - Rule: Never load the entire directory into the LLM context window.

D. The Agent Execution Loop (ReAct Framework)
   - Core Brain: Leverages the LangChain/Structured Tool Calling or raw system prompt 
     loops with Claude (Anthropic API) or Gemini (Google GenAI SDK).
   - Prompt Assembler: Dynamically compiles a system prompt containing:
     1. General agent guardrails.
     2. The specific execution instructions from the loaded Markdown file.
     3. The precise string-defined schemas of the allowed tools.
   - The Execution Loop: 
     [LLM generates thought/action] -> [Tool Runner executes locally] -> 
     [Output piped back as observation] -> [LLM processes updated state].

3. SPECIFICATION: MARKDOWN SKILL PATTERN (e.g., `skills/deploy_hotfix.md`)
--------------------------------------------------------------------------------
---
name: deploy_hotfix
description: Automatically cherry-picks a commit and opens a hotfix production PR
trigger_keywords: ["hotfix", "cherry-pick to prod"]
allowed_channels: ["#ops-alerts", "terminal"]
allowed_tools: ["git_checkout", "git_cherry_pick", "git_push", "create_gitlab_pr"]
---

# Objective
Safely cherry-pick a bugfix commit from the development branch into the production release branch.

# Execution Steps
1. Checkout the `main` branch and pull the latest code.
2. Create a new branch named `hotfix/<commit-id>`.
3. Cherry-pick the target commit hash provided by the user.
4. Resolve conflicts automatically if safe, otherwise fail instantly and alert user.
5. Push the branch and open a Pull Request against `main`.

# Governance Rules
- CRITICAL: Never push directly to `main` or `master`.
- If any unit test fails during local verification, abort the process entirely.

4. STEP-BY-STEP V1 IMPLEMENTATION ROADMAP
--------------------------------------------------------------------------------
Phase 1: Project Scaffolding & Abstractions (Days 1-2)
  [ ] Initialize Python environment, define `requirements.txt`.
  [ ] Write abstract interfaces (`QueueProvider`, `LLMProvider`, `StorageProvider`).
  [ ] Implement the CLI entrypoint and the SQLite-backed task store.

Phase 2: Local Context Engine & MD Parser (Days 3-4)
  [ ] Write the YAML/Markdown file parser.
  [ ] Implement a simple local keyword-based or semantic matcher to find the 
      correct `.md` file given an input command.
  [ ] Unit test: Verify that sending "fix a prod bug" successfully isolates 
      and reads `skills/deploy_hotfix.md` without reading other files.

Phase 3: The Tool Execution Box (Days 5-6)
  [ ] Build a localized tool registry mapping string names to safe Python operations 
      (e.g., running `subprocess.run` safely for git commands, calling boto3 for AWS).
  [ ] Implement input validation constraints to block forbidden keywords (like `rm -rf /` or `delete-stack`).

Phase 4: Agent Core & ReAct Loop (Days 7-9)
  [ ] Implement the core agent loop using Anthropic/Gemini APIs.
  [ ] Construct the dynamic prompt injector that reads the chosen MD file and 
      forces the LLM to stay within its objective and allowed tools boundaries.
  [ ] Handle state preservation so the agent remembers previous steps inside the loop.

Phase 5: Ingestion Webhooks & End-to-End Local Run (Days 10-12)
  [ ] Spin up a FastAPI webhook endpoint exposed via local tunnel/ngrok to Slack.
  [ ] Run an end-to-end integration test: Send a command via Slack, process it via the 
      local background worker thread, modify a local git repo, and post the output back to Slack.

5. MINIMAL PYTHON DEPENDENCIES (`requirements.txt`)
--------------------------------------------------------------------------------
fastapi>=0.100.0
uvicorn>=0.22.0
pydantic>=2.0.0
google-genai>=0.1.0        # For Gemini native tool calling/inference
anthropic>=0.15.0         # For Claude native tool calling/inference
pyyaml>=6.0.0             # To parse front-matter from MD files
chromadb>=0.4.0           # (Optional) For embedded, zero-ops vector indexing
sqlalchemy>=2.0.0         # Zero-config mapping to local SQLite
requests>=2.31.0          # Outbound API notifications (Slack/GitLab)
================================================================================