"""Tests for issue store (.coddy/issues/*.yaml)."""

from pathlib import Path

import pytest

from coddy.issue_file import IssueFile, IssueMessage
from coddy.issue_store import (
    add_message,
    create_issue,
    load_issue,
    list_issues_by_status,
    list_pending_plan,
    list_queued,
    save_issue,
    set_status,
)


def test_create_issue_writes_yaml(tmp_path: Path) -> None:
    """create_issue writes .coddy/issues/{n}.yaml with status pending_plan."""
    create_issue(
        tmp_path,
        issue_number=7,
        repo="owner/repo",
        title="Add login",
        description="Add a login form.",
        author="@user",
    )
    path = tmp_path / ".coddy" / "issues" / "7.yaml"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "pending_plan" in content
    assert "Add login" in content
    assert "Add a login form" in content
    assert "owner/repo" in content
    assert "assigned_at" in content


def test_load_issue_returns_issue_file(tmp_path: Path) -> None:
    """load_issue parses YAML into IssueFile."""
    create_issue(
        tmp_path,
        issue_number=8,
        repo="o/r",
        title="T",
        description="D",
        author="@u",
    )
    issue = load_issue(tmp_path, 8)
    assert issue is not None
    assert issue.status == "pending_plan"
    assert issue.title == "T"
    assert issue.repo == "o/r"
    assert len(issue.messages) == 1
    assert "T" in issue.messages[0].content and "D" in issue.messages[0].content


def test_load_issue_missing_returns_none(tmp_path: Path) -> None:
    """load_issue returns None when file does not exist."""
    assert load_issue(tmp_path, 999) is None


def test_add_message_appends_and_updates(tmp_path: Path) -> None:
    """add_message appends to messages and updates updated_at."""
    create_issue(tmp_path, 9, "o/r", "T", "D", "@u")
    add_message(tmp_path, 9, "@bot", "Here is the plan.", 2000)
    issue = load_issue(tmp_path, 9)
    assert issue is not None
    assert len(issue.messages) == 2
    assert issue.messages[1].name == "@bot"
    assert issue.messages[1].content == "Here is the plan."
    assert issue.messages[1].timestamp == 2000


def test_set_status_updates_file(tmp_path: Path) -> None:
    """set_status changes status in file."""
    create_issue(tmp_path, 10, "o/r", "T", "D", "@u")
    set_status(tmp_path, 10, "waiting_confirmation")
    issue = load_issue(tmp_path, 10)
    assert issue is not None
    assert issue.status == "waiting_confirmation"

    set_status(tmp_path, 10, "queued")
    issue2 = load_issue(tmp_path, 10)
    assert issue2 is not None
    assert issue2.status == "queued"


def test_list_issues_by_status(tmp_path: Path) -> None:
    """list_issues_by_status returns only issues with that status."""
    create_issue(tmp_path, 1, "o/r", "A", "", "@u")
    create_issue(tmp_path, 2, "o/r", "B", "", "@u")
    set_status(tmp_path, 2, "queued")
    pending = list_issues_by_status(tmp_path, "pending_plan")
    queued = list_issues_by_status(tmp_path, "queued")
    assert len(pending) == 1
    assert pending[0][0] == 1
    assert len(queued) == 1
    assert queued[0][0] == 2


def test_list_pending_plan_and_list_queued(tmp_path: Path) -> None:
    """list_pending_plan and list_queued filter by status."""
    create_issue(tmp_path, 3, "o/r", "X", "", "@u")
    create_issue(tmp_path, 4, "o/r", "Y", "", "@u")
    set_status(tmp_path, 4, "queued")
    assert len(list_pending_plan(tmp_path)) == 1
    assert list_pending_plan(tmp_path)[0][0] == 3
    assert len(list_queued(tmp_path)) == 1
    assert list_queued(tmp_path)[0][0] == 4


def test_save_issue_persists_manual_issue(tmp_path: Path) -> None:
    """save_issue writes an IssueFile built by hand."""
    issue = IssueFile(
        author="@x",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        status="queued",
        title="Manual",
        description="Desc",
        messages=[IssueMessage(name="@x", content="Manual\n\nDesc", timestamp=0)],
        repo="a/b",
        issue_number=99,
    )
    save_issue(tmp_path, 99, issue)
    loaded = load_issue(tmp_path, 99)
    assert loaded is not None
    assert loaded.title == "Manual"
    assert loaded.status == "queued"
