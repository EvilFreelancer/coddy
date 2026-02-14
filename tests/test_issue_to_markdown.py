"""Tests for YAML issue -> markdown converter (for agent)."""

from coddy.observer.issues import IssueComment, IssueFile
from coddy.utils.issue_to_markdown import issue_to_markdown


def test_issue_to_markdown_title_and_description() -> None:
    """Converter outputs title and description sections."""
    issue = IssueFile(
        author="@user",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        title="Add feature",
        description="Please add a button.",
    )
    md = issue_to_markdown(issue, issue_number=42)
    assert "# Issue 42" in md
    assert "## Title" in md
    assert "Add feature" in md
    assert "## Description" in md
    assert "Please add a button." in md


def test_issue_to_markdown_with_comments() -> None:
    """Converter includes comments section with name, content, created_at, updated_at."""
    issue = IssueFile(
        author="@user",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        title="T",
        description="D",
        comments=[
            IssueComment(name="@user", content="T\n\nD", created_at=1000, updated_at=1000),
            IssueComment(name="@bot", content="Here is the plan.", created_at=2000, updated_at=2000),
        ],
    )
    md = issue_to_markdown(issue, issue_number=7)
    assert "## Comments" in md
    assert "### @user" in md
    assert "T\n\nD" in md
    assert "### @bot" in md
    assert "Here is the plan." in md
    assert "created_at: 1000" in md
    assert "created_at: 2000" in md


def test_issue_to_markdown_without_issue_number() -> None:
    """Converter works without issue_number (no # Issue N line)."""
    issue = IssueFile(
        author="@u",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        title="T",
    )
    md = issue_to_markdown(issue)
    assert "# Issue" not in md or "## Title" in md
    assert "## Title" in md
    assert "T" in md


def test_issue_to_markdown_empty_description() -> None:
    """Empty description renders as (no description)."""
    issue = IssueFile(
        author="@u",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        title="Only title",
        description="",
    )
    md = issue_to_markdown(issue)
    assert "(no description)" in md


def test_issue_to_markdown_no_comments_section_when_empty() -> None:
    """When comments is empty, Comments section is not added with empty
    content."""
    issue = IssueFile(
        author="@u",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        title="T",
        description="D",
        comments=[],
    )
    md = issue_to_markdown(issue)
    assert "## Comments" not in md
