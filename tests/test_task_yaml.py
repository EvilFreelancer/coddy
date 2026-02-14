"""Tests for task and report YAML paths, task log path, and agent clarification."""

from datetime import datetime
from pathlib import Path

import yaml

from coddy.observer.models import ReviewComment
from coddy.worker.task_yaml import (
    read_agent_clarification,
    read_pr_report,
    read_review_reply,
    report_file_path,
    review_reply_file_path,
    review_task_file_path,
    task_file_path,
    task_log_path,
    write_review_task_file,
)


def test_task_file_path() -> None:
    """task_file_path returns .coddy/task-{n}.yaml under repo_dir."""
    assert task_file_path(Path("/repo"), 42) == Path("/repo/.coddy/task-42.yaml")


def test_report_file_path() -> None:
    """report_file_path returns .coddy/pr-{n}.yaml under repo_dir."""
    assert report_file_path(Path("/repo"), 42) == Path("/repo/.coddy/pr-42.yaml")


def test_task_log_path() -> None:
    """task_log_path returns .coddy/task-{n}.log under repo_dir."""
    assert task_log_path(Path("/repo"), 42) == Path("/repo/.coddy/task-42.log")


def test_read_agent_clarification_missing_file(tmp_path: Path) -> None:
    """read_agent_clarification returns None when task file does not exist."""
    assert read_agent_clarification(tmp_path, 99) is None


def test_read_agent_clarification_no_key(tmp_path: Path) -> None:
    """read_agent_clarification returns None when agent_clarification key is absent."""
    path = tmp_path / ".coddy" / "task-1.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"number": 1, "title": "Task", "body": "Do something."}), encoding="utf-8")
    assert read_agent_clarification(tmp_path, 1) is None


def test_read_agent_clarification_present(tmp_path: Path) -> None:
    """read_agent_clarification returns content of agent_clarification key."""
    path = tmp_path / ".coddy" / "task-2.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "number": 2,
        "title": "Vague",
        "body": "Vague.",
        "agent_clarification": "Please specify the acceptance criteria and target module.",
    }
    path.write_text(yaml.dump(data), encoding="utf-8")
    assert read_agent_clarification(tmp_path, 2) == (
        "Please specify the acceptance criteria and target module."
    )


def test_read_pr_report_missing(tmp_path: Path) -> None:
    """read_pr_report returns empty string when file does not exist."""
    assert read_pr_report(tmp_path, 99) == ""


def test_read_pr_report_present(tmp_path: Path) -> None:
    """read_pr_report returns body from pr YAML."""
    path = tmp_path / ".coddy" / "pr-3.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"body": "Done. Closes #3."}), encoding="utf-8")
    assert read_pr_report(tmp_path, 3) == "Done. Closes #3."


def test_review_task_file_path() -> None:
    """review_task_file_path returns .coddy/review-{pr}.yaml."""
    assert review_task_file_path(Path("/repo"), 5) == Path("/repo/.coddy/review-5.yaml")


def test_review_reply_file_path() -> None:
    """review_reply_file_path returns .coddy/review-reply-{pr}-{comment_id}.yaml."""
    assert review_reply_file_path(Path("/repo"), 5, 100) == Path(
        "/repo/.coddy/review-reply-5-100.yaml"
    )


def test_write_review_task_file(tmp_path: Path) -> None:
    """write_review_task_file creates YAML with todo list and current item."""
    dt = datetime(2024, 1, 15, 10, 0, 0)
    comments = [
        ReviewComment(
            id=1,
            body="Fix typo",
            author="user",
            path="a.py",
            line=10,
            side="RIGHT",
            created_at=dt,
            updated_at=None,
            in_reply_to_id=None,
        ),
        ReviewComment(
            id=2,
            body="Use constant",
            author="user",
            path="b.py",
            line=20,
            side="RIGHT",
            created_at=dt,
            updated_at=None,
            in_reply_to_id=None,
        ),
    ]
    out = write_review_task_file(3, 1, comments, 1, tmp_path)
    assert out == tmp_path / ".coddy" / "review-3.yaml"
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["pr_number"] == 3
    assert data["issue_number"] == 1
    assert data["current_index"] == 1
    assert data["total"] == 2
    assert "a.py" in str(data["current"])
    assert "Fix typo" in str(data["current"])
    assert "review-reply-3-1" in str(data["reply_path"])


def test_read_review_reply_missing(tmp_path: Path) -> None:
    """read_review_reply returns None when file does not exist."""
    assert read_review_reply(tmp_path, 3, 100) is None


def test_read_review_reply_present_yaml(tmp_path: Path) -> None:
    """read_review_reply returns body from reply YAML."""
    path = tmp_path / ".coddy" / "review-reply-3-100.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"body": "Done, fixed."}), encoding="utf-8")
    assert read_review_reply(tmp_path, 3, 100) == "Done, fixed."


def test_read_review_reply_plain_text(tmp_path: Path) -> None:
    """read_review_reply returns content when file is plain text (fallback)."""
    path = tmp_path / ".coddy" / "review-reply-3-101.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Plain reply text.", encoding="utf-8")
    assert read_review_reply(tmp_path, 3, 101) == "Plain reply text."
