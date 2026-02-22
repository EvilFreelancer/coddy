"""Tests for ralph_loop service."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coddy.observer.models import Issue
from coddy.worker.ralph_loop import run_ralph_loop_for_issue


def _issue(number: int = 1, body: str = "Enough body for sufficiency.") -> Issue:
    from datetime import UTC, datetime

    return Issue(
        number=number,
        title="Add login",
        body=body,
        author="user",
        labels=[],
        state="open",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_ralph_loop_returns_clarification_when_insufficient(tmp_path: Path) -> None:
    """When agent says data insufficient, we write clarification to issue YAML
    (observer posts)."""
    from coddy.services.store import create_issue, load_issue

    create_issue(
        tmp_path,
        issue_id=1,
        repo="owner/repo",
        title="Add login",
        description="Short",
        author="user",
    )

    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_default_branch.return_value = "main"

    agent = MagicMock()
    agent.evaluate_sufficiency.return_value = type(
        "R",
        (),
        {"sufficient": False, "clarification": "Please add acceptance criteria."},
    )()

    issue = _issue(number=1, body="Short")
    result = run_ralph_loop_for_issue(
        adapter,
        agent,
        issue,
        "owner/repo",
        tmp_path,
        default_branch="main",
        max_iterations=2,
    )
    assert result == "clarification"
    adapter.create_comment.assert_not_called()
    agent.generate_code.assert_not_called()

    stored = load_issue(tmp_path, 1)
    assert stored is not None
    assert stored.status == "waiting_user_reply"
    assert len(stored.comments) == 1
    assert stored.comments[0].content == "Please add acceptance criteria."


def test_ralph_loop_returns_success_when_pr_report_written(tmp_path: Path) -> None:
    """When generate_code returns PR body, we create PR and return success."""
    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_default_branch.return_value = "main"
    adapter.create_branch.side_effect = None
    adapter.create_pr.side_effect = None
    adapter.set_issue_labels.side_effect = None

    agent = MagicMock()
    agent.evaluate_sufficiency.return_value = type("R", (), {"sufficient": True, "clarification": ""})()
    agent.generate_code.return_value = "PR body with Closes #1"

    issue = _issue(number=1)
    with (
        patch(
            "coddy.worker.ralph_loop.fetch_and_checkout_branch",
        ),
        patch(
            "coddy.worker.ralph_loop.checkout_branch",
        ),
        patch(
            "coddy.worker.ralph_loop.commit_all_and_push",
        ),
    ):
        result = run_ralph_loop_for_issue(
            adapter,
            agent,
            issue,
            "owner/repo",
            tmp_path,
            default_branch="main",
            max_iterations=2,
        )
    assert result == "success"
    adapter.create_pr.assert_called_once()
    assert adapter.create_pr.call_args[1]["body"] == "PR body with Closes #1"
