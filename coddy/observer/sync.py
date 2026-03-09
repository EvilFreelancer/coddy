"""Sync issues and PRs from Git platform API into .coddy/ at observer startup.

Fetches open/closed issues and open/merged/rejected/draft PRs and writes YAML
files into .coddy/issues/{open|closed}/ and
.coddy/pull_requests/{open|merged|rejected|draft}/. Existing issue workflow
status and comments are preserved when updating from API.
"""

import logging
from pathlib import Path
from typing import Any

from coddy.services.store import (
    create_issue,
    load_issue,
    save_issue,
    set_issue_state,
    set_pr_status,
)


def _pr_status_from_api(pr: Any) -> str:
    """Map platform PR state, draft flag and merged_at to store status
    (open, merged, rejected, draft)."""
    if getattr(pr, "state", "open") == "open":
        if getattr(pr, "draft", False):
            return "draft"
        return "open"
    if getattr(pr, "merged_at", None):
        return "merged"
    return "rejected"


def run_sync(config: Any, repo_dir: Path, log: logging.Logger | None = None) -> None:
    """Fetch issues and PRs from the platform API and write to .coddy/.

    Uses config.bot.repository, config.github_token_resolved,
    config.github.api_url. Only runs for git_platform=github; other
    platforms no-op. Preserves existing issue status and comments when
    updating.
    """
    logger = log or logging.getLogger("coddy.observer.sync")
    repo = getattr(config.bot, "repository", "") or ""
    if not repo:
        logger.warning("Sync skipped: bot.repository not set")
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("Sync skipped: only GitHub supported")
        return
    token = getattr(config, "github_token_resolved", None)
    if not token:
        logger.warning("Sync skipped: no GitHub token")
        return

    from coddy.observer.adapters.github import GitHubAdapter

    api_url = getattr(config.github, "api_url", "https://api.github.com")
    adapter = GitHubAdapter(token=token, api_url=api_url)

    # Sync issues (open + closed)
    try:
        for state in ("open", "closed"):
            issues = adapter.list_issues(repo, state=state)
            platform_state = state
            for issue in issues:
                issue_id = issue.number
                existing = load_issue(repo_dir, issue_id)
                created_ts = int(issue.created_at.timestamp()) if hasattr(issue.created_at, "timestamp") else None
                updated_ts = int(issue.updated_at.timestamp()) if hasattr(issue.updated_at, "timestamp") else None
                if existing:
                    if existing.state != platform_state:
                        set_issue_state(repo_dir, issue_id, platform_state)
                        existing = load_issue(repo_dir, issue_id)
                    if existing:
                        existing.title = issue.title or existing.title
                        existing.description = issue.body or existing.description
                        existing.updated_at = updated_ts or existing.updated_at
                        save_issue(repo_dir, issue_id, existing)
                    logger.debug("Synced issue #%s (%s)", issue_id, platform_state)
                else:
                    create_issue(
                        repo_dir,
                        issue_id,
                        repo,
                        issue.title or "",
                        issue.body or "",
                        issue.author or "unknown",
                        created_at=created_ts,
                        updated_at=updated_ts,
                        state=platform_state,
                    )
                    logger.debug("Created issue #%s from sync (%s)", issue_id, platform_state)
    except Exception as e:
        logger.warning("Sync issues failed: %s", e)

    # Sync PRs
    try:
        pulls = adapter.list_pulls(repo, state="all")
        for pr in pulls:
            status = _pr_status_from_api(pr)
            set_pr_status(repo_dir, pr.number, status, repo=repo)
            logger.debug("Synced PR #%s -> %s", pr.number, status)
    except Exception as e:
        logger.warning("Sync PRs failed: %s", e)

    logger.info("Sync completed for %s", repo)
