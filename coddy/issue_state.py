"""Per-issue state in .coddy/state/ as markdown files.

States: pending_plan (wait idle_minutes) -> waiting_confirmation (plan posted)
-> then user confirms -> task enqueued and state cleared.
"""

import logging
import re
from pathlib import Path
from typing import Any

STATE_DIR = ".coddy/state"

LOG = logging.getLogger("coddy.issue_state")


def _state_dir(repo_dir: Path) -> Path:
    return Path(repo_dir) / STATE_DIR


def _state_path(repo_dir: Path, issue_number: int) -> Path:
    return _state_dir(repo_dir) / f"{issue_number}.md"


def _parse_state_md(content: str) -> dict[str, Any] | None:
    """Parse state markdown into dict."""
    data = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-z_]+):\s*(.+)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if key in ("issue_number", "idle_minutes"):
                try:
                    data[key] = int(value)
                except ValueError:
                    data[key] = value
            else:
                data[key] = value
    return data if data else None


def _state_to_markdown(data: dict[str, Any]) -> str:
    """Serialize state dict to markdown."""
    lines = [f"# Issue {data.get('issue_number', '')}", ""]
    for k, v in sorted(data.items()):
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


def set_pending_plan(
    repo_dir: Path,
    issue_number: int,
    repo: str,
    title: str,
) -> None:
    """Set state to pending_plan (wait for idle_minutes before running planner)."""
    from datetime import UTC, datetime

    path = _state_path(repo_dir, issue_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "state": "pending_plan",
        "repo": repo,
        "issue_number": issue_number,
        "title": title,
        "assigned_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(_state_to_markdown(data), encoding="utf-8")
    LOG.info("Issue #%s state: pending_plan", issue_number)


def set_waiting_confirmation(
    repo_dir: Path,
    issue_number: int,
    repo: str,
    title: str,
) -> None:
    """Set state to waiting_confirmation (plan posted, wait for user yes)."""
    from datetime import UTC, datetime

    path = _state_path(repo_dir, issue_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "state": "waiting_confirmation",
        "repo": repo,
        "issue_number": issue_number,
        "title": title,
        "plan_posted_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(_state_to_markdown(data), encoding="utf-8")
    LOG.info("Issue #%s state: waiting_confirmation", issue_number)


def get_state(repo_dir: Path, issue_number: int) -> dict[str, Any] | None:
    """Load state for issue if any."""
    path = _state_path(repo_dir, issue_number)
    if not path.is_file():
        return None
    try:
        return _parse_state_md(path.read_text(encoding="utf-8"))
    except OSError as e:
        LOG.warning("Failed to read state %s: %s", path, e)
        return None


def list_pending_plan_states(repo_dir: Path) -> list[dict[str, Any]]:
    """List all issues in pending_plan state (for scheduler)."""
    base = _state_dir(repo_dir)
    if not base.is_dir():
        return []
    out = []
    for f in base.glob("*.md"):
        try:
            if not f.stem.isdigit():
                continue
            data = _parse_state_md(f.read_text(encoding="utf-8"))
            if data and data.get("state") == "pending_plan":
                data["issue_number"] = int(f.stem)
                out.append(data)
        except (OSError, ValueError):
            continue
    return out


def clear_state(repo_dir: Path, issue_number: int) -> None:
    """Remove state file (after enqueue or cancel)."""
    path = _state_path(repo_dir, issue_number)
    if path.is_file():
        path.unlink()
        LOG.info("Cleared state for issue #%s", issue_number)
