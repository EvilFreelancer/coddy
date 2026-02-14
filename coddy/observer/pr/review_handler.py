"""
Process PR review comments: build todo list, run agent per item, commit/push and reply.

When the user posts one or more review comments, Coddy creates a todo list,
checks out the PR branch, and for each item runs the agent. The agent may
apply code changes and/or write a reply. Coddy commits and pushes changes,
then posts the reply to the comment thread.
"""

import logging
import re
from pathlib import Path
from typing import List

from coddy.observer.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.observer.models import ReviewComment
from coddy.services.git import (
    commit_all_and_push,
    fetch_and_checkout_branch,
)
from coddy.worker.agents.base import AIAgent


def _issue_number_from_branch(branch_name: str) -> int | None:
    """Extract issue number from branch name (e.g. 42-add-feature -> 42).

    Returns None if branch does not match expected pattern.
    """
    match = re.match(r"^(\d+)[-\s]", branch_name)
    if match:
        return int(match.group(1))
    return None


def process_pr_review(
    adapter: GitPlatformAdapter,
    agent: AIAgent,
    repo: str,
    pr_number: int,
    review_comments: List[ReviewComment],
    repo_dir: Path | None = None,
    bot_name: str | None = None,
    bot_email: str | None = None,
    log: logging.Logger | None = None,
) -> None:
    """
    Process a list of PR review comments: todo list, agent per item, commit and reply.

    1. Fetch PR and checkout head branch.
    2. For each comment (in order): run agent for that item; commit and push if
       there are changes; post reply if the agent produced one.
    3. Replies are posted to the corresponding comment thread.
    """
    logger = log or logging.getLogger("coddy.observer.pr.review_handler")
    repo_path = Path(repo_dir) if repo_dir is not None else Path.cwd()

    if not review_comments:
        logger.info("PR #%s: no review comments to process", pr_number)
        return

    try:
        pr = adapter.get_pr(repo, pr_number)
    except GitPlatformError as e:
        logger.warning("PR #%s: failed to get PR: %s", pr_number, e)
        return

    if pr.state != "open":
        logger.info("PR #%s: not open (state=%s), skipping review", pr_number, pr.state)
        return

    branch_name = pr.head_branch
    issue_number = _issue_number_from_branch(branch_name) or pr_number

    try:
        fetch_and_checkout_branch(branch_name, repo_dir=repo_path, log=logger)
    except Exception as e:
        logger.warning("PR #%s: failed to checkout %s: %s", pr_number, branch_name, e)
        return

    for index, comment in enumerate(review_comments, 1):
        logger.info(
            "PR #%s: processing review item %s/%s (comment %s)",
            pr_number,
            index,
            len(review_comments),
            comment.id,
        )
        reply_text = agent.process_review_item(
            pr_number,
            issue_number,
            review_comments,
            index,
            repo_path,
        )

        if bot_name and bot_email:
            line_display = str(comment.line) if comment.line is not None else "?"
            commit_message = f"#{issue_number} Address review: {comment.path}:{line_display}"
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
                if "nothing to commit" not in str(e).lower() and "no changes" not in str(e).lower():
                    logger.warning("PR #%s: commit/push failed: %s", pr_number, e)

        if reply_text and reply_text.strip():
            try:
                adapter.reply_to_review_comment(repo, pr_number, comment.id, reply_text.strip())
                logger.info("PR #%s: replied to comment %s", pr_number, comment.id)
            except GitPlatformError as e:
                logger.warning("PR #%s: failed to reply to comment %s: %s", pr_number, comment.id, e)
