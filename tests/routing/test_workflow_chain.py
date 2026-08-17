"""Skill workflow_chain and BaseTool function chaining."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.playbooks import PlaybookStore, _parse_playbook_index
from backend.routing.tool_planner import resolve_tool_plan
from backend.routing.types import RouteContext
from backend.routing.workflow_chain import plan_from_playbook_chain
from backend.tools.base.chain import chain_from_tools
from backend.tools.jira.write import JiraAssignIssueTool, JiraCreateIssueTool
from backend.tools.schedule.tools import schedule_tools


def test_jira_create_chain_hint_walks_next_tools():
    ordered = chain_from_tools(
        [JiraCreateIssueTool(), JiraAssignIssueTool()],
        start="jira_create_issue",
    )
    assert ordered[0] == "jira_create_issue"
    assert "jira_assign_issue" in ordered


def test_schedule_tools_share_base_contract():
    tools = {tool.name: tool for tool in schedule_tools()}
    create = tools["create_schedule"]
    assert create.domain == "schedule"
    assert create.capability == "schedule.write.create"
    assert "job_id" in create.produces
    assert create.chain_hint()


def test_bundled_skills_parse_workflow_chain():
    store = PlaybookStore()
    by_name = {pb.name: pb for pb in store.list_playbooks()}
    assert by_name["html_slides"].workflow_chain == ["save_html_deck", "publish_html_artifact"]
    assert by_name["html_slides"].use_workflow_chain
    assert by_name["create_pr"].workflow_chain[0] == "git_prepare_branch"
    assert by_name["create_pr"].use_workflow_chain
    assert by_name["repo_knowledge"].workflow_chain == ["search_repo_docs", "read_repo_doc"]
    assert by_name["jira_management"].workflow_chain[0] == "jira_create_issue"
    assert not by_name["jira_management"].use_workflow_chain


def test_plan_from_playbook_chain_filters_to_allowed(tmp_path):
    path = tmp_path / "chained.md"
    path.write_text(
        """---
name: chained
mode: investigation
allowed_tools:
  - search_repo_docs
  - read_repo_doc
workflow_chain:
  - search_repo_docs
  - read_repo_doc
  - web_search
---
# body
""",
        encoding="utf-8",
    )
    playbook = _parse_playbook_index(path, bundled=False)
    plan = plan_from_playbook_chain(playbook)
    assert plan is not None
    assert plan.strategy == "workflow_chain"
    assert plan.tools_needed == ["search_repo_docs", "read_repo_doc"]


def test_resolve_tool_plan_uses_skill_workflow_chain(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "chain_only.md").write_text(
        """---
name: chain_only
mode: investigation
allowed_tools:
  - search_repo_docs
  - read_repo_doc
workflow_chain:
  - search_repo_docs
  - read_repo_doc
use_workflow_chain: true
---
# body
""",
        encoding="utf-8",
    )
    config = AlfredConfig()
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text="hello",
        cleaned_intent="hello there",
    )
    context = RouteContext(intent=task.cleaned_intent, channel_id="C1")
    plan = resolve_tool_plan(
        config,
        task,
        context,
        skill_allowed=["search_repo_docs", "read_repo_doc"],
        playbook_store=PlaybookStore(tmp_path),
    )
    assert plan is not None
    assert plan.strategy == "workflow_chain"
    assert plan.tools_needed == ["search_repo_docs", "read_repo_doc"]
