"""
Tests for git_runner (branch name, fetch/checkout).
"""

from coddy.services.git_runner import branch_name_from_issue


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
