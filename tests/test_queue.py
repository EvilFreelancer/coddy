"""Tests for file-based task queue."""

from pathlib import Path

from coddy.queue import enqueue, list_pending, mark_done, mark_failed, take_next


def test_enqueue_and_list_pending(tmp_path: Path) -> None:
    """Enqueue adds a task file; list_pending returns it."""
    enqueue(tmp_path, "owner/repo", 42)
    tasks = list_pending(tmp_path)
    assert len(tasks) == 1
    assert tasks[0]["repo"] == "owner/repo"
    assert tasks[0]["issue_number"] == 42


def test_take_next_returns_smallest_issue(tmp_path: Path) -> None:
    """take_next returns task with smallest issue_number."""
    enqueue(tmp_path, "owner/repo", 10)
    enqueue(tmp_path, "owner/repo", 5)
    task = take_next(tmp_path)
    assert task is not None
    assert task["issue_number"] == 5


def test_mark_done_moves_to_done_dir(tmp_path: Path) -> None:
    """mark_done moves task file from pending to done."""
    enqueue(tmp_path, "owner/repo", 1, title="Task one")
    assert (tmp_path / ".coddy" / "queue" / "pending" / "1.md").is_file()
    mark_done(tmp_path, 1)
    assert not (tmp_path / ".coddy" / "queue" / "pending" / "1.md").is_file()
    assert (tmp_path / ".coddy" / "queue" / "done" / "1.md").is_file()


def test_mark_failed_moves_to_failed_dir(tmp_path: Path) -> None:
    """mark_failed moves task file from pending to failed."""
    enqueue(tmp_path, "owner/repo", 2)
    mark_failed(tmp_path, 2)
    assert not (tmp_path / ".coddy" / "queue" / "pending" / "2.md").is_file()
    assert (tmp_path / ".coddy" / "queue" / "failed" / "2.md").is_file()


def test_list_pending_empty_when_no_dir(tmp_path: Path) -> None:
    """list_pending returns [] when queue dir does not exist."""
    assert list_pending(tmp_path) == []


def test_take_next_returns_none_when_empty(tmp_path: Path) -> None:
    """take_next returns None when no pending tasks."""
    assert take_next(tmp_path) is None
