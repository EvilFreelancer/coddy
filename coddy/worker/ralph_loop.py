"""
Ralph-style development loop: run the AI agent repeatedly until PR report
or clarification.

Worker uses this for each queued issue. No polling for user reply - on
clarification we post and exit (task can be re-queued when user comments).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from coddy.observer.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.observer.models import Issue
from coddy.services.git import (
    branch_name_from_issue,
    checkout_branch,
    commit_all_and_push,
    fetch_and_checkout_branch,
    set_commit_author,
)
from coddy.services.store import save_pr, set_agent_clarification
from coddy.services.store.schemas import PRFile
from coddy.worker.agents.base import AIAgent
from coddy.worker.task_yaml import read_agent_clarification, read_pr_report

ResultKind = Literal["success", "clarification", "failed"]

DEFAULT_MAX_ITERATIONS = 10


def run_ralph_loop_for_issue(
    adapter: GitPlatformAdapter,
    agent: AIAgent,
    issue: Issue,
    repo: str,
    repo_dir: Path,
    *,
    bot_name: str | None = None,
    bot_email: str | None = None,
    bot_username: str | None = None,
    default_branch: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    log: logging.Logger | None = None,
) -> ResultKind:
    """
    Run the ralph loop for one issue: branch, sufficiency, then repeated
    agent runs until PR report file exists or clarification or max iterations.

    bot_name and bot_email are used as git commit author (user.name, user.email).
    Pass config.bot.name and config.bot.email from the worker so commits use
    the configured identity.

    Returns:
        "success" if PR was created; "clarification" if agent asked for
        clarification (posted to issue); "failed" otherwise.
    """
    logger = log or logging.getLogger("coddy.worker.ralph_loop")
    comments = adapter.get_issue_comments(repo, issue.number, since=None)
    result = agent.evaluate_sufficiency(issue, comments)

    if not result.sufficient:
        logger.info("Issue #%s: data insufficient, writing clarification to issue YAML", issue.number)
        bot_comment_name = f"@{bot_username}" if bot_username else "@bot"
        set_agent_clarification(repo_dir, issue.number, result.clarification, bot_name=bot_comment_name)
        return "clarification"

    branch_name = branch_name_from_issue(issue.number, issue.title)
    logger.info("Creating or reusing branch %s for issue #%s", branch_name, issue.number)

    try:
        adapter.create_branch(repo, branch_name, base_branch=default_branch)
    except GitPlatformError as e:
        err_msg = str(e).lower()
        if "already exists" in err_msg or "422" in err_msg:
            logger.info("Issue #%s: branch %s already exists, switching to it", issue.number, branch_name)
        else:
            logger.warning("Issue #%s: failed to create branch %s: %s", issue.number, branch_name, e)
            return "failed"

    try:
        fetch_and_checkout_branch(branch_name, repo_dir=repo_dir, log=logger)
    except Exception as e:
        logger.warning("Issue #%s: failed to checkout branch %s: %s", issue.number, branch_name, e)
        return "failed"

    if bot_name and bot_email:
        try:
            set_commit_author(bot_name, bot_email, repo_dir=repo_dir, log=logger)
        except Exception as e:
            logger.warning("Failed to set commit author: %s", e)

    try:
        adapter.set_issue_labels(repo, issue.number, ["in progress"])
    except GitPlatformError as e:
        logger.warning("Issue #%s: failed to set labels: %s", issue.number, e)

    for iteration in range(1, max_iterations + 1):
        if iteration > 1:
            logger.info(
                "Issue #%s: ralph iteration %s/%s (previous run produced no PR, e.g. timeout)",
                issue.number,
                iteration,
                max_iterations,
            )
        else:
            logger.info("Issue #%s: ralph iteration %s/%s", issue.number, iteration, max_iterations)
        issue = adapter.get_issue(repo, issue.number)
        comments = adapter.get_issue_comments(repo, issue.number, since=None)

        pr_body = agent.generate_code(issue, comments)

        if pr_body:
            if bot_name and bot_email:
                try:
                    commit_all_and_push(
                        branch_name,
                        f"#{issue.number} {issue.title}",
                        bot_name,
                        bot_email,
                        repo_dir=repo_dir,
                        log=logger,
                    )
                except Exception as e:
                    logger.warning("Issue #%s: failed to commit/push: %s", issue.number, e)
            try:
                base = default_branch or adapter.get_default_branch(repo)
                pr = adapter.create_pr(
                    repo,
                    title=issue.title,
                    body=pr_body or issue.body or "",
                    head=branch_name,
                    base=base,
                )
                adapter.set_issue_labels(repo, issue.number, ["review"])
                logger.info("Issue #%s: PR created, label set to review", issue.number)
                now = datetime.now(UTC).isoformat()
                pr_status = getattr(pr, "state", None)
                if not isinstance(pr_status, str):
                    pr_status = "open"
                pr_file = PRFile(
                    pr_id=getattr(pr, "number", 0),
                    repo=repo,
                    status=pr_status,
                    issue_id=issue.number,
                    created_at=now,
                    updated_at=now,
                )
                save_pr(repo_dir, pr_file)
                try:
                    checkout_branch(base, repo_dir=repo_dir, log=logger)
                    logger.info("Issue #%s: switched back to default branch: %s", issue.number, base)
                except Exception as e:
                    logger.warning("Issue #%s: failed to switch back to default branch: %s", issue.number, e)
                return "success"
            except GitPlatformError as e:
                logger.warning("Issue #%s: failed to create PR or set labels: %s", issue.number, e)
                try:
                    base = default_branch or adapter.get_default_branch(repo)
                    checkout_branch(base, repo_dir=repo_dir, log=logger)
                except Exception:
                    pass
                return "failed"

        clarification = read_agent_clarification(repo_dir, issue.number)
        if clarification:
            logger.info("Issue #%s: agent asked for clarification, writing to issue YAML", issue.number)
            bot_comment_name = f"@{bot_username}" if bot_username else "@bot"
            set_agent_clarification(repo_dir, issue.number, clarification, bot_name=bot_comment_name)
            try:
                base = default_branch or adapter.get_default_branch(repo)
                checkout_branch(base, repo_dir=repo_dir, log=logger)
            except Exception:
                pass
            return "clarification"

        report_body = read_pr_report(repo_dir, issue.number).strip()
        if report_body:
            if bot_name and bot_email:
                try:
                    commit_all_and_push(
                        branch_name,
                        f"#{issue.number} {issue.title}",
                        bot_name,
                        bot_email,
                        repo_dir=repo_dir,
                        log=logger,
                    )
                except Exception as e:
                    logger.warning("Issue #%s: failed to commit/push: %s", issue.number, e)
            try:
                base = default_branch or adapter.get_default_branch(repo)
                pr = adapter.create_pr(
                    repo,
                    title=issue.title,
                    body=report_body or issue.body or "",
                    head=branch_name,
                    base=base,
                )
                adapter.set_issue_labels(repo, issue.number, ["review"])
                logger.info("Issue #%s: PR created from report, label set to review", issue.number)
                now = datetime.now(UTC).isoformat()
                pr_status = getattr(pr, "state", None)
                if not isinstance(pr_status, str):
                    pr_status = "open"
                pr_file = PRFile(
                    pr_id=getattr(pr, "number", 0),
                    repo=repo,
                    status=pr_status,
                    issue_id=issue.number,
                    created_at=now,
                    updated_at=now,
                )
                save_pr(repo_dir, pr_file)
                checkout_branch(base, repo_dir=repo_dir, log=logger)
                return "success"
            except GitPlatformError as e:
                logger.warning("Issue #%s: failed to create PR or set labels: %s", issue.number, e)
                try:
                    base = default_branch or adapter.get_default_branch(repo)
                    checkout_branch(base, repo_dir=repo_dir, log=logger)
                except Exception:
                    pass
                return "failed"

    logger.warning("Issue #%s: max iterations (%s) reached without PR report", issue.number, max_iterations)
    try:
        base = default_branch or adapter.get_default_branch(repo)
        checkout_branch(base, repo_dir=repo_dir, log=logger)
    except Exception:
        pass
    return "failed"
