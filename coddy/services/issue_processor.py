"""
Process one issue: create branch, check sufficiency, wait for clarification if needed, then run code gen.

Single-threaded: blocks in poll loop until user replies when data is insufficient.
"""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from coddy.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.agents.base import AIAgent
from coddy.models import Issue
from coddy.services.git_runner import (
    branch_name_from_issue,
    checkout_branch,
    commit_all_and_push,
    fetch_and_checkout_branch,
)
from coddy.services.task_file import read_agent_clarification

POLL_INTERVAL_SECONDS = 60
POLL_MAX_ITERATIONS = 60 * 24  # 24 hours at 1/min


def process_one_issue(
    adapter: GitPlatformAdapter,
    agent: AIAgent,
    issue: Issue,
    repo: str,
    repo_dir: Path | None = None,
    bot_username: str | None = None,
    bot_name: str | None = None,
    bot_email: str | None = None,
    default_branch: str | None = None,
    poll_interval: int = POLL_INTERVAL_SECONDS,
    log: logging.Logger | None = None,
) -> None:
    """
    Full flow for one issue in one thread: branch, sufficiency check, optional wait, then work.

    1. Create branch on remote and checkout locally.
    2. Ask agent if issue data is sufficient (e.g. evaluate_sufficiency).
    3. If not: post clarification, set label 'stuck', poll for new comments;
       when user replies, re-evaluate until sufficient or timeout.
    4. If sufficient: set label 'in progress', call agent.generate_code.
    5. If generate_code returns no PR body: read .coddy/task-{n}.md for
       "## Agent clarification request"; if present, post it to the issue and poll.
    """
    logger = log or logging.getLogger("coddy.issue_processor")
    repo_path = Path(repo_dir) if repo_dir is not None else Path.cwd()

    branch_name = branch_name_from_issue(issue.number, issue.title)
    logger.info("Creating or reusing branch %s for issue #%s", branch_name, issue.number)

    try:
        adapter.create_branch(repo, branch_name, base_branch=default_branch)
    except GitPlatformError as e:
        err_msg = str(e).lower()
        if "already exists" in err_msg or "422" in err_msg:
            logger.info("Branch %s already exists, switching to it", branch_name)
        else:
            logger.warning("Failed to create branch %s: %s", branch_name, e)
            return

    try:
        fetch_and_checkout_branch(branch_name, repo_dir=repo_path, log=logger)
    except Exception as e:
        logger.warning("Failed to checkout branch %s: %s", branch_name, e)
        return

    last_comment_at: datetime | None = None

    while True:
        issue = adapter.get_issue(repo, issue.number)
        comments = adapter.get_issue_comments(repo, issue.number, since=None)
        result = agent.evaluate_sufficiency(issue, comments)

        if result.sufficient:
            logger.info("Issue #%s: data sufficient, starting work", issue.number)
            try:
                adapter.set_issue_labels(repo, issue.number, ["in progress"])
            except GitPlatformError as e:
                logger.warning("Failed to set labels: %s", e)
            pr_body = agent.generate_code(issue, comments)

            if pr_body:
                commit_message = f"#{issue.number} {issue.title}"
                if bot_name and bot_email:
                    try:
                        commit_all_and_push(
                            branch_name,
                            commit_message,
                            bot_name,
                            bot_email,
                            repo_dir=repo_path,
                            log=logger,
                        )
                    except Exception as e:
                        logger.warning("Failed to commit/push: %s", e)
                try:
                    base_branch = default_branch or adapter.get_default_branch(repo)
                    adapter.create_pr(
                        repo,
                        title=issue.title,
                        body=pr_body or issue.body or "",
                        head=branch_name,
                        base=base_branch,
                    )
                    adapter.set_issue_labels(repo, issue.number, ["review"])
                    logger.info("Issue #%s: PR created, label set to review", issue.number)
                except GitPlatformError as e:
                    logger.warning("Failed to create PR or set labels: %s", e)
                # Switch back to default branch after PR creation
                try:
                    base_branch = default_branch or adapter.get_default_branch(repo)
                    checkout_branch(base_branch, repo_dir=repo_path, log=logger)
                    logger.info("Switched back to default branch: %s", base_branch)
                except Exception as e:
                    logger.warning("Failed to switch back to default branch: %s", e)
                return

            clarification = read_agent_clarification(repo_path, issue.number)
            if clarification:
                logger.info(
                    "Issue #%s: agent asked for clarification (in task file), posting to issue",
                    issue.number,
                )
                try:
                    adapter.create_comment(repo, issue.number, clarification)
                    adapter.set_issue_labels(repo, issue.number, ["stuck"])
                except GitPlatformError as e:
                    logger.warning("Failed to post clarification or set labels: %s", e)
                    return
                for c in comments:
                    if c.created_at and (last_comment_at is None or c.created_at > last_comment_at):
                        last_comment_at = c.created_at
                if last_comment_at is None:
                    last_comment_at = datetime.now(UTC)
                logger.info(
                    "Issue #%s: waiting for user reply (polling every %ss)",
                    issue.number,
                    poll_interval,
                )
                for _ in range(POLL_MAX_ITERATIONS):
                    time.sleep(poll_interval)
                    new_comments = adapter.get_issue_comments(repo, issue.number, since=last_comment_at)
                    user_comments = [c for c in new_comments if bot_username is None or c.author != bot_username]
                    if not user_comments:
                        continue
                    for c in user_comments:
                        if c.created_at and c.created_at > last_comment_at:
                            last_comment_at = c.created_at
                    logger.info("Issue #%s: new user comment(s), re-evaluating", issue.number)
                    break
                else:
                    logger.warning("Issue #%s: poll timeout waiting for user reply", issue.number)
                    return
                continue

            logger.warning(
                "Issue #%s: agent produced no PR report and no clarification in task file",
                issue.number,
            )
            return

        logger.info("Issue #%s: data insufficient, asking for clarification", issue.number)
        try:
            adapter.create_comment(repo, issue.number, result.clarification)
            adapter.set_issue_labels(repo, issue.number, ["stuck"])
        except GitPlatformError as e:
            logger.warning("Failed to post clarification or set labels: %s", e)
            return

        for c in comments:
            if c.created_at and (last_comment_at is None or c.created_at > last_comment_at):
                last_comment_at = c.created_at
        if last_comment_at is None:
            last_comment_at = datetime.now(UTC)

        logger.info("Issue #%s: waiting for user reply (polling every %ss)", issue.number, poll_interval)
        for _ in range(POLL_MAX_ITERATIONS):
            time.sleep(poll_interval)
            new_comments = adapter.get_issue_comments(repo, issue.number, since=last_comment_at)
            user_comments = [c for c in new_comments if bot_username is None or c.author != bot_username]
            if not user_comments:
                continue
            for c in user_comments:
                if c.created_at and c.created_at > last_comment_at:
                    last_comment_at = c.created_at
            logger.info("Issue #%s: new user comment(s), re-evaluating", issue.number)
            break
        else:
            logger.warning("Issue #%s: poll timeout waiting for user reply", issue.number)
            return
