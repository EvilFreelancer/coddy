"""Tests for task and report file paths, task log path, and agent clarification."""

from pathlib import Path

from coddy.services.task_file import (
    read_agent_clarification,
    report_file_path,
    task_file_path,
    task_log_path,
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
    """read_agent_clarification returns content of Agent clarification request section."""
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
