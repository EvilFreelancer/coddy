"""PR storage in .coddy/pull_requests/open/, merged/, rejected/, draft/ as YAML files.

One file per PR: {status}/{pr_id}.yaml. Status is reflected by the folder.
When status changes, the file is moved to the correct folder.

Pending: .coddy/pull_requests/pending/{issue_id}.yaml - worker writes PR request
here; observer creates PR via API and moves record to open/{pr_id}.yaml.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from coddy.services.store.schemas import PendingPRRequest, PRFile

PRS_DIR = ".coddy/pull_requests"
PR_STATUSES = ("open", "merged", "rejected", "draft")
PENDING_SUBDIR = "pending"

LOG = logging.getLogger("coddy.services.store.pr_store")


def _prs_dir(repo_dir: Path) -> Path:
    return Path(repo_dir) / PRS_DIR


def _pr_path(repo_dir: Path, pr_id: int, status: str = "open") -> Path:
    if status not in PR_STATUSES:
        status = "open"
    return _prs_dir(repo_dir) / status / f"{pr_id}.yaml"


def _pending_dir(repo_dir: Path) -> Path:
    return _prs_dir(repo_dir) / PENDING_SUBDIR


def _pending_path(repo_dir: Path, issue_id: int) -> Path:
    return _pending_dir(repo_dir) / f"{issue_id}.yaml"


def load_pr(repo_dir: Path, pr_id: int) -> PRFile | None:
    """Load PR from .coddy/pull_requests/{open|merged|rejected|draft}/{pr_id}.yaml.

    Searches all status folders. Returns None if missing or invalid.
    """
    for status in PR_STATUSES:
        path = _pr_path(repo_dir, pr_id, status)
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not data:
                return None
            data.setdefault("status", status)
            return PRFile.model_validate(data)
        except (OSError, yaml.YAMLError, Exception) as e:
            LOG.warning("Failed to load PR %s: %s", pr_id, e)
            return None
    return None


def save_pr(repo_dir: Path, pr: PRFile) -> Path:
    """Write PR to .coddy/pull_requests/{status}/{pr_id}.yaml.

    Uses pr.status for folder. Creates dir if needed.
    """
    status = pr.status if pr.status in PR_STATUSES else "open"
    path = _pr_path(repo_dir, pr.pr_id, status)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = pr.model_dump(mode="json", exclude_none=True)
    payload.setdefault("status", status)
    raw = yaml.dump(
        payload,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(raw, encoding="utf-8")
    LOG.debug("Saved PR #%s to %s", pr.pr_id, path)
    return path


def set_pr_status(
    repo_dir: Path,
    pr_id: int,
    status: str,
    repo: str | None = None,
    issue_number: int | None = None,
) -> None:
    """Create or update PR file with given status (open, merged, rejected, draft).

    If status changes, the file is written to the new folder; the old
    file is removed if it existed in another folder. Accepts "closed" as
    alias for "rejected" for backward compatibility.
    """
    if status == "closed":
        status = "rejected"
    if status not in PR_STATUSES:
        status = "open"
    now = datetime.now(UTC).isoformat()
    pr = load_pr(repo_dir, pr_id)
    old_status = pr.status if pr else None
    if pr:
        pr.status = status
        pr.updated_at = now
    else:
        pr = PRFile(
            pr_id=pr_id,
            repo=repo or getattr(repo_dir, "_repo", "") or "",
            status=status,
            issue_id=issue_number,
            created_at=now,
            updated_at=now,
        )
    if repo:
        pr.repo = repo
    if issue_number is not None:
        pr.issue_id = issue_number
    save_pr(repo_dir, pr)
    if old_status and old_status != status:
        old_path = _pr_path(repo_dir, pr_id, old_status)
        if old_path.is_file():
            old_path.unlink()
    LOG.info("PR #%s status -> %s", pr_id, status)


def list_pending_pr_requests(repo_dir: Path) -> list[tuple[int, PendingPRRequest]]:
    """List all pending PR requests (worker wrote, observer should create PR).

    Returns list of (issue_id, PendingPRRequest) sorted by issue_id.
    """
    pending_dir = _pending_dir(repo_dir)
    if not pending_dir.is_dir():
        return []
    out: list[tuple[int, PendingPRRequest]] = []
    for path in sorted(pending_dir.glob("*.yaml")):
        try:
            stem = path.stem
            if not stem.isdigit():
                continue
            issue_id = int(stem)
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not data:
                continue
            out.append((issue_id, PendingPRRequest.model_validate(data)))
        except (OSError, yaml.YAMLError, Exception) as e:
            LOG.warning("Failed to load pending PR request %s: %s", path.name, e)
    out.sort(key=lambda t: t[0])
    return out


def save_pending_pr_request(repo_dir: Path, req: PendingPRRequest) -> Path:
    """Write pending PR request to
    .coddy/pull_requests/pending/{issue_id}.yaml."""
    path = _pending_path(repo_dir, req.issue_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = yaml.dump(
        req.model_dump(mode="json", exclude_none=True),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(raw, encoding="utf-8")
    LOG.debug("Saved pending PR request for issue #%s to %s", req.issue_id, path)
    return path


def delete_pending_pr_request(repo_dir: Path, issue_id: int) -> None:
    """Remove pending PR request file after observer has created the PR."""
    path = _pending_path(repo_dir, issue_id)
    if path.is_file():
        path.unlink()
        LOG.debug("Deleted pending PR request for issue #%s", issue_id)
