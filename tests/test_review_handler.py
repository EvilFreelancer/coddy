"""Tests for review handler (process_pr_review)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from coddy.models import PR, ReviewComment
from coddy.services.review_handler import _issue_number_from_branch, process_pr_review


def test_issue_number_from_branch() -> None:
    """Extract issue number from branch name."""
    assert _issue_number_from_branch("42-add-feature") == 42
    assert _issue_number_from_branch("1-fix-bug") == 1
    assert _issue_number_from_branch("123-some-slug") == 123
    assert _issue_number_from_branch("main") is None
    assert _issue_number_from_branch("feature/foo") is None


def test_process_pr_review_empty_comments() -> None:
    """process_pr_review does nothing when review_comments is empty."""
    adapter = Mock()
    agent = Mock()
    process_pr_review(adapter, agent, "owner/repo", 3, [])
    adapter.get_pr.assert_not_called()
    agent.process_review_item.assert_not_called()


def test_process_pr_review_calls_agent_and_reply(tmp_path: Path) -> None:
    """process_pr_review gets PR, checks out branch, runs agent, replies."""
    dt = datetime(2024, 1, 15, 10, 0, 0)
    comments = [
        ReviewComment(100, "Use constant", "user", "src/a.py", 10, "RIGHT", dt, None, None),
    ]
    pr = PR(3, "Title", "Body", "42-feature", "main", "open", None)
    adapter = Mock()
    adapter.get_pr.return_value = pr
    adapter.reply_to_review_comment.return_value = None

    agent = Mock()
    agent.process_review_item.return_value = "Done, fixed."

    with (
        patch(
            "coddy.services.review_handler.fetch_and_checkout_branch",
        ),
        patch(
            "coddy.services.review_handler.commit_all_and_push",
        ),
    ):
        process_pr_review(
            adapter,
            agent,
            "owner/repo",
            3,
            comments,
            repo_dir=tmp_path,
            bot_name="Bot",
            bot_email="bot@example.com",
        )

    adapter.get_pr.assert_called_once_with("owner/repo", 3)
    agent.process_review_item.assert_called_once()
    call_args = agent.process_review_item.call_args[0]
    assert call_args[0] == 3  # pr_number
    assert call_args[1] == 42  # issue_number
    assert call_args[2] == comments
    assert call_args[3] == 1  # current_index
    assert call_args[4] == tmp_path  # repo_dir
    adapter.reply_to_review_comment.assert_called_once_with("owner/repo", 3, 100, "Done, fixed.")
