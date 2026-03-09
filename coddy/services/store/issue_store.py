"""Issue storage in .coddy/issues/open/ and .coddy/issues/closed/ as YAML
files.

One file per issue: {state}/{issue_id}.yaml. Platform state (open/closed) is reflected
by the folder; workflow status is in the YAML. When state changes (e.g. issue closed),
the file is moved to the other folder.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from coddy.services.store.schemas import IssueComment, IssueFile

ISSUES_DIR = ".coddy/issues"
ISSUE_STATES = ("open", "closed")

LOG = logging.getLogger("coddy.services.store.issue_store")


def _issues_dir(repo_dir: Path) -> Path:
    return Path(repo_dir) / ISSUES_DIR


def _issue_path(repo_dir: Path, issue_id: int, state: str = "open") -> Path:
    if state not in ISSUE_STATES:
        state = "open"
    return _issues_dir(repo_dir) / state / f"{issue_id}.yaml"


def load_issue(repo_dir: Path, issue_id: int) -> IssueFile | None:
    """Load issue from .coddy/issues/open/{id}.yaml or closed/{id}.yaml.

    Looks in open/ first, then closed/. Returns None if missing or
    invalid.
    """
    for state in ISSUE_STATES:
        path = _issue_path(repo_dir, issue_id, state)
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not data:
                return None
            data.setdefault("issue_id", issue_id)
            data.setdefault("state", state)
            return IssueFile.model_validate(data)
        except (OSError, yaml.YAMLError, Exception) as e:
            LOG.warning("Failed to load issue %s: %s", path, e)
            return None
    return None


def save_issue(repo_dir: Path, issue_id: int, issue: IssueFile) -> Path:
    """Write issue to .coddy/issues/{state}/{issue_id}.yaml.

    Uses issue.state for folder. Creates dir if needed.
    """
    state = issue.state if issue.state in ISSUE_STATES else "open"
    path = _issue_path(repo_dir, issue_id, state)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = issue.model_dump(mode="json", exclude_none=True)
    if payload.get("assigned_at") is None:
        payload.pop("assigned_at", None)
    if payload.get("assigned_to") is None or payload.get("assigned_to") == "":
        payload.pop("assigned_to", None)
    for comment in payload.get("comments") or []:
        if comment.get("deleted_at") is None:
            comment.pop("deleted_at", None)
    if issue.issue_id is None:
        payload["issue_id"] = issue_id
    payload.setdefault("state", state)
    raw = yaml.dump(
        payload,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(raw, encoding="utf-8")
    LOG.debug("Saved issue #%s to %s", issue_id, path)
    return path


def create_issue(
    repo_dir: Path,
    issue_id: int,
    repo: str,
    title: str,
    description: str,
    author: str,
    created_at: int | None = None,
    updated_at: int | None = None,
    assigned_at: int | None = None,
    assigned_to: str | None = None,
    state: str = "open",
) -> IssueFile:
    """Create a new issue file with status pending_plan.

    comments is empty by default (title/description are separate
    fields). All date fields are Unix timestamps.
    assigned_at/assigned_to omitted when not assigned.
    state determines folder: open or closed.
    """
    now_ts = int(datetime.now(UTC).timestamp())
    created = created_at if created_at is not None else now_ts
    updated = updated_at if updated_at is not None else now_ts
    if state not in ISSUE_STATES:
        state = "open"
    issue = IssueFile(
        author=author,
        created_at=created,
        updated_at=updated,
        status="pending_plan",
        title=title,
        description=description,
        comments=[],
        repo=repo,
        issue_id=issue_id,
        assigned_at=assigned_at,
        assigned_to=assigned_to,
        state=state,
    )
    save_issue(repo_dir, issue_id, issue)
    LOG.info("Created issue #%s, status pending_plan, state %s", issue_id, state)
    return issue


def add_comment(
    repo_dir: Path,
    issue_id: int,
    name: str,
    content: str,
    created_at: int | None = None,
    updated_at: int | None = None,
    comment_id: int | None = None,
) -> None:
    """Append a comment to the issue thread and bump updated_at."""
    issue = load_issue(repo_dir, issue_id)
    if not issue:
        LOG.warning("Cannot add comment: issue #%s not found", issue_id)
        return
    now_ts = int(datetime.now(UTC).timestamp())
    ts_created = created_at if created_at is not None else now_ts
    ts_updated = updated_at if updated_at is not None else now_ts
    issue.comments.append(
        IssueComment(
            comment_id=comment_id,
            name=name,
            content=content,
            created_at=ts_created,
            updated_at=ts_updated,
        )
    )
    issue.updated_at = now_ts
    save_issue(repo_dir, issue_id, issue)
    LOG.debug("Added comment to issue #%s from %s", issue_id, name)


def update_comment(
    repo_dir: Path,
    issue_id: int,
    comment_id: int,
    content: str,
    updated_at: int | None = None,
) -> bool:
    """Update comment by comment_id.

    Returns True if found and updated.
    """
    issue = load_issue(repo_dir, issue_id)
    if not issue:
        return False
    now_ts = int(datetime.now(UTC).timestamp())
    ts_updated = updated_at if updated_at is not None else now_ts
    for c in issue.comments:
        if c.comment_id == comment_id:
            c.content = content
            c.updated_at = ts_updated
            issue.updated_at = now_ts
            save_issue(repo_dir, issue_id, issue)
            LOG.debug("Updated comment %s on issue #%s", comment_id, issue_id)
            return True
    return False


def delete_comment(repo_dir: Path, issue_id: int, comment_id: int, deleted_at: int | None = None) -> bool:
    """Mark comment as deleted (soft delete, set deleted_at).

    Returns True if found.
    """
    issue = load_issue(repo_dir, issue_id)
    if not issue:
        return False
    now_ts = int(datetime.now(UTC).timestamp())
    ts = deleted_at if deleted_at is not None else now_ts
    for c in issue.comments:
        if c.comment_id == comment_id:
            c.deleted_at = ts
            issue.updated_at = now_ts
            save_issue(repo_dir, issue_id, issue)
            LOG.debug("Marked comment %s on issue #%s as deleted", comment_id, issue_id)
            return True
    return False


def set_issue_status(repo_dir: Path, issue_id: int, status: str) -> None:
    """Update issue workflow status (e.g. waiting_confirmation, queued)."""
    issue = load_issue(repo_dir, issue_id)
    if not issue:
        LOG.warning("Cannot set status: issue #%s not found", issue_id)
        return
    issue.status = status
    issue.updated_at = int(datetime.now(UTC).timestamp())
    save_issue(repo_dir, issue_id, issue)
    LOG.info("Issue #%s status -> %s", issue_id, status)


def set_issue_state(repo_dir: Path, issue_id: int, new_state: str) -> None:
    """Move issue file to open/ or closed/ and update state in YAML."""
    if new_state not in ISSUE_STATES:
        new_state = "open"
    issue = load_issue(repo_dir, issue_id)
    if not issue:
        LOG.warning("Cannot set state: issue #%s not found", issue_id)
        return
    old_path = _issue_path(repo_dir, issue_id, issue.state)
    issue.state = new_state
    issue.updated_at = int(datetime.now(UTC).timestamp())
    save_issue(repo_dir, issue_id, issue)
    if old_path.is_file() and old_path != _issue_path(repo_dir, issue_id, new_state):
        old_path.unlink()
    LOG.info("Issue #%s state -> %s", issue_id, new_state)


def set_agent_clarification(repo_dir: Path, issue_id: int, message: str, bot_name: str = "@bot") -> None:
    """Add a bot comment with the clarification message and set status to
    waiting_user_reply.

    Observer will later post that comment to the platform and set status
    to clarification_sent.
    """
    issue = load_issue(repo_dir, issue_id)
    if not issue:
        LOG.warning("Cannot set agent clarification: issue #%s not found", issue_id)
        return
    now_ts = int(datetime.now(UTC).timestamp())
    add_comment(repo_dir, issue_id, bot_name, message, created_at=now_ts, updated_at=now_ts)
    set_issue_status(repo_dir, issue_id, "waiting_user_reply")
    LOG.info("Issue #%s: agent clarification comment added, status -> waiting_user_reply", issue_id)


def mark_clarification_sent(repo_dir: Path, issue_id: int) -> None:
    """Set issue status to clarification_sent (comment already posted by
    observer)."""
    issue = load_issue(repo_dir, issue_id)
    if not issue:
        LOG.warning("Cannot mark clarification sent: issue #%s not found", issue_id)
        return
    now_ts = int(datetime.now(UTC).timestamp())
    issue.status = "clarification_sent"
    issue.updated_at = now_ts
    save_issue(repo_dir, issue_id, issue)
    LOG.info("Issue #%s: clarification marked sent, status -> clarification_sent", issue_id)


def list_issues_by_status(repo_dir: Path, status: str) -> list[tuple[int, IssueFile]]:
    """List all issues with the given workflow status.

    Scans both open/ and closed/ folders. Returns list of (issue_id,
    IssueFile).
    """
    base = _issues_dir(repo_dir)
    out = []
    for state in ISSUE_STATES:
        subdir = base / state
        if not subdir.is_dir():
            continue
        for f in subdir.glob("*.yaml"):
            if not f.stem.isdigit():
                continue
            try:
                n = int(f.stem)
                issue = load_issue(repo_dir, n)
                if issue and issue.status == status:
                    out.append((n, issue))
            except (ValueError, Exception):
                continue
    return out


def list_queued(repo_dir: Path) -> list[tuple[int, IssueFile]]:
    """List issues with status=queued (for worker)."""
    return list_issues_by_status(repo_dir, "queued")


def list_pending_plan(repo_dir: Path) -> list[tuple[int, IssueFile]]:
    """List issues with status=pending_plan."""
    return list_issues_by_status(repo_dir, "pending_plan")
