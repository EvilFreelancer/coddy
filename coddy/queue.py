"""File-based task queue for daemon/worker separation.

Daemon enqueues tasks (e.g. issue number) under .coddy/queue/pending/.
Worker dequeues by listing pending, processing, and moving to done/ or failed/.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

QUEUE_DIR = ".coddy/queue"
PENDING = "pending"
DONE = "done"
FAILED = "failed"

LOG = logging.getLogger("coddy.queue")


def _queue_base(repo_dir: Path) -> Path:
    return Path(repo_dir) / QUEUE_DIR


def _pending_dir(repo_dir: Path) -> Path:
    return _queue_base(repo_dir) / PENDING


def _done_dir(repo_dir: Path) -> Path:
    return _queue_base(repo_dir) / DONE


def _failed_dir(repo_dir: Path) -> Path:
    return _queue_base(repo_dir) / FAILED


def enqueue(
    repo_dir: Path,
    repo: str,
    issue_number: int,
    payload: Dict[str, Any] | None = None,
) -> Path:
    """Enqueue a task: work on issue for repo.

    Writes .coddy/queue/pending/{issue_number}.json.
    If the file already exists, overwrites (idempotent for same issue).

    Returns the path to the written file.
    """
    base = _pending_dir(repo_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{issue_number}.json"
    data = {"repo": repo, "issue_number": issue_number}
    if payload:
        data["payload"] = payload
    path.write_text(json.dumps(data, indent=0), encoding="utf-8")
    LOG.info("Enqueued task: %s", path.name)
    return path


def list_pending(repo_dir: Path) -> List[Dict[str, Any]]:
    """List all pending tasks (issue numbers). Returns list of task dicts."""
    base = _pending_dir(repo_dir)
    if not base.is_dir():
        return []
    tasks = []
    for f in sorted(base.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "repo" in data and "issue_number" in data:
                tasks.append(data)
        except (json.JSONDecodeError, OSError) as e:
            LOG.warning("Skip invalid queue file %s: %s", f, e)
    return tasks


def take_next(repo_dir: Path) -> Dict[str, Any] | None:
    """Take the next pending task (smallest issue number). Does not remove it.

    Worker should call mark_done or mark_failed after processing.
    """
    pending = list_pending(repo_dir)
    if not pending:
        return None
    # Sort by issue_number so we process in order
    pending.sort(key=lambda t: t["issue_number"])
    return pending[0]


def mark_done(repo_dir: Path, issue_number: int) -> None:
    """Move task from pending to done."""
    _move_task(repo_dir, issue_number, _done_dir(repo_dir))


def mark_failed(repo_dir: Path, issue_number: int) -> None:
    """Move task from pending to failed."""
    _move_task(repo_dir, issue_number, _failed_dir(repo_dir))


def _move_task(repo_dir: Path, issue_number: int, target_dir: Path) -> None:
    pending = _pending_dir(repo_dir)
    path = pending / f"{issue_number}.json"
    if not path.is_file():
        LOG.warning("No pending task %s to move", path)
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.exists():
        target.unlink()
    path.rename(target)
    LOG.info("Moved task %s to %s", path.name, target_dir.name)
