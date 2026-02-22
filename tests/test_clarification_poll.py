"""Tests for observer clarification poll (post agent question to platform)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coddy.observer.clarification_poll import run_clarification_poll
from coddy.services.store import create_issue, load_issue, set_agent_clarification


def test_clarification_poll_posts_and_marks_sent(tmp_path: Path) -> None:
    """When issue has waiting_user_reply and message, poll posts and marks clarification_sent."""
    create_issue(tmp_path, 1, "owner/repo", "T", "D", "@u")
    set_agent_clarification(tmp_path, 1, "Please specify the API version.", bot_name="@bot")

    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = "token"
    config.github = MagicMock()
    config.github.api_url = "https://api.github.com"

    mock_adapter = MagicMock()
    with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
        run_clarification_poll(config, tmp_path)

    mock_adapter.create_comment.assert_called_once()
    assert mock_adapter.create_comment.call_args[0] == ("owner/repo", 1, "Please specify the API version.")
    mock_adapter.set_issue_labels.assert_called_once_with("owner/repo", 1, ["stuck"])

    issue = load_issue(tmp_path, 1)
    assert issue is not None
    assert issue.status == "clarification_sent"


def test_clarification_poll_skips_when_already_sent(tmp_path: Path) -> None:
    """After posting, status is clarification_sent so poll does not process the issue again."""
    create_issue(tmp_path, 2, "owner/repo", "T", "D", "@u")
    set_agent_clarification(tmp_path, 2, "Question?", bot_name="@bot")
    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = "token"
    config.github = MagicMock()
    config.github.api_url = "https://api.github.com"
    mock_adapter = MagicMock()
    with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
        run_clarification_poll(config, tmp_path)
        run_clarification_poll(config, tmp_path)
    mock_adapter.create_comment.assert_called_once()
