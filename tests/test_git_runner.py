"""Tests for git_runner (branch name, fetch/checkout, pull)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from coddy.services.git_runner import (
    GitRunnerError,
    branch_name_from_issue,
    run_git_pull,
)


def test_branch_name_from_issue() -> None:
    """Branch name is number plus slugified title."""
    assert branch_name_from_issue(1, "Implement get_issue_assignees") == "1-implement-get-issue-assignees"
    assert branch_name_from_issue(42, "Add user login") == "42-add-user-login"
    assert branch_name_from_issue(1, "Fix bug") == "1-fix-bug"


def test_branch_name_from_issue_long_title() -> None:
    """Long title is truncated to 40 chars in slug."""
    long_title = "a" * 50
    name = branch_name_from_issue(1, long_title)
    assert name.startswith("1-")
    assert len(name) <= 43


def test_run_git_pull_success() -> None:
    """run_git_pull runs git pull origin <branch> in repo_dir."""
    with patch("coddy.services.git_runner._run_git") as mock_run:
        run_git_pull("main", repo_dir=Path("/tmp/repo"), log=None)
    mock_run.assert_called_once_with(["pull", "origin", "main"], cwd=Path("/tmp/repo"), log=None)


def test_run_git_pull_uses_cwd_when_no_repo_dir() -> None:
    """run_git_pull uses Path.cwd() when repo_dir is None."""
    with patch("coddy.services.git_runner._run_git") as mock_run:
        run_git_pull("main", log=None)
    assert mock_run.call_count == 1
    assert mock_run.call_args[0][0] == ["pull", "origin", "main"]
    assert mock_run.call_args[1]["cwd"] == Path.cwd()


def test_run_git_pull_raises_on_failure() -> None:
    """run_git_pull propagates GitRunnerError from _run_git."""
    with patch("coddy.services.git_runner._run_git", side_effect=GitRunnerError("pull failed")):
        with pytest.raises(GitRunnerError, match="pull failed"):
            run_git_pull("main", repo_dir=Path("/tmp/repo"))
