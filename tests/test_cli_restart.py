"""CLI restart command tests."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from backend.cli import main


def test_restart_invokes_stop_then_up():
    runner = CliRunner()
    with patch("backend.cli.stop_all", return_value={"ok": True, "steps": [], "message": "stopped"}) as stop_mock, patch(
        "backend.cli.start_all",
        return_value={"ok": True, "steps": [], "message": "started"},
    ) as start_mock, patch("backend.cli.ConfigManager") as manager_cls:
        manager = manager_cls.return_value
        manager.is_initialized.return_value = True
        manager.load_merged.return_value = (manager.load_merged.return_value, None)

        result = runner.invoke(main, ["restart"])

    assert result.exit_code == 0, result.output
    stop_mock.assert_called_once()
    start_mock.assert_called_once()
