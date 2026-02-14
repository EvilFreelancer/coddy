"""File-based task queue in .coddy/queue/ as markdown files.

Each task is a .md file that is human-readable and can be parsed back to a dict.
Format: .coddy/queue/pending/42.md with key-value lines.
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
    """Take the next pending task (smallest issue number). Does not remove it."""
    pending = list_pending(repo_dir)
    if not pending:
        return None
    pending.sort(key=lambda t: t["issue_number"])
    return pending[0]


def mark_done(repo_dir: Path, issue_number: int) -> None:
    """Move task from pending to done (same .md format)."""
    _move_task_md(repo_dir, issue_number, _done_dir(repo_dir))


def mark_failed(repo_dir: Path, issue_number: int) -> None:
    """Move task from pending to failed."""
    _move_task_md(repo_dir, issue_number, _failed_dir(repo_dir))


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
