"""Handle GitHub webhook events (PR merged, issues assigned, issue comment).

On PR merged runs git pull and exits for restart. On issue assigned
creates issue file and runs planner; on user confirmation sets status queued.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict

from coddy.observer.adapters.github import GitHubAdapter
from coddy.observer.planner import is_affirmative_comment, on_user_confirmed, run_planner
from coddy.services.git import GitRunnerError, run_git_pull
from coddy.worker.agents.cursor_cli_agent import make_cursor_cli_agent
from coddy.services.store import (
    create_issue,
    load_issue,
    set_issue_status,
    set_pr_status,
)


def _working_dir_from_config(config: Any) -> Path:
    """Resolve workspace path (sources and .coddy/) from config."""
    workspace = getattr(config.bot, "workspace", ".") or "."
    if workspace != ".":
        return Path(workspace).resolve()
    if config.ai_agents and "cursor_cli" in config.ai_agents:
        wd = getattr(config.ai_agents["cursor_cli"], "working_directory", None)
        if wd:
            return Path(wd).resolve()
    return Path.cwd()


def _handle_pull_request_closed(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """On PR closed: set PR status (merged/closed) in .coddy/prs/, then if merged pull and exit."""
    logger = log or logging.getLogger("coddy.observer.webhook.handlers")
    if payload.get("action") != "closed":
        return
    pull = payload.get("pull_request") or {}
    pr_number = pull.get("number")
    repo_payload = payload.get("repository") or {}
    repo_full_name = repo_payload.get("full_name") or ""
    if repo_full_name and repo_full_name != getattr(config.bot, "repository", ""):
        logger.debug("Skipping PR closed: repository %s is not configured repo", repo_full_name)
        return
    working_dir = Path(repo_dir) if repo_dir is not None else _working_dir_from_config(config)
    if pr_number is not None and repo_full_name:
        status = "merged" if pull.get("merged") else "closed"
        set_pr_status(working_dir, int(pr_number), status, repo=repo_full_name)

    if not pull.get("merged"):
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("Skipping PR merged: platform is not github")
        return
    default_branch = getattr(config.bot, "default_branch", "main")
    try:
        run_git_pull(default_branch, repo_dir=working_dir, log=logger)
    except GitRunnerError as e:
        logger.warning("PR merged: git pull failed - %s", e)
        return
    logger.info("PR merged: pulled origin/%s, exiting for restart", default_branch)
    sys.exit(0)


def _handle_issue_comment(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path,
    log: logging.Logger,
) -> None:
    """On new comment: if issue is waiting_confirmation and user says yes, set queued and post work started."""
    if payload.get("action") != "created":
        return
    comment_payload = payload.get("comment") or {}
    body = comment_payload.get("body") or ""
    user = comment_payload.get("user") or {}
    author = user.get("login", "")
    bot_username = getattr(config.bot, "github_username", None)
    if bot_username and author == bot_username:
        return
    issue_payload = payload.get("issue") or {}
    issue_number = issue_payload.get("number")
    if issue_number is None:
        return
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        return
    issue_file = load_issue(repo_dir, int(issue_number))
    if not issue_file or issue_file.status != "waiting_confirmation":
        return
    if not is_affirmative_comment(body):
        return
    token = getattr(config, "github_token_resolved", None)
    if not token:
        log.warning("No GitHub token; cannot post reply")
        return
    adapter = GitHubAdapter(
        token=token,
        api_url=getattr(config.github, "api_url", "https://api.github.com"),
    )
    on_user_confirmed(
        adapter,
        int(issue_number),
        repo,
        issue_file.title or "",
        repo_dir,
        comment_author=author,
        comment_body=body,
        bot_username=bot_username or "",
        log=log,
    )


def _handle_issues(config: Any, payload: Dict[str, Any], repo_dir: Path, log: logging.Logger) -> None:
    """Dispatch issues event: assigned -> create issue; closed -> set issue status closed."""
    action = payload.get("action")
    if action == "closed":
        issue_payload = payload.get("issue") or {}
        issue_number = issue_payload.get("number")
        if issue_number is not None:
            issue_file = load_issue(repo_dir, int(issue_number))
            if issue_file:
                set_issue_status(repo_dir, int(issue_number), "closed")
                log.info("Issue #%s closed, status -> closed", issue_number)
        return
    if action == "assigned":
        _handle_issues_assigned(config, payload, repo_dir, log)


def _handle_issues_assigned(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path,
    log: logging.Logger,
) -> None:
    """On issue assigned: if bot is in assignees, create issue and run planner (post plan, waiting_confirmation)."""
    if payload.get("action") != "assigned":
        return
    issue_payload = payload.get("issue") or {}
    assignees = issue_payload.get("assignees") or []
    bot_username = getattr(config.bot, "github_username", None)
    if not bot_username:
        log.debug("Skipping issues.assigned: no bot github_username configured")
        return
    logins = [a.get("login") for a in assignees if isinstance(a, dict) and a.get("login")]
    if bot_username not in logins:
        return
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        log.debug("Skipping issues.assigned: repository %s not configured", repo)
        return
    issue_number = issue_payload.get("number")
    title = issue_payload.get("title") or ""
    if issue_number is None:
        return
    user_payload = issue_payload.get("user") or {}
    author = user_payload.get("login") or "unknown"
    body = issue_payload.get("body") or ""
    create_issue(
        repo_dir,
        int(issue_number),
        repo,
        title,
        body,
        author,
    )
    token = getattr(config, "github_token_resolved", None)
    if token and getattr(config.bot, "git_platform", "") == "github":
        try:
            adapter = GitHubAdapter(
                token=token,
                api_url=getattr(config.github, "api_url", "https://api.github.com"),
            )
            issue = adapter.get_issue(repo, int(issue_number))
            agent = make_cursor_cli_agent(config)
            run_planner(
                adapter,
                agent,
                issue,
                repo,
                repo_dir,
                bot_username=bot_username,
                log=log,
            )
        except Exception as e:
            log.exception("Failed to run planner for issue #%s: %s", issue_number, e)
    else:
        log.info(
            "Issue #%s assigned, status pending_plan (no token or not github; plan not posted)",
            issue_number,
        )


def handle_github_event(
    config: Any,
    event: str,
    payload: Dict[str, Any],
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """Handle a GitHub webhook event.

    Supported events:
    - pull_request (action=closed, merged=true): git pull from default branch, then exit 0 to allow restart.
    - issues (action=assigned): if bot is in assignees, enqueue task for worker.
    - issue_comment: on user confirmation set issue status to queued.
    """
    logger = log or logging.getLogger("coddy.observer.webhook.handlers")
    work_dir = Path(repo_dir) if repo_dir is not None else _working_dir_from_config(config)

    if event == "pull_request":
        _handle_pull_request_closed(config, payload, repo_dir=work_dir, log=logger)
        return

    if event == "issues":
        _handle_issues(config, payload, work_dir, logger)
        return

    if event == "issue_comment":
        _handle_issue_comment(config, payload, work_dir, logger)
        return
