"""Tests for webhook handlers (PR merged, review comment)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from coddy.webhook.handlers import handle_github_event


@pytest.fixture
def config_pr_merged() -> "object":
    """Config with github platform and default_branch."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.default_branch = "main"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": "."})()}
    return config


def test_handle_pr_merged_pulls_and_exits(config_pr_merged: "object") -> None:
    """On pull_request closed+merged, run_git_pull is called and
    sys.exit(0)."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": True, "number": 1},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.services.git_runner.run_git_pull", create=True) as mock_pull:
        with patch("coddy.webhook.handlers.sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit(0)
            with pytest.raises(SystemExit, match="0"):
                handle_github_event(config_pr_merged, "pull_request", payload)
    mock_pull.assert_called_once()
    call_kw = mock_pull.call_args[1]
    assert call_kw["log"] is not None
    mock_exit.assert_called_once_with(0)


def test_handle_pr_merged_ignores_when_not_merged(config_pr_merged: "object") -> None:
    """pull_request closed but not merged does nothing."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": False},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.services.git_runner.run_git_pull", create=True) as mock_pull:
        with patch("coddy.webhook.handlers.sys.exit") as mock_exit:
            handle_github_event(config_pr_merged, "pull_request", payload)
    mock_pull.assert_not_called()
    mock_exit.assert_not_called()


def test_handle_pr_merged_ignores_other_repo(config_pr_merged: "object") -> None:
    """pull_request merged for another repo does nothing."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": True},
        "repository": {"full_name": "other/repo"},
    }
    with patch("coddy.services.git_runner.run_git_pull", create=True) as mock_pull:
        with patch("coddy.webhook.handlers.sys.exit") as mock_exit:
            handle_github_event(config_pr_merged, "pull_request", payload)
    mock_pull.assert_not_called()
    mock_exit.assert_not_called()


def test_handle_pr_merged_uses_repo_dir_when_passed(config_pr_merged: "object") -> None:
    """When repo_dir is passed, run_git_pull is called with that path."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": True},
        "repository": {"full_name": "owner/repo"},
    }
    custom_dir = Path("/tmp/bot-repo")
    with patch("coddy.services.git_runner.run_git_pull", create=True) as mock_pull:
        with patch("coddy.webhook.handlers.sys.exit", side_effect=SystemExit(0)):
            with pytest.raises(SystemExit):
                handle_github_event(
                    config_pr_merged,
                    "pull_request",
                    payload,
                    repo_dir=custom_dir,
                )
    mock_pull.assert_called_once()
    assert mock_pull.call_args[1]["repo_dir"] == custom_dir


def test_handle_pr_merged_no_exit_on_pull_failure(config_pr_merged: "object") -> None:
    """When run_git_pull raises, we do not call sys.exit."""
    from coddy.services.git_runner import GitRunnerError

    payload = {
        "action": "closed",
        "pull_request": {"merged": True},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.services.git_runner.run_git_pull", create=True, side_effect=GitRunnerError("pull failed")):
        with patch("coddy.webhook.handlers.sys.exit") as mock_exit:
            handle_github_event(config_pr_merged, "pull_request", payload)
    mock_exit.assert_not_called()


def test_handle_issues_assigned_enqueues_when_bot_in_assignees(tmp_path: Path) -> None:
    """On issues.assigned with bot in assignees, enqueue is called."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}

    payload = {
        "action": "assigned",
        "issue": {"number": 42, "assignees": [{"login": "coddy-bot"}, {"login": "other"}]},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.queue.enqueue") as mock_enqueue:
        handle_github_event(config, "issues", payload, repo_dir=tmp_path)
    mock_enqueue.assert_called_once()
    call_args = mock_enqueue.call_args[0]
    assert call_args[0] == tmp_path
    assert call_args[1] == "owner/repo"
    assert call_args[2] == 42


def test_handle_issues_assigned_ignores_when_bot_not_assignee(tmp_path: Path) -> None:
    """On issues.assigned without bot in assignees, enqueue is not called."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}

    payload = {
        "action": "assigned",
        "issue": {"number": 42, "assignees": [{"login": "other-user"}]},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.queue.enqueue") as mock_enqueue:
        handle_github_event(config, "issues", payload, repo_dir=tmp_path)
    mock_enqueue.assert_not_called()
