"""Handle GitHub webhook events (PR merged, issues assigned, issue comment).

On PR merged runs git pull and exits for restart. On issue assigned
creates/updates issue file and sets status pending_plan (worker builds
plan). On user confirmation sets status queued.
"""

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from coddy.observer.adapters.github import GitHubAdapter
from coddy.observer.planner import is_affirmative_comment, on_user_confirmed
from coddy.services.git import GitRunnerError, run_git_pull
from coddy.services.store import (
    add_comment,
    add_review,
    add_review_comment,
    create_issue,
    delete_comment,
    load_issue,
    load_pr,
    save_issue,
    set_issue_state,
    set_issue_status,
    set_pr_status,
    set_pr_workflow_status,
    update_comment,
)


def _working_dir_from_config(config: Any) -> Path:
    """Resolve workspace path (sources and .coddy/) from config.

    Only bot.workspace_path is used.
    """
    workspace = getattr(config.bot, "workspace_path", ".") or "."
    if workspace == ".":
        return Path.cwd()
    return Path(workspace).resolve()


def _handle_pull_request_closed(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """On PR closed: set PR status (merged/closed) in .coddy/pull_requests/, then if merged pull and exit."""
    logger = log or logging.getLogger("coddy.observer.webhook.handlers")
    if payload.get("action") != "closed":
        return
    pull = payload.get("pull_request") or {}
    pr_number = pull.get("number")
    repo_payload = payload.get("repository") or {}
    repo_full_name = repo_payload.get("full_name") or ""
    if repo_full_name and repo_full_name != getattr(config.bot, "repository", ""):
        logger.debug("PR #%s: skipping PR closed - repository %s is not configured repo", pr_number, repo_full_name)
        return
    working_dir = Path(repo_dir) if repo_dir is not None else _working_dir_from_config(config)
    if pr_number is not None and repo_full_name:
        status = "merged" if pull.get("merged") else "rejected"
        set_pr_status(working_dir, int(pr_number), status, repo=repo_full_name)

    if not pull.get("merged"):
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("PR #%s: skipping PR merged - platform is not github", pr_number)
        return
    default_branch = getattr(config.bot, "default_branch", "main")
    try:
        run_git_pull(default_branch, repo_dir=working_dir, log=logger)
    except GitRunnerError as e:
        logger.warning("PR #%s: git pull failed - %s", pr_number, e)
        return
    logger.info("PR #%s: pulled origin/%s, exiting for restart", pr_number, default_branch)
    sys.exit(0)


def _handle_pull_request_draft_or_ready(
    config: Any,
    payload: Dict[str, Any],
    status: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """On pull_request converted_to_draft or ready_for_review: set PR status in store."""
    logger = log or logging.getLogger("coddy.observer.webhook.handlers")
    pull = payload.get("pull_request") or {}
    pr_number = pull.get("number")
    repo_payload = payload.get("repository") or {}
    repo_full_name = repo_payload.get("full_name") or ""
    if not repo_full_name or repo_full_name != getattr(config.bot, "repository", ""):
        return
    working_dir = Path(repo_dir) if repo_dir is not None else _working_dir_from_config(config)
    if pr_number is not None:
        set_pr_status(working_dir, int(pr_number), status, repo=repo_full_name)
        logger.info("PR #%s status -> %s", pr_number, status)


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
    """On comment: created -> append; edited -> update; deleted -> set deleted_at.
    If created + waiting_confirmation + affirmative -> on_user_confirmed."""
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
            if issue_file.status == "clarification_sent":
                set_issue_status(repo_dir, int(issue_number), "user_replied")
                log.info("Issue #%s user replied after clarification, status -> user_replied", issue_number)
        if issue_file and issue_file.status in ("waiting_confirmation", "waiting_go") and is_affirmative_comment(body):
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
    """Store all issue events; on action=assigned set status pending_plan when
    bot is assignee."""
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
                create_issue(
                    repo_dir,
                    int(issue_number),
                    repo,
                    title,
                    body,
                    author,
                    state="closed",
                )
            set_issue_state(repo_dir, int(issue_number), "closed")
            set_issue_status(repo_dir, int(issue_number), "closed")
            log.info("Issue #%s closed, state -> closed", issue_number)
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
    """When bot is in assignees, set status to pending_plan so worker builds
    the plan."""
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
    set_issue_status(repo_dir, int(issue_number), "pending_plan")
    log.info("Issue #%s assigned, status -> pending_plan (worker will build plan)", issue_number)


def _handle_pull_request_review(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path,
    log: logging.Logger,
) -> None:
    """On pull_request_review submitted: store review in PR file."""
    action = payload.get("action")
    if action != "submitted":
        return
    review_payload = payload.get("review") or {}
    pr_payload = payload.get("pull_request") or {}
    pr_number = pr_payload.get("number")
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        return
    if pr_number is None:
        return

    bot_username = getattr(config.bot, "username", None)
    user = review_payload.get("user") or {}
    author = user.get("login", "")
    if bot_username and author == bot_username:
        return

    review_id = review_payload.get("id")
    state = review_payload.get("state", "commented")
    body = review_payload.get("body") or ""
    ts = _parse_comment_timestamp(review_payload.get("submitted_at")) or int(datetime.now(UTC).timestamp())

    pr = load_pr(repo_dir, int(pr_number))
    if not pr:
        set_pr_status(repo_dir, int(pr_number), "open", repo=repo)

    add_review(
        repo_dir,
        int(pr_number),
        review_id=int(review_id) if review_id is not None else 0,
        author=author,
        state=state,
        body=body,
        created_at=ts,
    )
    set_pr_workflow_status(repo_dir, int(pr_number), "pending_plan")
    log.info(
        "PR #%s: review %s submitted by %s (state=%s), workflow_status -> pending_plan",
        pr_number,
        review_id,
        author,
        state,
    )


def _handle_pull_request_review_comment(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path,
    log: logging.Logger,
) -> None:
    """On pull_request_review_comment created/edited: store comment in PR
    file."""
    action = payload.get("action")
    if action not in ("created", "edited"):
        return
    comment_payload = payload.get("comment") or {}
    pr_payload = payload.get("pull_request") or {}
    pr_number = pr_payload.get("number")
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        return
    if pr_number is None:
        return

    bot_username = getattr(config.bot, "username", None)
    user = comment_payload.get("user") or {}
    author = user.get("login", "")
    if bot_username and author == bot_username:
        return

    comment_id = comment_payload.get("id")
    if comment_id is None:
        return

    review_id = comment_payload.get("pull_request_review_id")
    content = comment_payload.get("body") or ""
    path = comment_payload.get("path") or ""
    line = comment_payload.get("line")
    in_reply_to_id = comment_payload.get("in_reply_to_id")
    ts = _parse_comment_timestamp(comment_payload.get("created_at")) or int(datetime.now(UTC).timestamp())

    pr = load_pr(repo_dir, int(pr_number))
    if not pr:
        set_pr_status(repo_dir, int(pr_number), "open", repo=repo)

    add_review_comment(
        repo_dir,
        int(pr_number),
        review_id=int(review_id) if review_id is not None else None,
        comment_id=int(comment_id),
        author=author,
        content=content,
        path=path,
        line=line,
        created_at=ts,
        in_reply_to_id=int(in_reply_to_id) if in_reply_to_id is not None else None,
    )
    set_pr_workflow_status(repo_dir, int(pr_number), "pending_plan")
    log.info(
        "PR #%s: review comment %s on %s:%s by %s, workflow_status -> pending_plan",
        pr_number,
        comment_id,
        path,
        line,
        author,
    )


def _handle_pr_issue_comment(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path,
    log: logging.Logger,
) -> None:
    """Handle issue_comment on a PR (general PR comment, not line-level).

    If PR has workflow_status=waiting_confirmation and comment is
    affirmative, set workflow_status to in_progress.
    """
    action = payload.get("action")
    if action != "created":
        return
    comment_payload = payload.get("comment") or {}
    body = comment_payload.get("body") or ""
    user = comment_payload.get("user") or {}
    author = user.get("login", "")
    bot_username = getattr(config.bot, "username", None)
    if bot_username and author == bot_username:
        return

    issue_payload = payload.get("issue") or {}
    pr_number = issue_payload.get("number")
    if pr_number is None:
        return

    if not issue_payload.get("pull_request"):
        return

    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo or repo != getattr(config.bot, "repository", ""):
        return

    pr = load_pr(repo_dir, int(pr_number))
    if not pr:
        return

    if pr.workflow_status == "waiting_confirmation" and is_affirmative_comment(body):
        from coddy.services.store import set_pr_workflow_status

        set_pr_workflow_status(repo_dir, int(pr_number), "in_progress")
        log.info("PR #%s: user confirmed review plan, workflow_status -> in_progress", pr_number)


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
    - pull_request (action=converted_to_draft): set PR status to draft.
    - pull_request (action=ready_for_review): set PR status to open.
    - pull_request_review (action=submitted): store review in PR file.
    - pull_request_review_comment (action=created/edited): store line comment in PR file.
    - issues (action=assigned): if bot is in assignees, set status pending_plan (worker builds plan).
    - issue_comment: on user confirmation set issue status to queued; on PR comment check review confirmation.
    """
    logger = log or logging.getLogger("coddy.observer.webhook.handlers")
    work_dir = Path(repo_dir) if repo_dir is not None else _working_dir_from_config(config)

    if event == "pull_request":
        action = payload.get("action")
        if action == "closed":
            _handle_pull_request_closed(config, payload, repo_dir=work_dir, log=logger)
        elif action == "converted_to_draft":
            _handle_pull_request_draft_or_ready(config, payload, "draft", repo_dir=work_dir, log=logger)
        elif action == "ready_for_review":
            _handle_pull_request_draft_or_ready(config, payload, "open", repo_dir=work_dir, log=logger)
        return

    if event == "pull_request_review":
        _handle_pull_request_review(config, payload, work_dir, logger)
        return

    if event == "pull_request_review_comment":
        _handle_pull_request_review_comment(config, payload, work_dir, logger)
        return

    if event == "issues":
        _handle_issues(config, payload, work_dir, logger)
        return

    if event == "issue_comment":
        _handle_pr_issue_comment(config, payload, work_dir, logger)
        _handle_issue_comment(config, payload, work_dir, logger)
        return
