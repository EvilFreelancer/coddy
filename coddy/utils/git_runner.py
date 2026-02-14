"""Run git commands in the repository (fetch, checkout).

Used after creating a branch via platform API so the local workspace
switches to that branch.
"""

import logging
import subprocess
from pathlib import Path

from coddy.utils.branch import is_valid_branch_name, sanitize_branch_name


class GitRunnerError(Exception):
    """Raised when a git command fails."""

    pass


def _run_git(args: list[str], cwd: Path, log: logging.Logger | None = None) -> None:
    """Run git command; raise GitRunnerError on non-zero exit."""
    cmd = ["git"] + args
    try:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, timeout=60)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip()
        if log:
            log.warning("Git %s failed: %s", args, err)
        raise GitRunnerError(f"git {' '.join(args)}: {err}") from e
    except FileNotFoundError as e:
        raise GitRunnerError("git not found") from e


def branch_name_from_issue(issue_number: int, title: str) -> str:
    """
    Build branch name from issue number and title: {number}-short-description.

    Format: lowercase, words separated by dashes; uses sanitize_branch_name
    for spaces, invalid chars, and truncation (max 100 chars for slug).
    """
    slug = sanitize_branch_name(title, max_length=100)
    name = f"{issue_number}-{slug}" if slug else str(issue_number)
    if not is_valid_branch_name(name):
        raise ValueError(f"Branch name transformation produced invalid name: {name!r}")
    return name


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


def fetch_and_checkout_branch(
    branch_name: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """Fetch from origin and checkout the given branch (must exist on
    remote)."""
    cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()
    _run_git(["fetch", "origin", branch_name], cwd=cwd, log=log)
    _run_git(["checkout", branch_name], cwd=cwd, log=log)
    if log:
        log.info("Checked out branch %s", branch_name)


def checkout_branch(
    branch_name: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """Checkout the given branch (must exist locally or on remote)."""
    cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()
    try:
        _run_git(["checkout", branch_name], cwd=cwd, log=log)
    except GitRunnerError:
        _run_git(["fetch", "origin", branch_name], cwd=cwd, log=log)
        _run_git(["checkout", branch_name], cwd=cwd, log=log)
    if log:
        log.info("Checked out branch %s", branch_name)


def commit_all_and_push(
    branch_name: str,
    commit_message: str,
    bot_name: str,
    bot_email: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """Stage all changes, commit with bot identity, and push branch to
    origin."""
    cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()
    _run_git(["add", "-A"], cwd=cwd, log=log)
    try:
        _run_git(
            ["-c", f"user.name={bot_name}", "-c", f"user.email={bot_email}", "commit", "-m", commit_message],
            cwd=cwd,
            log=log,
        )
    except GitRunnerError as e:
        if "nothing to commit" in str(e).lower() or "no changes" in str(e).lower():
            if log:
                log.info("Nothing to commit, working tree clean")
            return
        raise
    _run_git(["push", "origin", branch_name], cwd=cwd, log=log)
    if log:
        log.info("Pushed branch %s to origin", branch_name)
