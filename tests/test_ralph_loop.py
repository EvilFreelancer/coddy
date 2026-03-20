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
    """When generate_code returns PR body, worker writes pending PR request
    (observer creates PR)."""
    import yaml

    issue = _issue(number=1)
    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_issue.return_value = issue
    adapter.get_default_branch.return_value = "main"
    adapter.create_branch.side_effect = None
    adapter.set_issue_labels.side_effect = None

    agent = MagicMock()
    agent.evaluate_sufficiency.return_value = type("R", (), {"sufficient": True, "clarification": ""})()
    agent.generate_code.return_value = "PR body with Closes #1"
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
    adapter.create_pr.assert_not_called()
    pending_path = tmp_path / ".coddy" / "pull_requests" / "pending" / "1.yaml"
    assert pending_path.exists()
    data = yaml.safe_load(pending_path.read_text())
    assert data["issue_id"] == 1
    assert data["repo"] == "owner/repo"
    assert data["body"] == "PR body with Closes #1"
    assert data["head"] == "1-add-login"
    assert data["base"] == "main"


def test_ralph_loop_calls_agent_each_iteration_until_pr_body(tmp_path: Path) -> None:
    """When generate_code returns None then PR body, loop runs agent twice then
    writes pending PR request."""
    import yaml

    issue = _issue(number=1)
    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_issue.return_value = issue
    adapter.get_default_branch.return_value = "main"
    adapter.create_branch.side_effect = None
    adapter.set_issue_labels.side_effect = None

    agent = MagicMock()
    agent.evaluate_sufficiency.return_value = type("R", (), {"sufficient": True, "clarification": ""})()
    agent.generate_code.side_effect = [None, "PR body from second run"]
    with (
        patch("coddy.worker.ralph_loop.fetch_and_checkout_branch"),
        patch("coddy.worker.ralph_loop.checkout_branch"),
        patch("coddy.worker.ralph_loop.commit_all_and_push"),
    ):
        result = run_ralph_loop_for_issue(
            adapter,
            agent,
            issue,
            "owner/repo",
            tmp_path,
            default_branch="main",
            max_iterations=5,
        )
    assert result == "success"
    assert agent.generate_code.call_count == 2
    adapter.create_pr.assert_not_called()
    pending_path = tmp_path / ".coddy" / "pull_requests" / "pending" / "1.yaml"
    assert pending_path.exists()
    data = yaml.safe_load(pending_path.read_text())
    assert data["body"] == "PR body from second run"


def test_ralph_loop_returns_failed_after_max_iterations_without_pr(tmp_path: Path) -> None:
    """When generate_code always returns None and no report file, loop runs
    max_iterations then returns failed."""
    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_default_branch.return_value = "main"
    adapter.create_branch.side_effect = None
    adapter.set_issue_labels.side_effect = None

    agent = MagicMock()
    agent.evaluate_sufficiency.return_value = type("R", (), {"sufficient": True, "clarification": ""})()
    agent.generate_code.return_value = None

    issue = _issue(number=1)
    with (
        patch("coddy.worker.ralph_loop.fetch_and_checkout_branch"),
        patch("coddy.worker.ralph_loop.checkout_branch"),
    ):
        result = run_ralph_loop_for_issue(
            adapter,
            agent,
            issue,
            "owner/repo",
            tmp_path,
            default_branch="main",
            max_iterations=3,
        )
    assert result == "failed"
    assert agent.generate_code.call_count == 3
