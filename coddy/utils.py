"""Shared utilities (e.g. branch name sanitization)."""

import re

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
