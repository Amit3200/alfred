"""System prompt addendum for Slack board create confirmations."""


def slack_board_create_addendum() -> str:
    return (
        "\n\n## Slack board task create\n"
        "A bootstrap step may have already created the list item from the thread. "
        "Confirm success from that block only — do not call slack_board_create_task again "
        "unless bootstrap failed or the user asked for different fields."
    )
