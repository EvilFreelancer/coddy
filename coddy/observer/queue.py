"""Task queue: tasks are taken from .coddy/issues/ (status=queued).

Legacy: .coddy/queue/ (pending/done/failed) is no longer used. Worker and planner
use only .coddy/issues/ and .coddy/prs/ YAML. take_next/mark_done/mark_failed
operate on issue status; enqueue/list_pending/_move_task_md remain for backward
compatibility but are not used by the main flow.
"""

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

QUEUE_DIR = ".coddy/queue"
PENDING = "pending"
DONE = "done"
FAILED = "failed"

LOG = logging.getLogger("coddy.observer.queue")


def _queue_base(repo_dir: Path) -> Path:
    return Path(repo_dir) / QUEUE_DIR


def _pending_dir(repo_dir: Path) -> Path:
    return _queue_base(repo_dir) / PENDING


def _done_dir(repo_dir: Path) -> Path:
    return _queue_base(repo_dir) / DONE


def _failed_dir(repo_dir: Path) -> Path:
    return _queue_base(repo_dir) / FAILED


def _task_to_markdown(repo: str, issue_number: int, title: str, enqueued_at: str) -> str:
    """Single task as readable markdown (easy to restore to dict)."""
    return f"""# Issue {issue_number}

repo: {repo}
issue_number: {issue_number}
title: {title}
enqueued_at: {enqueued_at}
"""


def _parse_task_md(content: str, issue_number: int) -> dict[str, Any] | None:
    """Parse markdown task file into dict. Returns None if invalid."""
    data = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-z_]+):\s*(.+)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if key == "issue_number":
                try:
                    data[key] = int(value)
                except ValueError:
                    return None
            else:
                data[key] = value
    if "repo" in data and "issue_number" in data:
        data.setdefault("issue_number", issue_number)
        return data
    return None


def enqueue(
    repo_dir: Path,
    repo: str,
    issue_number: int,
    title: str = "",
    payload: dict[str, Any] | None = None,
) -> Path:
    """Enqueue a task as .coddy/queue/pending/{issue_number}.md.

    Markdown is human-readable and parseable back to a list of tasks.
    """
    base = _pending_dir(repo_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{issue_number}.md"
    enqueued_at = datetime.now(UTC).isoformat()
    body = _task_to_markdown(repo, issue_number, title or f"Issue {issue_number}", enqueued_at)
    path.write_text(body, encoding="utf-8")
    LOG.info("Enqueued task: %s", path.name)
    return path


def list_pending(repo_dir: Path) -> list[dict[str, Any]]:
    """List all pending tasks by reading .md files and parsing them."""
    base = _pending_dir(repo_dir)
    if not base.is_dir():
        return []
    tasks = []
    for f in sorted(base.glob("*.md")):
        try:
            stem = f.stem
            if not stem.isdigit():
                continue
            issue_number = int(stem)
            content = f.read_text(encoding="utf-8")
            data = _parse_task_md(content, issue_number)
            if data:
                tasks.append(data)
        except (OSError, ValueError) as e:
            LOG.warning("Skip invalid queue file %s: %s", f, e)
    return tasks


def take_next(repo_dir: Path) -> dict[str, Any] | None:
    """Return next task from .coddy/issues/ (status=queued), smallest issue number. Does not remove it."""
    from coddy.observer.issues.issue_store import list_queued

    queued = list_queued(repo_dir)
    if not queued:
        return None
    queued.sort(key=lambda t: t[0])
    issue_number, issue_file = queued[0]
    return {
        "issue_number": issue_number,
        "repo": issue_file.repo or "",
        "title": issue_file.title or "",
    }


def mark_done(repo_dir: Path, issue_number: int) -> None:
    """Set issue status to done in .coddy/issues/."""
    from coddy.observer.issues.issue_store import set_status

    set_status(repo_dir, issue_number, "done")


def mark_failed(repo_dir: Path, issue_number: int) -> None:
    """Set issue status to failed in .coddy/issues/."""
    from coddy.observer.issues.issue_store import set_status

    set_status(repo_dir, issue_number, "failed")


def _move_task_md(repo_dir: Path, issue_number: int, target_dir: Path) -> None:
    pending = _pending_dir(repo_dir)
    path = pending / f"{issue_number}.md"
    if not path.is_file():
        LOG.warning("No pending task %s to move", path)
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.exists():
        target.unlink()
    path.rename(target)
    LOG.info("Moved task %s to %s", path.name, target_dir.name)
