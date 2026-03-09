"""Tests for observer clarification poll, plan post poll, and create PR
poll."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coddy.observer.clarification_poll import (
    run_clarification_poll,
    run_create_pr_poll,
    run_plan_post_poll,
)
from coddy.services.store import (
    add_comment,
    create_issue,
    load_issue,
    load_pr,
    save_pending_pr_request,
    set_agent_clarification,
    set_issue_status,
)
from coddy.services.store.schemas import PendingPRRequest


def test_clarification_poll_posts_and_marks_sent(tmp_path: Path) -> None:
    """When issue has waiting_user_reply and message, poll posts and marks
    clarification_sent."""
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
    """After posting, status is clarification_sent so poll does not process the
    issue again."""
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


def test_plan_post_poll_posts_plan_and_sets_waiting_confirmation(tmp_path: Path) -> None:
    """When issue has plan_ready and last comment, poll posts to GitHub and
    sets waiting_confirmation."""
    create_issue(tmp_path, 3, "owner/repo", "T", "D", "@u")
    add_comment(tmp_path, 3, "@bot", "## Plan\n\n1. Step one\n\n---\nReply yes to start.")
    set_issue_status(tmp_path, 3, "plan_ready")

    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = "token"
    config.github = MagicMock()
    config.github.api_url = "https://api.github.com"

    mock_adapter = MagicMock()
    with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
        run_plan_post_poll(config, tmp_path)

    mock_adapter.create_comment.assert_called_once()
    assert mock_adapter.create_comment.call_args[0][2] == "## Plan\n\n1. Step one\n\n---\nReply yes to start."
    issue = load_issue(tmp_path, 3)
    assert issue is not None
    assert issue.status == "waiting_confirmation"


def test_create_pr_poll_creates_pr_and_moves_to_open(tmp_path: Path) -> None:
    """When pending PR request exists, poll creates PR via API, saves to open/,
    deletes pending."""
    req = PendingPRRequest(
        issue_id=5,
        repo="owner/repo",
        title="Add feature",
        body="Body with Closes #5",
        head="5-add-feature",
        base="main",
        created_at="2024-01-01T00:00:00Z",
    )
    save_pending_pr_request(tmp_path, req)

    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = "token"
    config.github = MagicMock()
    config.github.api_url = "https://api.github.com"

    fake_pr = MagicMock()
    fake_pr.number = 42
    fake_pr.state = "open"
    mock_adapter = MagicMock()
    mock_adapter.create_pr.return_value = fake_pr

    with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
        run_create_pr_poll(config, tmp_path)

    mock_adapter.create_pr.assert_called_once()
    assert mock_adapter.create_pr.call_args[1]["title"] == "Add feature"
    assert mock_adapter.create_pr.call_args[1]["body"] == "Body with Closes #5"
    assert mock_adapter.create_pr.call_args[1]["head"] == "5-add-feature"
    assert mock_adapter.create_pr.call_args[1]["base"] == "main"
    mock_adapter.set_issue_labels.assert_called_once_with("owner/repo", 5, ["review"])

    pr = load_pr(tmp_path, 42)
    assert pr is not None
    assert pr.pr_id == 42
    assert pr.issue_id == 5
    assert pr.status == "open"
    assert not (tmp_path / ".coddy" / "pull_requests" / "pending" / "5.yaml").exists()
