"""PR storage in .coddy/prs/ as YAML files.

One file per PR: {pr_number}.yaml. Status is updated in place (open, merged, closed).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from coddy.observer.prs.pr_file import PRFile

PRS_DIR = ".coddy/prs"

LOG = logging.getLogger("coddy.observer.prs.pr_store")


def _prs_dir(repo_dir: Path) -> Path:
    return Path(repo_dir) / PRS_DIR


def _pr_path(repo_dir: Path, pr_number: int) -> Path:
    return _prs_dir(repo_dir) / f"{pr_number}.yaml"


def load_pr(repo_dir: Path, pr_number: int) -> PRFile | None:
    """Load PR from .coddy/prs/{pr_number}.yaml. Returns None if missing or invalid."""
    path = _pr_path(repo_dir, pr_number)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data:
            return None
        return PRFile.model_validate(data)
    except (OSError, yaml.YAMLError, Exception) as e:
        LOG.warning("Failed to load PR %s: %s", pr_number, e)
        return None


def save_pr(repo_dir: Path, pr: PRFile) -> Path:
    """Write PR to .coddy/prs/{pr_number}.yaml. Creates dir if needed."""
    path = _pr_path(repo_dir, pr.pr_number)
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
    LOG.debug("Saved PR #%s to %s", pr.pr_number, path)
    return path


def set_pr_status(
    repo_dir: Path,
    pr_number: int,
    status: str,
    repo: str | None = None,
    issue_number: int | None = None,
) -> None:
    """Create or update PR file with given status (open, merged, closed)."""
    now = datetime.now(UTC).isoformat()
    pr = load_pr(repo_dir, pr_number)
    if pr:
        pr.status = status
        pr.updated_at = now
    else:
        pr = PRFile(
            pr_number=pr_number,
            repo=repo or getattr(repo_dir, "_repo", "") or "",
            status=status,
            issue_number=issue_number,
            created_at=now,
            updated_at=now,
        )
    if repo:
        pr.repo = repo
    if issue_number is not None:
        pr.issue_number = issue_number
    save_pr(repo_dir, pr)
    LOG.info("PR #%s status -> %s", pr_number, status)
