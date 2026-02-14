"""Tests for Pydantic issue file models."""

from coddy.observer.issues import IssueComment, IssueFile


def test_issue_comment_model() -> None:
    """IssueComment accepts name, content, created_at, updated_at."""
    msg = IssueComment(name="@user", content="Hello", created_at=1234567890, updated_at=1234567890)
    assert msg.name == "@user"
    assert msg.content == "Hello"
    assert msg.created_at == 1234567890
    assert msg.updated_at == 1234567890


def test_issue_file_minimal() -> None:
    """IssueFile with required fields only."""
    issue = IssueFile(
        author="@author",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    assert issue.status == "pending_plan"
    assert issue.title == ""
    assert issue.description == ""
    assert issue.comments == []
    assert issue.repo is None
    assert issue.issue_number is None
    assert issue.assigned_at is None


def test_issue_file_full() -> None:
    """IssueFile with comments and meta."""
    msg = IssueComment(name="@user", content="Title\n\nBody", created_at=1000, updated_at=1000)
    issue = IssueFile(
        author="@user",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-02T00:00:00Z",
        status="waiting_confirmation",
        title="Add feature",
        description="Please add X.",
        comments=[msg],
        repo="owner/repo",
        issue_number=42,
        assigned_at="2024-01-01T12:00:00Z",
    )
    assert issue.status == "waiting_confirmation"
    assert issue.title == "Add feature"
    assert len(issue.comments) == 1
    assert issue.comments[0].content == "Title\n\nBody"
    assert issue.repo == "owner/repo"
    assert issue.issue_number == 42


def test_issue_file_roundtrip_dict() -> None:
    """IssueFile can be built from model_dump()."""
    issue = IssueFile(
        author="@a",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        title="T",
        description="D",
        comments=[IssueComment(name="@a", content="T\n\nD", created_at=0, updated_at=0)],
    )
    data = issue.model_dump(mode="json")
    restored = IssueFile.model_validate(data)
    assert restored.title == issue.title
    assert restored.comments[0].content == issue.comments[0].content
