"""Review loop: process PR review comments using the AI agent.

For each unresolved review comment, the agent either applies a code fix
or writes a reply. Replies are posted back to the PR comment thread.
"""

import logging
from pathlib import Path
from typing import Literal

from coddy.observer.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.observer.models import ReviewComment
from coddy.services.git import (
    checkout_branch,
    commit_all_and_push,
    fetch_and_checkout_branch,
    set_commit_author,
)
from coddy.services.store.schemas import PRFile
from coddy.worker.agents.base import AIAgent
from coddy.worker.task_yaml import read_review_reply

ResultKind = Literal["success", "failed"]

LOG = logging.getLogger("coddy.worker.review_loop")


def run_review_loop_for_pr(
    adapter: GitPlatformAdapter,
    agent: AIAgent,
    pr_file: PRFile,
    repo: str,
    repo_dir: Path,
    *,
    bot_username: str | None = None,
    bot_name: str | None = None,
    bot_email: str | None = None,
    default_branch: str | None = None,
    log: logging.Logger | None = None,
) -> ResultKind:
    """Process all review comments on a PR.

    Checks out the PR branch, runs agent for each comment, commits
    changes, posts replies.
    """
    logger = log or LOG
    pr_number = pr_file.pr_id
    issue_number = pr_file.issue_id or 0

    review_comments: list[ReviewComment] = []
    for review in pr_file.reviews:
        for comment in review.comments:
            if comment.in_reply_to_id is not None:
                continue
            review_comments.append(
                ReviewComment(
                    id=comment.comment_id or 0,
                    body=comment.content,
                    author=comment.name,
                    path=comment.path,
                    line=comment.line,
                    side="RIGHT",
                    created_at=comment.created_at,
                    updated_at=comment.updated_at,
                )
            )

    if not review_comments:
        logger.info("PR #%s: no review comments to process", pr_number)
        return "success"

    try:
        pr = adapter.get_pr(repo, pr_number)
        head_branch = pr.head_branch
    except Exception as e:
        logger.warning("PR #%s: failed to get PR from platform: %s", pr_number, e)
        return "failed"

    try:
        fetch_and_checkout_branch(head_branch, repo_dir=repo_dir, log=logger)
    except Exception as e:
        logger.warning("PR #%s: failed to checkout branch %s: %s", pr_number, head_branch, e)
        return "failed"

    if bot_name and bot_email:
        set_commit_author(bot_name, bot_email, repo_dir=repo_dir, log=logger)

    for idx, comment in enumerate(review_comments, 1):
        logger.info(
            "PR #%s: processing review comment %d/%d on %s:%s",
            pr_number,
            idx,
            len(review_comments),
            comment.path,
            comment.line,
        )
        try:
            reply = agent.process_review_item(
                pr_number=pr_number,
                issue_number=issue_number,
                comments=review_comments,
                current_index=idx,
                repo_dir=repo_dir,
            )
        except Exception as e:
            logger.warning("PR #%s: agent failed for comment %d: %s", pr_number, idx, e)
            reply = None

        if reply is None:
            reply = read_review_reply(repo_dir, pr_number, comment.id)

        if reply and comment.id:
            try:
                adapter.reply_to_review_comment(repo, pr_number, comment.id, reply)
                logger.info("PR #%s: replied to comment %s", pr_number, comment.id)
            except GitPlatformError as e:
                logger.warning("PR #%s: failed to reply to comment %s: %s", pr_number, comment.id, e)

    try:
        commit_all_and_push(
            f"#{issue_number} Address review comments on PR #{pr_number}",
            repo_dir=repo_dir,
            log=logger,
        )
    except Exception as e:
        logger.warning("PR #%s: commit/push failed (no changes?): %s", pr_number, e)

    if default_branch:
        try:
            checkout_branch(default_branch, repo_dir=repo_dir, log=logger)
        except Exception:
            pass

    logger.info("PR #%s: review loop complete", pr_number)
    return "success"
