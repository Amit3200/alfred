"""Direct tool paths: workflow, PR, planned, repo-doc QA."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Literal

from backend.ai.base import Message
from backend.ai.registry import LLMRouter
from backend.orchestrator.policy import (
    needs_context_refresh,
    omit_assistant_session_history,
)
from backend.orchestrator.task_cancel import TaskCancelledError, raise_if_cancelled
from backend.routing.playbook_store_registry import get_playbook_store
from backend.routing.playbooks import Playbook, PlaybookStore
from backend.orchestrator.prompts import GITHUB_COMMENT_RULES, build_alfred_system_prompt, build_slack_user_message
from backend.formatting.render import Channel, render_for_channel
from backend.formatting.sanitize import clean_response_scaffold
from backend.integrations.slack.context import SlackContextBundle
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse, ResponsePayload
from backend.models.session import ConversationSession, mirror_workspace_key, task_session_key
from backend.models.task import Task
from backend.paths import get_data_dir
from backend.db.session_store import SessionStore
from backend.tools.result import ToolResult
from backend.orchestrator.processor.helpers import (
    _tool_result_to_response,
    _unified_metadata_patch,
)

logger = logging.getLogger(__name__)


class DirectMixin:
    def _try_workflow_entry(
        self,
        skill: Playbook | None,
        task: Task,
        *,
        session: ConversationSession | None,
        slack_context: str | None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Gate create-PR / plan commands; ask clarifying questions or run plan-only flow."""
        if skill is None:
            return None, None

        from backend.orchestrator.workflow_gates import gate_create_pr, gate_plan_task
        from backend.orchestrator.planning import generate_standalone_plan

        if skill.name == "create_pr":
            gate = gate_create_pr(
                task,
                self.config,
                session=session,
                slack_context=slack_context,
            )
            if not gate.ready:
                return AssistantResponse.from_text(gate.message), gate.metadata_patch or None
            if gate.enriched_intent:
                task.cleaned_intent = gate.enriched_intent
            from backend.orchestrator.planning import adopt_session_plan_for_task

            patch = dict(gate.metadata_patch or {})
            adopted = adopt_session_plan_for_task(task, session, self._data_dir_path())
            if adopted:
                patch["plan_file"] = adopted
            return None, patch or None

        if skill.name == "plan_task":
            gate = gate_plan_task(
                task,
                self.config,
                session=session,
                slack_context=slack_context,
            )
            if not gate.ready:
                return AssistantResponse.from_text(gate.message), gate.metadata_patch or None
            if gate.enriched_intent:
                task.cleaned_intent = gate.enriched_intent
            context_parts = [slack_context or ""]
            if session and session.context_snapshot and session.context_snapshot not in context_parts:
                context_parts.append(session.context_snapshot)
            plan_text, plan_path = generate_standalone_plan(
                task,
                self.config,
                context="\n\n".join(p for p in context_parts if p).strip(),
                data_dir=self._data_dir,
                task_kind="workflow_execution",
            )
            if not plan_text:
                return (
                    AssistantResponse.from_text(
                        "I couldn't generate a plan — check Admin → AI (Workflow execution provider) and try again."
                    ),
                    gate.metadata_patch,
                )
            path_note = f"\n\n_Saved to `{plan_path}`_" if plan_path else ""
            body = f"*Task plan*\n\n{plan_text}{path_note}"
            patch = dict(gate.metadata_patch or {})
            if plan_path:
                patch["plan_file"] = plan_path
            return AssistantResponse.from_text(body), patch

        return None, None

    def _resolve_pr_review_skill(
        self,
        investigation: Playbook | None,
        task: Task,
        session: ConversationSession | None,
    ) -> Playbook | None:
        """Return the review_pr skill when intent is a PR review or thread follow-up."""
        from backend.routing.git.direct import should_run_pr_analysis

        if investigation and investigation.name == "review_pr":
            return investigation
        if should_run_pr_analysis(task.cleaned_intent, session):
            return self._playbooks.get_by_name("review_pr")
        return None

    def _prefetch_pr_context(
        self,
        task: Task,
        *,
        session: ConversationSession | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Gather PR facts for injection; analysis is driven by the review_pr skill."""
        from backend.routing.git.direct import resolve_pr_for_analysis
        from backend.integrations.git.pr_analysis import format_pr_context_for_prompt, gather_pr_context

        ref = resolve_pr_for_analysis(task.cleaned_intent, session)
        if not ref:
            return "", None

        repo, number = ref
        logger.info("Pre-fetching PR context: %s #%s", repo, number)
        try:
            ctx = gather_pr_context(
                self.config,
                data_dir=self._data_dir_path(),
                workspace_id=mirror_workspace_key(task),
                repo=repo,
                number=number,
            )
        except RuntimeError as exc:
            logger.warning("PR context fetch failed: %s", exc)
            return "", None
        except Exception:
            logger.exception("PR context fetch failed")
            return "", None

        return format_pr_context_for_prompt(ctx), ctx.metadata

    def _try_unified_direct(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None = None,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Try running direct actions unified under a single router entry point."""
        from backend.routing.intent import detect_direct_action
        from backend.tools.builder import build_git_tool_registry

        direct = detect_direct_action(
            task.cleaned_intent,
            self.config,
            task,
            session=session,
            playbook=skill,
            data_dir=self._data_dir_path(),
        )
        if not direct:
            return None, None

        tool_name, tool_args = direct
        if not skill.allowed_tools or tool_name not in skill.allowed_tools:
            from backend.routing.git.direct import wants_pr_code_analysis, wants_pr_summary

            if (
                tool_name == "get_pr"
                and wants_pr_summary(task.cleaned_intent)
                and not wants_pr_code_analysis(task.cleaned_intent)
            ):
                git_skill = self._playbooks.get_by_name("git_status")
                if git_skill and git_skill.name != skill.name:
                    return self._try_unified_direct(git_skill, task, session)
            logger.info("Direct tool %s detected but not in allowed_tools for %s", tool_name, skill.name)
            return None, None

        logger.info("Unified direct execution: running tool %s", tool_name)

        # 1. Custom built-in direct handlers
        if tool_name == "lookup_user_identity":
            from backend.integrations.identity.user_identity import format_user_identity_result, lookup_user_identity

            data = lookup_user_identity(
                self.config,
                task=task,
                data_dir=self._data_dir_path(),
                slack_user_id=str(tool_args.get("slack_user_id") or ""),
                query=str(tool_args.get("query") or ""),
                targets=tool_args.get("targets"),
            )
            if data.get("error"):
                return AssistantResponse.error(str(data["error"])), None
            return AssistantResponse.from_text(format_user_identity_result(data)), None

        if tool_name == "build_workspace_identity_map":
            from backend.integrations.identity.user_identity import (
                build_workspace_identity_map,
                format_user_identity_result,
            )

            data = build_workspace_identity_map(
                self.config,
                data_dir=self._data_dir_path(),
                include_github=bool(tool_args.get("include_github", True)),
            )
            if data.get("error"):
                return AssistantResponse.error(str(data["error"])), None
            return AssistantResponse.from_text(format_user_identity_result(data)), None

        # 2. Standard registry-driven tools (JIRA/Git/AWS)
        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=skill.allowed_tools or None,
        )
        self._attach_governance(registry, task, session=session, skill_name=skill.name)

        result = registry.run_normalized(
            tool_name,
            tool_args,
            allowed=skill.allowed_tools,
            git=self.config.git,
            session=session,
        )
        if result.kind == "error":
            return AssistantResponse.error(result.data.get("message", f"Tool {tool_name} failed.")), None

        patch = _unified_metadata_patch(tool_name, tool_args, result)

        from backend.routing.git.direct import wants_pr_summary, wants_pr_code_analysis

        if tool_name == "get_pr" and wants_pr_summary(task.cleaned_intent):
            detail = result.data.get("pr")
            if detail and not wants_pr_code_analysis(task.cleaned_intent):
                summary = self._summarize_pr(detail, task)
                if not summary:
                    from backend.formatting.strategies import format_pr_detail

                    summary = format_pr_detail({"pr": detail}, slack=task.source == "slack")
                return AssistantResponse.from_text(summary), patch

        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, patch
        return None, patch

    def _execute_planned_direct(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None,
        plan: Any,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Run a single-step tool plan without the ReAct loop (fast path)."""
        from backend.routing.tool_plan_types import ToolPlan

        if not isinstance(plan, ToolPlan) or len(plan.steps) != 1:
            return None, None

        step = plan.steps[0]
        tool_name = step.tool
        tool_args = dict(step.args_hint or {})

        if plan.intent_class == "repo.docs.qa" and tool_name == "search_repo_docs":
            # Doc Q&A uses LangGraph worker (search → read → grounded answer), not the BM25 fast path.
            return None, None

        if tool_name == "save_html_deck":
            # Slides require the LLM to synthesize HTML before calling the tool.
            return None, None

        if tool_name == "connector_get_messages" or str(plan.intent_class or "").startswith(
            "connector.read.messages"
        ):
            # Message windows need the worker so the model can summarize per chat.
            return None, None

        if tool_name == "publish_html_artifact":
            from backend.routing.html_slides_delivery import (
                publish_args_complete,
                resolve_publish_html_args,
            )

            tool_args = resolve_publish_html_args(
                tool_args,
                task=task,
                session_metadata=dict(session.metadata if session else {}),
            )
            if not publish_args_complete(tool_args):
                return None, None

        from backend.routing.slack_board.agent import SLACK_BOARD_WRITE_TOOLS

        if tool_name in SLACK_BOARD_WRITE_TOOLS:
            return None, None

        if not skill.allowed_tools or tool_name not in skill.allowed_tools:
            return None, None

        from backend.tools.builder import build_git_tool_registry

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=skill.allowed_tools or None,
        )
        self._attach_governance(registry, task, session=session, skill_name=skill.name)
        result = registry.run_normalized(
            tool_name,
            tool_args,
            allowed=skill.allowed_tools,
            git=self.config.git,
            session=session,
        )
        if result.kind == "error":
            return AssistantResponse.error(result.data.get("message", f"Tool {tool_name} failed.")), None
        patch = _unified_metadata_patch(tool_name, tool_args, result)
        structured = _tool_result_to_response(result)
        if structured is not None:
            return structured, patch
        text = str(result.data.get("text") or "").strip()
        if text:
            return AssistantResponse.from_text(text), patch
        return None, patch

    def _execute_repo_doc_qa_direct(
        self,
        skill: Playbook,
        task: Task,
        session: ConversationSession | None,
        query: str,
    ) -> tuple[AssistantResponse | None, dict[str, Any] | None]:
        """Search indexed docs, read the top hit, and synthesize a grounded answer."""
        from backend.formatting.intent_formatters import format_doc_search
        from backend.observability.checkpoint import log_checkpoint
        from backend.routing.reply_meta import attach_reply_meta, doc_reply_meta
        from backend.tools.builder import build_git_tool_registry

        allowed = list(skill.allowed_tools or [])
        if "search_repo_docs" not in allowed:
            repo_skill = self._playbooks.get_by_name("repo_knowledge")
            if repo_skill and repo_skill.allowed_tools:
                allowed = list(repo_skill.allowed_tools)
                skill = repo_skill

        registry = build_git_tool_registry(
            self.config,
            workspace_id=mirror_workspace_key(task),
            data_dir=self._data_dir_path(),
            allowed_tools=allowed or None,
        )
        self._attach_governance(registry, task, session=session, skill_name=skill.name)

        log_checkpoint("doc_tool_call", "search_repo_docs", "started")
        search_result = registry.run_normalized(
            "search_repo_docs",
            {"query": query},
            allowed=allowed,
            git=self.config.git,
            session=session,
        )
        if search_result.kind == "error":
            log_checkpoint("doc_tool_call", "search_repo_docs", "error", error=RuntimeError(str(search_result.data.get("message") or "Doc search failed.")))
            return AssistantResponse.error(str(search_result.data.get("message") or "Doc search failed.")), None

        if not search_result.data.get("found"):
            log_checkpoint("doc_tool_call", "search_repo_docs", "completed")
            from backend.context.doc_index import describe_missing_doc_topic, significant_query_tokens
            from backend.routing.chat_persona import normalize_persona

            if significant_query_tokens(query):
                topic = describe_missing_doc_topic(query)
                body = (
                    f"**No** — **{topic}** is not documented in indexed support documentation. "
                    "It does not appear to be a supported integration in our handbook."
                )
                meta = doc_reply_meta(query, None, not_found=True)
                return (
                    attach_reply_meta(AssistantResponse.from_text(body), meta),
                    {"last_intent_class": "repo.docs.qa", "reply_meta": meta},
                )

            persona = str(task.metadata.get("chat_persona_effective") or task.metadata.get("chat_persona") or "")
            if normalize_persona(persona) == "support" and self.config.web_search.enabled and "web_search" in allowed:
                log_checkpoint("doc_tool_call", "web_search", "started")
                web_result = registry.run_normalized(
                    "web_search",
                    {"query": query},
                    allowed=allowed,
                    git=self.config.git,
                    session=session,
                )
                if web_result.kind != "error" and web_result.data.get("results"):
                    log_checkpoint("doc_tool_call", "web_search", "completed")
                    from backend.formatting.strategies import WebSearchFormatter

                    body = WebSearchFormatter().render(web_result.data, slack=False)
                    prefix = (
                        "I couldn't find this in indexed documentation. "
                        "Here's what I found on the web instead:\n\n"
                    )
                    meta = doc_reply_meta(query, None, web_fallback=True)
                    return (
                        attach_reply_meta(AssistantResponse.from_text(prefix + body), meta),
                        {"reply_meta": meta},
                    )
                log_checkpoint("doc_tool_call", "web_search", "completed")
            return (
                AssistantResponse.structured(
                    "doc_search",
                    {"query": query, "results": [], "found": False},
                ),
                None,
            )

        log_checkpoint("doc_tool_call", "search_repo_docs", "completed")
        hits = list(search_result.data.get("results") or [])
        from backend.context.doc_index import describe_missing_doc_topic, pick_best_doc_hit, significant_query_tokens

        top = pick_best_doc_hit(hits, query)
        if top is None:
            if hits and significant_query_tokens(query):
                topic = describe_missing_doc_topic(query)
                body = (
                    f"**No** — **{topic}** is not documented in indexed support documentation. "
                    "It does not appear to be a supported integration in our handbook."
                )
                meta = doc_reply_meta(query, None, not_found=True)
                return (
                    attach_reply_meta(AssistantResponse.from_text(body), meta),
                    {"last_intent_class": "repo.docs.qa", "reply_meta": meta},
                )
            return (
                AssistantResponse.structured(
                    "doc_search",
                    {"query": query, "results": [], "found": False},
                ),
                None,
            )
        doc_path = str(top.get("path") or "")
        doc_repo = str(top.get("repo") or "").strip()
        if doc_path:
            log_checkpoint("doc_found", doc_path, "completed")
        if doc_repo:
            log_checkpoint("repo_context", doc_repo, "completed")
        read_args: dict[str, Any] = {"path": doc_path}
        if doc_repo:
            read_args["repo"] = doc_repo

        doc_content = str(top.get("excerpt") or "")
        if "read_repo_doc" in allowed and doc_path:
            log_checkpoint("doc_tool_call", "read_repo_doc", "started")
            read_result = registry.run_normalized(
                "read_repo_doc",
                read_args,
                allowed=allowed,
                git=self.config.git,
                session=session,
            )
            if read_result.kind != "error":
                doc_content = str(read_result.data.get("content") or doc_content)
                log_checkpoint("doc_tool_call", "read_repo_doc", "completed")
            else:
                log_checkpoint(
                    "doc_tool_call",
                    "read_repo_doc",
                    "error",
                    error=RuntimeError(str(read_result.data.get("message") or "Read failed.")),
                )

        log_checkpoint("doc_synthesis", "summarize", "started")
        answer = self._synthesize_doc_answer(
            task.cleaned_intent,
            doc_path=doc_path,
            doc_content=doc_content,
            repo=doc_repo,
        )
        log_checkpoint("doc_synthesis", "summarize", "completed")
        from backend.context.doc_assets import build_doc_answer_payload

        meta = doc_reply_meta(query, top)
        payload = build_doc_answer_payload(
            text=answer,
            doc_path=doc_path,
            repo=doc_repo,
            doc_content=doc_content,
        )
        response = AssistantResponse.structured("doc_answer", payload, text=str(payload.get("text") or answer))
        return (
            attach_reply_meta(response, meta),
            {
                "last_intent_class": "repo.docs.qa",
                "doc_path": doc_path,
                "doc_repo": doc_repo,
                "reply_meta": meta,
            },
        )


