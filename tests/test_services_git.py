"""Tests for coddy.services.git (branches, push_pull)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from coddy.services.git import (
    GitRunnerError,
    branch_name_from_issue,
    checkout_branch,
    is_valid_branch_name,
    run_git_pull,
    sanitize_branch_name,
)


class TestBranches:
    """coddy.services.git.branches: branch names, sanitize, validate, checkout."""

    def test_branch_name_from_issue(self) -> None:
        """Branch name is number plus slugified title."""
        assert branch_name_from_issue(1, "Implement get_issue_assignees") == "1-implement-get-issue-assignees"
        assert branch_name_from_issue(42, "Add user login") == "42-add-user-login"
        assert branch_name_from_issue(1, "Fix bug") == "1-fix-bug"

    def test_branch_name_from_issue_long_title(self) -> None:
        """Long title is truncated to max length in slug (100 chars)."""
        long_title = "a" * 150
        name = branch_name_from_issue(1, long_title)
        assert name.startswith("1-")
        assert len(name) <= 104

    def test_branch_name_from_issue_produces_valid_branch_name(self) -> None:
        """Branch name built from issue is valid (sanitization applied correctly)."""
        name = branch_name_from_issue(42, "Add user login form with validation???")
        assert is_valid_branch_name(name), f"branch_name_from_issue produced invalid name: {name!r}"
        name2 = branch_name_from_issue(1, "Fix: bug ~ ^ : ? * [ ]")
        assert is_valid_branch_name(name2), f"branch_name_from_issue produced invalid name: {name2!r}"

    def test_sanitize_branch_name_replaces_spaces_with_dashes(self) -> None:
        """Spaces are replaced with single dashes."""
        assert sanitize_branch_name("add user login") == "add-user-login"
        assert sanitize_branch_name("  a  b  ") == "a-b"

    def test_sanitize_branch_name_removes_invalid_characters(self) -> None:
        """Invalid characters (e.g. special chars) are removed."""
        assert sanitize_branch_name("add~feature") == "addfeature"
        assert sanitize_branch_name("fix: bug") == "fix-bug"
        assert sanitize_branch_name("test?me") == "testme"
        assert sanitize_branch_name("foo*bar") == "foobar"
        assert sanitize_branch_name("a.b.c") == "a-b-c"

    def test_sanitize_branch_name_lowercase(self) -> None:
        """Output is lowercase."""
        assert sanitize_branch_name("Add Feature") == "add-feature"

    def test_sanitize_branch_name_strips_and_collapses_dashes(self) -> None:
        """Leading/trailing dashes and repeated dashes are normalized."""
        assert sanitize_branch_name("--hello--world--") == "hello-world"
        assert sanitize_branch_name("  spaces  ") == "spaces"

    def test_sanitize_branch_name_truncates_to_max_length(self) -> None:
        """Long result is truncated to max_length, default 100."""
        long_input = "a" * 150
        result = sanitize_branch_name(long_input, max_length=100)
        assert len(result) <= 100
        result_default = sanitize_branch_name(long_input)
        assert len(result_default) <= 100

    def test_sanitize_branch_name_truncate_does_not_end_with_dash(self) -> None:
        """When truncating, result does not end with a trailing dash."""
        long_input = "a-b-" * 30
        result = sanitize_branch_name(long_input, max_length=20)
        assert len(result) <= 20
        assert not result.endswith("-")

    def test_sanitize_branch_name_empty_after_sanitize(self) -> None:
        """If only invalid chars, return empty string."""
        assert sanitize_branch_name("???***") == ""
        assert sanitize_branch_name("   ") == ""

    def test_is_valid_branch_name_accepts_valid_names(self) -> None:
        """Valid branch names (digits, lowercase letters, dashes) are accepted."""
        assert is_valid_branch_name("42-add-feature") is True
        assert is_valid_branch_name("1-fix-bug") is True
        assert is_valid_branch_name("123") is True
        assert is_valid_branch_name("a-b-c") is True

    def test_is_valid_branch_name_rejects_invalid(self) -> None:
        """Invalid branch names are rejected (spaces, special chars, double dot)."""
        assert is_valid_branch_name("42 add feature") is False
        assert is_valid_branch_name("42..add") is False
        assert is_valid_branch_name("42~feature") is False
        assert is_valid_branch_name("42:feature") is False
        assert is_valid_branch_name("42?feature") is False
        assert is_valid_branch_name("") is False
        assert is_valid_branch_name("-leading") is False
        assert is_valid_branch_name("trailing-") is False

    def test_sanitize_result_is_valid(self) -> None:
        """Result of sanitize_branch_name is always valid when non-empty."""
        inputs = ["Add user login", "Fix: bug???", "a" * 80, "  x  y  z  "]
        for text in inputs:
            result = sanitize_branch_name(text, max_length=100)
            if result:
                assert is_valid_branch_name(result), f"sanitize({text!r}) produced invalid name {result!r}"

    def test_checkout_branch_success(self) -> None:
        """checkout_branch runs git checkout <branch> in repo_dir."""
        with patch("coddy.services.git.branches._run_git") as mock_run:
            checkout_branch("main", repo_dir=Path("/tmp/repo"), log=None)
        mock_run.assert_called_once_with(["checkout", "main"], cwd=Path("/tmp/repo"), log=None)

    def test_checkout_branch_fetches_if_not_exists_locally(self) -> None:
        """checkout_branch fetches branch if checkout fails initially."""
        with patch("coddy.services.git.branches._run_git") as mock_run:
            mock_run.side_effect = [GitRunnerError("branch not found"), None, None]
            checkout_branch("main", repo_dir=Path("/tmp/repo"), log=None)
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[0][0][0] == ["checkout", "main"]
        assert mock_run.call_args_list[1][0][0] == ["fetch", "origin", "main"]
        assert mock_run.call_args_list[2][0][0] == ["checkout", "main"]

    def test_checkout_branch_uses_cwd_when_no_repo_dir(self) -> None:
        """checkout_branch uses Path.cwd() when repo_dir is None."""
        with patch("coddy.services.git.branches._run_git") as mock_run:
            checkout_branch("main", log=None)
        assert mock_run.call_count == 1
        assert mock_run.call_args[0][0] == ["checkout", "main"]
        assert mock_run.call_args[1]["cwd"] == Path.cwd()


class TestPushPull:
    """coddy.services.git.push_pull: run_git_pull."""

    def test_run_git_pull_success(self) -> None:
        """run_git_pull runs git pull origin <branch> in repo_dir."""
        with patch("coddy.services.git.push_pull._run_git") as mock_run:
            run_git_pull("main", repo_dir=Path("/tmp/repo"), log=None)
        mock_run.assert_called_once_with(["pull", "origin", "main"], cwd=Path("/tmp/repo"), log=None)

    def test_run_git_pull_uses_cwd_when_no_repo_dir(self) -> None:
        """run_git_pull uses Path.cwd() when repo_dir is None."""
        with patch("coddy.services.git.push_pull._run_git") as mock_run:
            run_git_pull("main", log=None)
        assert mock_run.call_count == 1
        assert mock_run.call_args[0][0] == ["pull", "origin", "main"]
        assert mock_run.call_args[1]["cwd"] == Path.cwd()

    def test_run_git_pull_raises_on_failure(self) -> None:
        """run_git_pull propagates GitRunnerError from _run_git."""
        with patch("coddy.services.git.push_pull._run_git", side_effect=GitRunnerError("pull failed")):
            with pytest.raises(GitRunnerError, match="pull failed"):
                run_git_pull("main", repo_dir=Path("/tmp/repo"))
