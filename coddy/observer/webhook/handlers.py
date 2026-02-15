"""Handle GitHub webhook events (PR merged, issues assigned, issue comment).

On PR merged runs git pull and exits for restart. On issue assigned
creates issue file and runs planner; on user confirmation sets status
queued.
"""

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from coddy.observer.adapters.github import GitHubAdapter
from coddy.observer.planner import is_affirmative_comment, on_user_confirmed, run_planner
from coddy.services.git import GitRunnerError, run_git_pull
from coddy.services.store import (
    add_comment,
    create_issue,
    delete_comment,
    load_issue,
    save_issue,
    set_issue_status,
    set_pr_status,
    update_comment,
)
from coddy.worker.agents.cursor_cli_agent import make_cursor_cli_agent


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


def _parse_comment_timestamp(iso_str: str | None) -> int | None:
    """Parse GitHub ISO date to Unix timestamp, or None if missing/invalid."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def _handle_issue_comment(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path,
    log: logging.Logger,
) -> None:
    """On comment: created -> append to store; edited -> update; deleted -> set deleted_at. If created + waiting_confirmation + affirmative -> on_user_confirmed."""
    action = payload.get("action")
    if action not in ("created", "edited", "deleted"):
        return
    comment_payload = payload.get("comment") or {}
    body = comment_payload.get("body") or ""
    user = comment_payload.get("user") or {}
    author = user.get("login", "")
    comment_id = comment_payload.get("comment_id") or comment_payload.get("id")
    bot_username = getattr(config.bot, "username", None)
    issue_payload = payload.get("issue") or {}
    issue_number = issue_payload.get("number")
    if issue_number is None:
        return
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        return
    issue_file = load_issue(repo_dir, int(issue_number))

    if action == "created":
        if bot_username and author == bot_username:
            return
        if issue_file:
            ts_created = _parse_comment_timestamp(comment_payload.get("created_at"))
            ts_updated = _parse_comment_timestamp(comment_payload.get("updated_at"))
            add_comment(
                repo_dir,
                int(issue_number),
                author,
                body,
                created_at=ts_created,
                updated_at=ts_updated,
                comment_id=int(comment_id) if comment_id is not None else None,
            )
            log.debug("Added comment to issue #%s from %s", issue_number, author)
        if issue_file and issue_file.status == "waiting_confirmation" and is_affirmative_comment(body):
            token = getattr(config, "github_token_resolved", None)
            if token:
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
            else:
                log.warning("No GitHub token; cannot post reply")
        return

    if action == "edited":
        if issue_file and comment_id is not None:
            ts_updated = _parse_comment_timestamp(comment_payload.get("updated_at"))
            if update_comment(repo_dir, int(issue_number), int(comment_id), body, updated_at=ts_updated):
                log.debug("Updated comment %s on issue #%s", comment_id, issue_number)
        return

    if action == "deleted":
        if issue_file and comment_id is not None:
            if delete_comment(repo_dir, int(issue_number), int(comment_id)):
                log.debug("Deleted comment %s on issue #%s", comment_id, issue_number)
        return


def _ensure_issue_in_store(config: Any, payload: Dict[str, Any], repo_dir: Path, log: logging.Logger) -> bool:
    """Create issue in store from payload if not present.

    Returns True if repo matches and issue stored.
    """
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        return False
    issue_payload = payload.get("issue") or {}
    issue_number = issue_payload.get("number")
    if issue_number is None:
        return False
    existing = load_issue(repo_dir, int(issue_number))
    if existing:
        return True
    title = issue_payload.get("title") or ""
    body = issue_payload.get("body") or ""
    user_payload = issue_payload.get("user") or {}
    author = user_payload.get("login") or "unknown"
    assignees = issue_payload.get("assignees") or []
    first_assignee = assignees[0].get("login") if assignees and isinstance(assignees[0], dict) else None
    now_ts = int(datetime.now(UTC).timestamp())
    assigned_at = now_ts if first_assignee else None
    assigned_to = first_assignee
    create_issue(
        repo_dir,
        int(issue_number),
        repo,
        title,
        body,
        author,
        assigned_at=assigned_at,
        assigned_to=assigned_to,
    )
    return True


def _handle_issues(config: Any, payload: Dict[str, Any], repo_dir: Path, log: logging.Logger) -> None:
    """Store all issue events; run planner only when action=assigned and
    assignee is bot."""
    action = payload.get("action")
    issue_payload = payload.get("issue") or {}
    issue_number = issue_payload.get("number")
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")

    if action == "closed":
        if issue_number is not None and repo and repo == getattr(config.bot, "repository", ""):
            if not load_issue(repo_dir, int(issue_number)):
                title = issue_payload.get("title") or ""
                body = issue_payload.get("body") or ""
                user_payload = issue_payload.get("user") or {}
                author = user_payload.get("login") or "unknown"
                create_issue(repo_dir, int(issue_number), repo, title, body, author)
            set_issue_status(repo_dir, int(issue_number), "closed")
            log.info("Issue #%s closed, status -> closed", issue_number)
        return
    if action == "edited":
        if issue_number is not None and repo and repo == getattr(config.bot, "repository", ""):
            issue_file = load_issue(repo_dir, int(issue_number))
            if issue_file:
                issue_file.title = issue_payload.get("title") or issue_file.title
                issue_file.description = issue_payload.get("body") or issue_file.description
                issue_file.updated_at = int(datetime.now(UTC).timestamp())
                save_issue(repo_dir, int(issue_number), issue_file)
                log.debug("Issue #%s updated (title/description)", issue_number)
        return
    if action == "unassigned":
        if issue_number is not None and repo and repo == getattr(config.bot, "repository", ""):
            issue_file = load_issue(repo_dir, int(issue_number))
            if issue_file:
                issue_file.assigned_at = None
                issue_file.assigned_to = None
                issue_file.updated_at = int(datetime.now(UTC).timestamp())
                save_issue(repo_dir, int(issue_number), issue_file)
                log.debug("Issue #%s unassigned, cleared assigned_at/assigned_to", issue_number)
        return
    if action in ("opened", "assigned"):
        _ensure_issue_in_store(config, payload, repo_dir, log)
        if action == "assigned":
            assignees = issue_payload.get("assignees") or []
            first_assignee = assignees[0].get("login") if assignees and isinstance(assignees[0], dict) else None
            if first_assignee and issue_number is not None and repo and repo == getattr(config.bot, "repository", ""):
                issue_file = load_issue(repo_dir, int(issue_number))
                if issue_file:
                    issue_file.assigned_at = int(datetime.now(UTC).timestamp())
                    issue_file.assigned_to = first_assignee
                    save_issue(repo_dir, int(issue_number), issue_file)
            _handle_issues_assigned(config, payload, repo_dir, log)


def _handle_issues_assigned(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path,
    log: logging.Logger,
) -> None:
    """Run planner only when bot is in assignees (issue already stored by
    _handle_issues)."""
    if payload.get("action") != "assigned":
        return
    issue_payload = payload.get("issue") or {}
    assignees = issue_payload.get("assignees") or []
    bot_username = getattr(config.bot, "username", None)
    if not bot_username:
        log.debug("Skipping work on issues.assigned: no bot username configured")
        return
    logins = [a.get("login") for a in assignees if isinstance(a, dict) and a.get("login")]
    if bot_username not in logins:
        log.debug("Skipping work on issues.assigned: assignee is not bot (%s)", bot_username)
        return
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        log.debug("Skipping issues.assigned: repository %s not configured", repo)
        return
    issue_number = issue_payload.get("number")
    if issue_number is None:
        return
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
