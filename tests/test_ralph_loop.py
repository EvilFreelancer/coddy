"""Tests for ralph_loop service."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def test_ralph_loop_calls_agent_each_iteration_until_pr_body(tmp_path: Path) -> None:
    """When generate_code returns None then PR body, loop runs agent twice then
    succeeds."""
    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_default_branch.return_value = "main"
    adapter.create_branch.side_effect = None
    adapter.create_pr.side_effect = None
    adapter.set_issue_labels.side_effect = None

    agent = MagicMock()
    agent.evaluate_sufficiency.return_value = type("R", (), {"sufficient": True, "clarification": ""})()
    agent.generate_code.side_effect = [None, "PR body from second run"]

    issue = _issue(number=1)
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
    adapter.create_pr.assert_called_once()
    assert adapter.create_pr.call_args[1]["body"] == "PR body from second run"


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


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("agent"), reason="Cursor CLI (agent) not installed")
def test_ralph_loop_runs_real_cursor_cli_integration(tmp_path: Path) -> None:
    """Integration: ralph loop starts real Cursor CLI; skip if agent not in PATH.

    Verifies the loop creates task YAML, invokes the agent, and writes .coddy/task-N.log.
    Does not require the agent to complete the task (may timeout).
    """
    from coddy.services.store import create_issue
    from coddy.worker.agents.cursor_cli_agent import CursorCLIAgent

    (tmp_path / ".coddy").mkdir(parents=True, exist_ok=True)
    create_issue(
        tmp_path,
        issue_id=1,
        repo="owner/repo",
        title="Add a comment to README",
        description="Add a single line to README with the word Hello.",
        author="user",
    )

    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_issue.return_value = _issue(
        number=1,
        body="Add a single line to README with the word Hello.",
    )
    adapter.get_default_branch.return_value = "main"
    adapter.create_branch.side_effect = None
    adapter.set_issue_labels.side_effect = None
    adapter.create_pr.side_effect = None

    agent = CursorCLIAgent(
        command="agent",
        timeout=30,
        working_directory=str(tmp_path),
    )

    def _checkout_noop(*args: object, **kwargs: object) -> None:
        pass

    with (
        patch("coddy.worker.ralph_loop.fetch_and_checkout_branch", side_effect=_checkout_noop),
        patch("coddy.worker.ralph_loop.checkout_branch", side_effect=_checkout_noop),
        patch("coddy.worker.ralph_loop.commit_all_and_push", side_effect=_checkout_noop),
    ):
        result = run_ralph_loop_for_issue(
            adapter,
            agent,
            adapter.get_issue.return_value,
            "owner/repo",
            tmp_path,
            default_branch="main",
            max_iterations=1,
        )

    log_path = tmp_path / ".coddy" / "task-1.log"
    assert log_path.is_file(), "Ralph loop must invoke Cursor CLI and write task-1.log"
    content = log_path.read_text(encoding="utf-8")
    assert "command=agent" in content or "Issue #1" in content
    assert "timeout=30" in content
    # Result may be success (agent wrote report), failed (timeout), or clarification
    assert result in ("success", "failed", "clarification")
