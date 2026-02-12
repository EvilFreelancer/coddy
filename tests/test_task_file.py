"""Tests for task and report file paths, task log path, and agent
clarification."""

from datetime import datetime
from pathlib import Path

from coddy.models import ReviewComment
from coddy.services.task_file import (
    read_agent_clarification,
    read_review_reply,
    report_file_path,
    review_reply_file_path,
    review_task_file_path,
    task_file_path,
    task_log_path,
    write_review_task_file,
)


def test_task_file_path() -> None:
    """task_file_path returns .coddy/task-{n}.md under repo_dir."""
    assert task_file_path(Path("/repo"), 42) == Path("/repo/.coddy/task-42.md")


def test_report_file_path() -> None:
    """report_file_path returns .coddy/pr-{n}.md under repo_dir."""
    assert report_file_path(Path("/repo"), 42) == Path("/repo/.coddy/pr-42.md")


def test_task_log_path() -> None:
    """task_log_path returns .coddy/task-{n}.log under repo_dir."""
    assert task_log_path(Path("/repo"), 42) == Path("/repo/.coddy/task-42.log")


def test_read_agent_clarification_missing_file(tmp_path: Path) -> None:
    """read_agent_clarification returns None when task file does not exist."""
    assert read_agent_clarification(tmp_path, 99) is None


def test_read_agent_clarification_no_section(tmp_path: Path) -> None:
    """read_agent_clarification returns None when section is absent."""
    path = tmp_path / ".coddy" / "task-1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Task\n\n## Description\n\nDo something.", encoding="utf-8")
    assert read_agent_clarification(tmp_path, 1) is None


def test_read_agent_clarification_present(tmp_path: Path) -> None:
    """read_agent_clarification returns content of Agent clarification request
    section."""
    path = tmp_path / ".coddy" / "task-2.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Task\n\n## Description\n\nVague.\n\n"
        "## Agent clarification request\n\n"
        "Please specify the acceptance criteria and target module.",
        encoding="utf-8",
    )
    assert read_agent_clarification(tmp_path, 2) == ("Please specify the acceptance criteria and target module.")


def test_read_agent_clarification_stops_at_next_heading(tmp_path: Path) -> None:
    """read_agent_clarification returns only content until next ##."""
    path = tmp_path / ".coddy" / "task-3.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Task\n\n## Agent clarification request\n\nNeed more info.\n\n## Other\n\nIgnore.",
        encoding="utf-8",
    )
    assert read_agent_clarification(tmp_path, 3) == "Need more info."


def test_review_task_file_path() -> None:
    """review_task_file_path returns .coddy/review-{pr}.md."""
    assert review_task_file_path(Path("/repo"), 5) == Path("/repo/.coddy/review-5.md")


def test_review_reply_file_path() -> None:
    """review_reply_file_path returns .coddy/review-
    reply-{pr}-{comment_id}.md."""
    assert review_reply_file_path(Path("/repo"), 5, 100) == Path("/repo/.coddy/review-reply-5-100.md")


def test_write_review_task_file(tmp_path: Path) -> None:
    """write_review_task_file creates file with todo list and current item."""
    dt = datetime(2024, 1, 15, 10, 0, 0)
    comments = [
        ReviewComment(1, "Fix typo", "user", "a.py", 10, "RIGHT", dt, None, None),
        ReviewComment(2, "Use constant", "user", "b.py", 20, "RIGHT", dt, None, None),
    ]
    out = write_review_task_file(3, 1, comments, 1, tmp_path)
    assert out == tmp_path / ".coddy" / "review-3.md"
    text = out.read_text(encoding="utf-8")
    assert "PR #3" in text
    assert "Issue #1" in text
    assert "Current item: 1 of 2" in text
    assert "a.py" in text
    assert "Fix typo" in text
    assert "review-reply-3-1" in text


def test_read_review_reply_missing(tmp_path: Path) -> None:
    """read_review_reply returns None when file does not exist."""
    assert read_review_reply(tmp_path, 3, 100) is None


def test_read_review_reply_present(tmp_path: Path) -> None:
    """read_review_reply returns file content when present."""
    path = tmp_path / ".coddy" / "review-reply-3-100.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Done, fixed.", encoding="utf-8")
    assert read_review_reply(tmp_path, 3, 100) == "Done, fixed."
