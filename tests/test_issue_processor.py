"""Tests for issue processor (process_one_issue)."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from coddy.agents.base import SufficiencyResult
from coddy.models import Issue
from coddy.services.issue_processor import process_one_issue


def test_process_one_issue_sets_review_label_after_pr_created(tmp_path: Path) -> None:
    """When agent completes and returns PR body, issue gets label 'review'
    after create_pr."""
    dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    issue = Issue(6, "Add review label", "Body", "user", [], "open", dt, dt)

    adapter = Mock()
    adapter.get_issue.return_value = issue
    adapter.get_issue_comments.return_value = []
    adapter.get_default_branch.return_value = "main"
    adapter.create_pr.return_value = None

    agent = Mock()
    agent.evaluate_sufficiency.return_value = SufficiencyResult(sufficient=True)
    agent.generate_code.return_value = "PR description body"

    with (
        patch(
            "coddy.services.issue_processor.fetch_and_checkout_branch",
        ),
        patch(
            "coddy.services.issue_processor.commit_all_and_push",
        ),
    ):
        process_one_issue(
            adapter,
            agent,
            issue,
            "owner/repo",
            repo_dir=tmp_path,
            bot_name="Bot",
            bot_email="bot@example.com",
            default_branch="main",
        )

    adapter.create_pr.assert_called_once()
    set_labels_calls = [c for c in adapter.set_issue_labels.call_args_list]
    review_calls = [c for c in set_labels_calls if c[0][2] == ["review"]]
    assert len(review_calls) == 1, "set_issue_labels should be called with ['review'] after PR creation"
    assert review_calls[0][0][0] == "owner/repo"
    assert review_calls[0][0][1] == 6
    assert review_calls[0][0][2] == ["review"]
