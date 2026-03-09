"""Poll .coddy/issues/ and .coddy/pull_requests/ and post to platform.

- plan_ready: worker wrote the plan; post last comment to GitHub, set waiting_confirmation.
- waiting_user_reply: post last comment (clarification), set clarification_sent.
- pull_requests/pending/: worker wrote PR request; create PR via API, move to open/, set label review.
- review_received: idle timeout passed since last review; set pending_plan for worker to process.
"""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coddy.observer.adapters.base import GitPlatformError
from coddy.services.store import (
    delete_pending_pr_request,
    list_issues_by_status,
    list_pending_pr_requests,
    list_prs_by_workflow_status,
    mark_clarification_sent,
    save_pr,
    set_issue_status,
    set_pr_workflow_status,
)
from coddy.services.store.schemas import PRFile

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


def run_create_pr_poll(
    config: Any,
    repo_dir: Path,
    log: logging.Logger | None = None,
) -> None:
    """Process pending PR requests: create PR via API, save to open/, set label review."""
    logger = log or LOG
    pending = list_pending_pr_requests(repo_dir)
    if not pending:
        return
    repo = getattr(config.bot, "repository", "") or ""
    if not repo:
        logger.debug("No bot.repository configured, skipping create PR poll")
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("Create PR poll only supports GitHub, skipping")
        return
    token = getattr(config, "github_token_resolved", None)
    if not token:
        logger.debug("No GitHub token, skipping create PR poll")
        return

    from coddy.observer.adapters.github import GitHubAdapter

    adapter = GitHubAdapter(
        token=token,
        api_url=getattr(config.github, "api_url", "https://api.github.com"),
    )

    for issue_id, req in pending:
        req_repo = req.repo or repo
        try:
            pr = adapter.create_pr(
                req_repo,
                title=req.title,
                body=req.body,
                head=req.head,
                base=req.base,
            )
            pr_number = getattr(pr, "number", 0)
            pr_status = getattr(pr, "state", None)
            if not isinstance(pr_status, str):
                pr_status = "open"
            now = datetime.now(UTC).isoformat()
            pr_file = PRFile(
                pr_id=pr_number,
                repo=req_repo,
                status=pr_status,
                issue_id=issue_id,
                created_at=now,
                updated_at=now,
            )
            save_pr(repo_dir, pr_file)
            delete_pending_pr_request(repo_dir, issue_id)
            adapter.set_issue_labels(req_repo, issue_id, ["review"])
            logger.info("Created PR #%s for issue #%s, label set to review", pr_number, issue_id)
        except GitPlatformError as e:
            logger.warning("Failed to create PR for issue #%s: %s", issue_id, e)


DEFAULT_REVIEW_IDLE_TIMEOUT = 30


def run_review_idle_poll(
    config: Any,
    repo_dir: Path,
    log: logging.Logger | None = None,
    idle_timeout: int | None = None,
) -> None:
    """Check PRs with workflow_status=review_received.

    If idle timeout has passed since last_review_ts, transition to
    pending_plan so the worker can generate a review response plan.
    """
    logger = log or LOG
    received = list_prs_by_workflow_status(repo_dir, "review_received")
    if not received:
        return

    timeout = idle_timeout if idle_timeout is not None else DEFAULT_REVIEW_IDLE_TIMEOUT
    now = int(time.time())

    for pr_id, pr_file in received:
        last_ts = pr_file.last_review_ts or 0
        if now - last_ts >= timeout:
            set_pr_workflow_status(repo_dir, pr_id, "pending_plan")
            logger.info(
                "PR #%s: idle timeout reached (%ss since last review), workflow_status -> pending_plan",
                pr_id,
                now - last_ts,
            )
