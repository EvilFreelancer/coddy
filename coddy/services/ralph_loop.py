"""
Ralph-style development loop: run the AI agent repeatedly until PR report
or clarification.

Worker uses this for each queued issue. No polling for user reply - on
clarification we post and exit (task can be re-queued when user comments).
"""

import logging
from pathlib import Path
from typing import Literal

from coddy.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.agents.base import AIAgent
from coddy.models import Issue
from coddy.services.git_runner import (
    branch_name_from_issue,
    checkout_branch,
    commit_all_and_push,
    fetch_and_checkout_branch,
)
from coddy.services.task_file import read_agent_clarification, read_pr_report

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
    default_branch: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    log: logging.Logger | None = None,
) -> ResultKind:
    """
    Run the ralph loop for one issue: branch, sufficiency, then repeated
    agent runs until PR report file exists or clarification or max iterations.

    Returns:
        "success" if PR was created; "clarification" if agent asked for
        clarification (posted to issue); "failed" otherwise.
    """
    logger = log or logging.getLogger("coddy.ralph_loop")
    comments = adapter.get_issue_comments(repo, issue.number, since=None)
    result = agent.evaluate_sufficiency(issue, comments)

    if not result.sufficient:
        logger.info("Issue #%s: data insufficient, posting clarification", issue.number)
        try:
            adapter.create_comment(repo, issue.number, result.clarification)
            adapter.set_issue_labels(repo, issue.number, ["stuck"])
        except GitPlatformError as e:
            logger.warning("Failed to post clarification or set labels: %s", e)
        return "clarification"

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
            return "failed"

    try:
        fetch_and_checkout_branch(branch_name, repo_dir=repo_dir, log=logger)
    except Exception as e:
        logger.warning("Failed to checkout branch %s: %s", branch_name, e)
        return "failed"

    try:
        adapter.set_issue_labels(repo, issue.number, ["in progress"])
    except GitPlatformError as e:
        logger.warning("Failed to set labels: %s", e)

    for iteration in range(1, max_iterations + 1):
        logger.info("Issue #%s: ralph iteration %s/%s", issue.number, iteration, max_iterations)
        # Refresh issue/comments in case of edits
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
                    logger.warning("Failed to commit/push: %s", e)
            try:
                base = default_branch or adapter.get_default_branch(repo)
                adapter.create_pr(
                    repo,
                    title=issue.title,
                    body=pr_body or issue.body or "",
                    head=branch_name,
                    base=base,
                )
                adapter.set_issue_labels(repo, issue.number, ["review"])
                logger.info("Issue #%s: PR created, label set to review", issue.number)
            except GitPlatformError as e:
                logger.warning("Failed to create PR or set labels: %s", e)
            try:
                base = default_branch or adapter.get_default_branch(repo)
                checkout_branch(base, repo_dir=repo_dir, log=logger)
                logger.info("Switched back to default branch: %s", base)
            except Exception as e:
                logger.warning("Failed to switch back to default branch: %s", e)
            return "success"

        clarification = read_agent_clarification(repo_dir, issue.number)
        if clarification:
            logger.info("Issue #%s: agent asked for clarification, posting to issue", issue.number)
            try:
                adapter.create_comment(repo, issue.number, clarification)
                adapter.set_issue_labels(repo, issue.number, ["stuck"])
            except GitPlatformError as e:
                logger.warning("Failed to post clarification or set labels: %s", e)
            try:
                base = default_branch or adapter.get_default_branch(repo)
                checkout_branch(base, repo_dir=repo_dir, log=logger)
            except Exception:
                pass
            return "clarification"

        # Check for PR report file written by agent without return value
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
                    logger.warning("Failed to commit/push: %s", e)
            try:
                base = default_branch or adapter.get_default_branch(repo)
                adapter.create_pr(
                    repo,
                    title=issue.title,
                    body=report_body or issue.body or "",
                    head=branch_name,
                    base=base,
                )
                adapter.set_issue_labels(repo, issue.number, ["review"])
                checkout_branch(base, repo_dir=repo_dir, log=logger)
            except GitPlatformError as e:
                logger.warning("Failed to create PR or switch branch: %s", e)
            return "success"

    logger.warning("Issue #%s: max iterations (%s) reached without PR report", issue.number, max_iterations)
    try:
        base = default_branch or adapter.get_default_branch(repo)
        checkout_branch(base, repo_dir=repo_dir, log=logger)
    except Exception:
        pass
    return "failed"
