"""Poll .coddy/issues/ and post to platform.

- plan_ready: worker wrote the plan to the issue file; post last comment to GitHub, set waiting_confirmation.
- waiting_user_reply: post last comment (clarification), set clarification_sent.
"""

import logging
from pathlib import Path
from typing import Any

from coddy.services.store import (
    list_issues_by_status,
    mark_clarification_sent,
    set_issue_status,
)

LOG = logging.getLogger("coddy.observer.clarification_poll")


def _last_comment_content(issue_file: Any) -> str | None:
    """Return content of the last comment (when status=waiting_user_reply it is
    the one to post)."""
    if not issue_file.comments:
        return None
    content = (issue_file.comments[-1].content or "").strip()
    return content or None


def run_clarification_poll(
    config: Any,
    repo_dir: Path,
    log: logging.Logger | None = None,
) -> None:
    """Process issues with status=waiting_user_reply: post last unposted
    comment to platform, mark sent."""
    logger = log or LOG
    waiting = list_issues_by_status(repo_dir, "waiting_user_reply")
    if not waiting:
        return
    repo = getattr(config.bot, "repository", "") or ""
    if not repo:
        logger.debug("No bot.repository configured, skipping clarification poll")
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("Clarification poll only supports GitHub, skipping")
        return
    token = getattr(config, "github_token_resolved", None)
    if not token:
        logger.debug("No GitHub token, skipping clarification poll")
        return

    from coddy.observer.adapters.github import GitHubAdapter

    adapter = GitHubAdapter(
        token=token,
        api_url=getattr(config.github, "api_url", "https://api.github.com"),
    )

    for issue_number, issue_file in waiting:
        msg = _last_comment_content(issue_file)
        if not msg:
            continue
        issue_repo = issue_file.repo or repo
        try:
            adapter.create_comment(issue_repo, issue_number, msg)
            adapter.set_issue_labels(issue_repo, issue_number, ["stuck"])
            mark_clarification_sent(repo_dir, issue_number)
            logger.info("Posted clarification for issue #%s, status -> clarification_sent", issue_number)
        except Exception as e:
            logger.warning("Failed to post clarification for issue #%s: %s", issue_number, e)


def run_plan_post_poll(
    config: Any,
    repo_dir: Path,
    log: logging.Logger | None = None,
) -> None:
    """Process issues with status=plan_ready: post last comment (worker's plan)
    to GitHub, set waiting_confirmation."""
    logger = log or LOG
    plan_ready = list_issues_by_status(repo_dir, "plan_ready")
    if not plan_ready:
        return
    repo = getattr(config.bot, "repository", "") or ""
    if not repo:
        logger.debug("No bot.repository configured, skipping plan post poll")
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("Plan post poll only supports GitHub, skipping")
        return
    token = getattr(config, "github_token_resolved", None)
    if not token:
        logger.debug("No GitHub token, skipping plan post poll")
        return

    from coddy.observer.adapters.github import GitHubAdapter

    adapter = GitHubAdapter(
        token=token,
        api_url=getattr(config.github, "api_url", "https://api.github.com"),
    )

    for issue_number, issue_file in plan_ready:
        msg = _last_comment_content(issue_file)
        if not msg:
            continue
        issue_repo = issue_file.repo or repo
        try:
            adapter.create_comment(issue_repo, issue_number, msg)
            set_issue_status(repo_dir, issue_number, "waiting_confirmation")
            logger.info("Posted plan for issue #%s, status -> waiting_confirmation", issue_number)
        except Exception as e:
            logger.warning("Failed to post plan for issue #%s: %s", issue_number, e)
