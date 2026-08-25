from backend.domains.jira.description import enrich_jira_create_description
from backend.models.task import Task


def _task(text: str) -> Task:
    return Task(
        source="slack",  # type: ignore[arg-type]
        user_id="U1",
        channel_id="C123",
        thread_ts="111.222",
        raw_text=text,
        cleaned_intent=text,
    )


def test_empty_description_gets_request_and_slack_link():
    text = enrich_jira_create_description(
        "",
        summary="Show COD disable reason in tech",
        task=_task("create the same task on JIRA on TECH board"),
        channel_id="C123",
        thread_ts="111.222",
    )
    assert "Show COD disable reason in tech" in text
    assert "create the same task on JIRA on TECH board" in text
    assert "Slack thread:" in text
    assert "C123" in text


def test_llm_description_keeps_text_and_appends_missing_slack_link():
    text = enrich_jira_create_description(
        "Show why COD is disabled in checkout.",
        summary="Show COD disable reason in tech",
        task=_task("create the same task on JIRA on TECH board"),
        session_metadata={
            "last_board_task": {
                "display_id": "TS-23",
                "record_id": "RecABC",
                "list_name": "Tech Tasks",
            }
        },
        channel_id="C123",
        thread_ts="111.222",
    )
    assert text.startswith("Show why COD is disabled in checkout.")
    assert "TS-23" in text
    assert "Slack thread:" in text
    assert "C123" in text


def test_does_not_duplicate_existing_slack_link():
    link = "https://slack.com/archives/C123/p111222"
    text = enrich_jira_create_description(
        f"Details here.\nSlack thread: {link}",
        channel_id="C123",
        thread_ts="111.222",
    )
    assert text.count(link) == 1
