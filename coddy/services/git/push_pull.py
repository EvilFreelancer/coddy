"""Pull from and push to remote (origin)."""

import logging
import re
from pathlib import Path

from coddy.services.git._run import _run_git
from coddy.services.git.commits import add_all_and_commit

_ISSUE_RE = re.compile(r"#(\d+)")


def _extract_issue_tag(commit_message: str) -> str:
    """Extract first #N from commit_message, or return empty string."""
    m = _ISSUE_RE.search(commit_message)
    return m.group(0) if m else ""


def run_git_pull(
    branch: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """Run git pull origin <branch> in the repository."""
    cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()
    _run_git(["pull", "origin", branch], cwd=cwd, log=log)
    if log:
        log.info("Pulled origin/%s", branch)


def push_branch(
    branch_name: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """Push the given branch to origin."""
    cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()
    _run_git(["push", "origin", branch_name], cwd=cwd, log=log)
    if log:
        log.info("Pushed branch %s to origin", branch_name)


def commit_all_and_push(
    branch_name: str,
    commit_message: str,
    bot_name: str,
    bot_email: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """Stage all changes, commit with bot identity, and push branch to origin.

    Pass bot_name and bot_email from config (config.bot.name,
    config.bot.email).
    """
    tag = _extract_issue_tag(commit_message)
    if add_all_and_commit(commit_message, bot_name, bot_email, repo_dir=repo_dir, log=log):
        if log and tag:
            log.info("%s: committing and pushing to %s", tag, branch_name)
        push_branch(branch_name, repo_dir=repo_dir, log=log)
