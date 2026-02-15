"""Branch name sanitization, validation, and local branch operations (checkout,
fetch)."""

import logging
import re
from pathlib import Path

from coddy.services.git._run import GitRunnerError, _run_git

# Git ref name rules: no "..", no space, no ~ ^ : ? * [ \ ; output uses only a-z, 0-9, dash
_INVALID_BRANCH_CHARS_RE = re.compile(r"[^a-z0-9\-]")
_DOUBLE_DASH_RE = re.compile(r"-+")


def sanitize_branch_name(text: str, max_length: int = 100) -> str:
    """Sanitize a string for use as (part of) a branch name.

    Replaces spaces with dashes, removes invalid characters, lowercases,
    collapses and strips dashes, and truncates to max_length without
    leaving a trailing dash.

    Args:
        text: Raw string (e.g. issue title fragment).
        max_length: Maximum length of the result (default 100).

    Returns:
        Sanitized string safe for branch names; may be empty if input
        had no valid characters.
    """
    if not text or not text.strip():
        return ""
    s = text.lower().strip()
    for char in " ._":
        s = s.replace(char, "-")
    s = _INVALID_BRANCH_CHARS_RE.sub("", s)
    s = _DOUBLE_DASH_RE.sub("-", s).strip("-")
    if len(s) > max_length:
        s = s[:max_length].rstrip("-")
    return s


def is_valid_branch_name(name: str) -> bool:
    """Check that a branch name is valid (transformation was applied
    correctly).

    Valid: non-empty, only lowercase letters, digits, dashes; no "..";
    no leading or trailing dash.

    Args:
        name: Branch name to validate.

    Returns:
        True if the name is valid for use as a Git branch name.
    """
    if not name or not name.strip():
        return False
    if ".." in name:
        return False
    if name.startswith("-") or name.endswith("-"):
        return False
    return bool(re.match(r"^[a-z0-9\-]+$", name))


def branch_name_from_issue(issue_id: int, title: str) -> str:
    """Build branch name from issue number and title: {number}-short-description.

    Format: lowercase, words separated by dashes; uses sanitize_branch_name
    for spaces, invalid chars, and truncation (max 100 chars for slug).

    Args:
        issue_id: Issue number.
        title: Issue title.

    Returns:
        Branch name like "42-add-user-login".

    Raises:
        ValueError: If the resulting name is invalid.
    """
    slug = sanitize_branch_name(title, max_length=100)
    name = f"{issue_id}-{slug}" if slug else str(issue_id)
    if not is_valid_branch_name(name):
        raise ValueError(f"Branch name transformation produced invalid name: {name!r}")
    return name


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
