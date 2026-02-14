"""Issue storage in .coddy/issues/ as YAML files.

One file per issue: {issue_number}.yaml with meta, title, description, messages.
Status is updated in place (no moving files). Worker picks issues with status=queued.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from coddy.issue_file import IssueFile, IssueMessage

ISSUES_DIR = ".coddy/issues"

LOG = logging.getLogger("coddy.issue_store")


def _issues_dir(repo_dir: Path) -> Path:
    return Path(repo_dir) / ISSUES_DIR


def _issue_path(repo_dir: Path, issue_number: int) -> Path:
    return _issues_dir(repo_dir) / f"{issue_number}.yaml"


def load_issue(repo_dir: Path, issue_number: int) -> IssueFile | None:
    """Load issue from .coddy/issues/{issue_number}.yaml. Returns None if missing or invalid."""
    path = _issue_path(repo_dir, issue_number)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data:
            return None
        data.setdefault("issue_number", issue_number)
        return IssueFile.model_validate(data)
    except (OSError, yaml.YAMLError, Exception) as e:
        LOG.warning("Failed to load issue %s: %s", path, e)
        return None


def save_issue(repo_dir: Path, issue_number: int, issue: IssueFile) -> Path:
    """Write issue to .coddy/issues/{issue_number}.yaml. Creates dir if needed."""
    path = _issue_path(repo_dir, issue_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep issue_number in file for readability
    payload = issue.model_dump(mode="json", exclude_none=True)
    if issue.issue_number is None:
        payload["issue_number"] = issue_number
    raw = yaml.dump(
        payload,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(raw, encoding="utf-8")
    LOG.debug("Saved issue #%s to %s", issue_number, path)
    return path


def create_issue(
    repo_dir: Path,
    issue_number: int,
    repo: str,
    title: str,
    description: str,
    author: str,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> IssueFile:
    """Create a new issue file with status pending_plan. First message = title + description."""
    now = datetime.now(UTC).isoformat()
    created = created_at or now
    updated = updated_at or now
    first_content = f"{title}\n\n{description}".strip() if title or description else "(no content)"
    msg = IssueMessage(name=author, content=first_content, timestamp=int(datetime.now(UTC).timestamp()))
    issue = IssueFile(
        author=author,
        created_at=created,
        updated_at=updated,
        status="pending_plan",
        title=title,
        description=description,
        messages=[msg],
        repo=repo,
        issue_number=issue_number,
        assigned_at=now,
    )
    save_issue(repo_dir, issue_number, issue)
    LOG.info("Created issue #%s, status pending_plan", issue_number)
    return issue


def add_message(
    repo_dir: Path,
    issue_number: int,
    name: str,
    content: str,
    timestamp: int | None = None,
) -> None:
    """Append a message to the issue thread and bump updated_at."""
    issue = load_issue(repo_dir, issue_number)
    if not issue:
        LOG.warning("Cannot add message: issue #%s not found", issue_number)
        return
    ts = timestamp or int(datetime.now(UTC).timestamp())
    issue.messages.append(IssueMessage(name=name, content=content, timestamp=ts))
    issue.updated_at = datetime.now(UTC).isoformat()
    save_issue(repo_dir, issue_number, issue)
    LOG.debug("Added message to issue #%s from %s", issue_number, name)


def set_status(repo_dir: Path, issue_number: int, status: str) -> None:
    """Update issue status (e.g. waiting_confirmation, queued)."""
    issue = load_issue(repo_dir, issue_number)
    if not issue:
        LOG.warning("Cannot set status: issue #%s not found", issue_number)
        return
    issue.status = status
    issue.updated_at = datetime.now(UTC).isoformat()
    save_issue(repo_dir, issue_number, issue)
    LOG.info("Issue #%s status -> %s", issue_number, status)


def list_issues_by_status(repo_dir: Path, status: str) -> list[tuple[int, IssueFile]]:
    """List all issues with the given status. Returns list of (issue_number, IssueFile)."""
    base = _issues_dir(repo_dir)
    if not base.is_dir():
        return []
    out = []
    for f in base.glob("*.yaml"):
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
    """List issues with status=pending_plan (for scheduler)."""
    return list_issues_by_status(repo_dir, "pending_plan")
