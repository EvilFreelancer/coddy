"""Tests for task queue (take_next from .coddy/issues/ queued;
mark_done/mark_failed set issue status)."""

from pathlib import Path

from coddy.observer.issues import create_issue, load_issue, set_status
from coddy.observer.queue import enqueue, list_pending, mark_done, mark_failed, take_next


def test_enqueue_and_list_pending(tmp_path: Path) -> None:
    """Legacy enqueue adds a task file in .coddy/queue/pending/; list_pending
    returns it."""
    enqueue(tmp_path, "owner/repo", 42)
    tasks = list_pending(tmp_path)
    assert len(tasks) == 1
    assert tasks[0]["repo"] == "owner/repo"
    assert tasks[0]["issue_number"] == 42


def test_take_next_returns_smallest_issue(tmp_path: Path) -> None:
    """take_next returns task from .coddy/issues/ (status=queued) with smallest
    issue_number."""
    create_issue(tmp_path, 10, "owner/repo", "Ten", "", "u")
    create_issue(tmp_path, 5, "owner/repo", "Five", "", "u")
    set_status(tmp_path, 10, "queued")
    set_status(tmp_path, 5, "queued")
    task = take_next(tmp_path)
    assert task is not None
    assert task["issue_number"] == 5
    assert task["repo"] == "owner/repo"


def test_mark_done_sets_issue_status_done(tmp_path: Path) -> None:
    """mark_done sets issue status to done in .coddy/issues/."""
    create_issue(tmp_path, 1, "owner/repo", "Task one", "", "u")
    set_status(tmp_path, 1, "queued")
    mark_done(tmp_path, 1)
    issue = load_issue(tmp_path, 1)
    assert issue is not None
    assert issue.status == "done"


def test_mark_failed_sets_issue_status_failed(tmp_path: Path) -> None:
    """mark_failed sets issue status to failed in .coddy/issues/."""
    create_issue(tmp_path, 2, "owner/repo", "Task two", "", "u")
    set_status(tmp_path, 2, "queued")
    mark_failed(tmp_path, 2)
    issue = load_issue(tmp_path, 2)
    assert issue is not None
    assert issue.status == "failed"


def test_list_pending_empty_when_no_dir(tmp_path: Path) -> None:
    """list_pending returns [] when queue dir does not exist."""
    assert list_pending(tmp_path) == []


def test_take_next_returns_none_when_empty(tmp_path: Path) -> None:
    """take_next returns None when no pending tasks."""
    assert take_next(tmp_path) is None
