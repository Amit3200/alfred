"""System prompt addendum for Slack board create confirmations."""


def slack_board_create_addendum() -> str:
    return slack_board_agentic_addendum(intent_class="slack.board.create")


def slack_board_agentic_addendum(*, intent_class: str = "") -> str:
    from backend.routing.slack_board_agent import slack_board_agentic_addendum as _addendum

    return _addendum(intent_class=intent_class)
