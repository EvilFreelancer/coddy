"""PR storage in .coddy/prs/ as YAML files.

One file per PR: {pr_id}.yaml. Status is updated in place (open, merged, closed).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from coddy.services.store.schemas import PRFile

PRS_DIR = ".coddy/prs"

LOG = logging.getLogger("coddy.services.store.pr_store")


def _prs_dir(repo_dir: Path) -> Path:
    return Path(repo_dir) / PRS_DIR


def _pr_path(repo_dir: Path, pr_id: int) -> Path:
    return _prs_dir(repo_dir) / f"{pr_id}.yaml"


def load_pr(repo_dir: Path, pr_id: int) -> PRFile | None:
    """Load PR from .coddy/prs/{pr_id}.yaml. Returns None if missing or invalid."""
    path = _pr_path(repo_dir, pr_id)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data:
            return None
        return PRFile.model_validate(data)
    except (OSError, yaml.YAMLError, Exception) as e:
        LOG.warning("Failed to load PR %s: %s", pr_id, e)
        return None


def save_pr(repo_dir: Path, pr: PRFile) -> Path:
    """Write PR to .coddy/prs/{pr_id}.yaml. Creates dir if needed."""
    path = _pr_path(repo_dir, pr.pr_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = pr.model_dump(mode="json", exclude_none=True)
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
    """Create or update PR file with given status (open, merged, closed)."""
    now = datetime.now(UTC).isoformat()
    pr = load_pr(repo_dir, pr_id)
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
    LOG.info("PR #%s status -> %s", pr_id, status)
