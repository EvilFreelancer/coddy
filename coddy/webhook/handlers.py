"""Handle GitHub webhook events (e.g. PR review comment, PR merged).

Parses payload and delegates to services (review handler) or runs git
pull and restarts on PR merged.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from coddy.models import ReviewComment


def _parse_review_comment_from_payload(comment_payload: Dict[str, Any]) -> ReviewComment | None:
    """Build ReviewComment from GitHub webhook comment object."""
    try:
        cid = comment_payload.get("id")
        if cid is None:
            return None
        body = comment_payload.get("body") or ""
        user = comment_payload.get("user") or {}
        author = user.get("login", "")
        path = comment_payload.get("path") or ""
        line = comment_payload.get("line")
        side = comment_payload.get("side", "RIGHT")
        created = comment_payload.get("created_at")
        updated = comment_payload.get("updated_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        else:
            created = datetime.now()
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        in_reply_to_id = comment_payload.get("in_reply_to_id")
        return ReviewComment(
            id=int(cid),
            body=body,
            author=author,
            path=path,
            line=int(line) if line is not None else None,
            side=side,
            created_at=created,
            updated_at=updated,
            in_reply_to_id=int(in_reply_to_id) if in_reply_to_id is not None else None,
        )
    except (TypeError, ValueError) as e:
        logging.getLogger("coddy.webhook.handlers").warning("Failed to parse review comment: %s", e)
        return None


def _working_dir_from_config(config: Any) -> Path:
    """Resolve bot working directory (repo root) from config."""
    if config.ai_agents and "cursor_cli" in config.ai_agents:
        wd = getattr(config.ai_agents["cursor_cli"], "working_directory", None)
        if wd:
            return Path(wd)
    return Path.cwd()


def _handle_pr_merged(
    config: Any,
    payload: Dict[str, Any],
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> None:
    """On PR merged: pull from default branch then exit 0 so supervisor can restart."""
    logger = log or logging.getLogger("coddy.webhook.handlers")
    if payload.get("action") != "closed":
        return
    pull = payload.get("pull_request") or {}
    if not pull.get("merged"):
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("Skipping PR merged: platform is not github")
        return
    repo_payload = payload.get("repository") or {}
    repo_full_name = repo_payload.get("full_name") or ""
    if repo_full_name and repo_full_name != getattr(config.bot, "repository", ""):
        logger.debug("Skipping PR merged: repository %s is not configured repo", repo_full_name)
        return
    working_dir = Path(repo_dir) if repo_dir is not None else _working_dir_from_config(config)
    default_branch = getattr(config.bot, "default_branch", "main")
    from coddy.services.git_runner import GitRunnerError, run_git_pull

    try:
        run_git_pull(default_branch, repo_dir=working_dir, log=logger)
    except GitRunnerError as e:
        logger.warning("PR merged: git pull failed - %s", e)
        return
    logger.info("PR merged: pulled origin/%s, exiting for restart", default_branch)
    sys.exit(0)


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
    - pull_request_review_comment (action=created): run review handler for the new comment.
    """
    logger = log or logging.getLogger("coddy.webhook.handlers")

    if event == "pull_request":
        _handle_pr_merged(config, payload, repo_dir=repo_dir, log=logger)
        return

    if event != "pull_request_review_comment":
        return
    if payload.get("action") != "created":
        return
    comment_payload = payload.get("comment")
    if not comment_payload:
        logger.warning("pull_request_review_comment payload missing 'comment'")
        return
    review_comment = _parse_review_comment_from_payload(comment_payload)
    if not review_comment:
        return
    pull = payload.get("pull_request") or {}
    pr_number = pull.get("number")
    if pr_number is None:
        logger.warning("pull_request_review_comment payload missing pull_request.number")
        return
    repo_payload = payload.get("repository") or {}
    repo = repo_payload.get("full_name") or getattr(config.bot, "repository", "")
    if not repo:
        logger.warning("Could not determine repository from payload or config")
        return

    token = getattr(config, "github_token_resolved", None)
    if not token:
        logger.warning("No GitHub token; cannot process review comment")
        return
    if getattr(config.bot, "git_platform", "") != "github":
        logger.debug("Skipping review comment: platform is not github")
        return

    from coddy.adapters.github import GitHubAdapter
    from coddy.services.review_handler import process_pr_review

    adapter = GitHubAdapter(
        token=token,
        api_url=getattr(config.github, "api_url", "https://api.github.com"),
    )
    agent = _make_agent_from_config(config)
    repo_path = Path(repo_dir) if repo_dir is not None else Path.cwd()
    working_dir = repo_path
    if config.ai_agents and "cursor_cli" in config.ai_agents:
        wd = getattr(config.ai_agents["cursor_cli"], "working_directory", None)
        if wd:
            working_dir = Path(wd)
    process_pr_review(
        adapter,
        agent,
        repo,
        int(pr_number),
        [review_comment],
        repo_dir=working_dir,
        bot_name=getattr(config.bot, "name", None),
        bot_email=getattr(config.bot, "email", None),
        log=logger,
    )


def _make_agent_from_config(config: Any) -> Any:
    """Build AI agent from config (same logic as main._make_agent)."""
    if getattr(config.bot, "ai_agent", "") == "cursor_cli" and getattr(config, "ai_agents", {}).get("cursor_cli"):
        from coddy.agents.cursor_cli_agent import make_cursor_cli_agent

        return make_cursor_cli_agent(config)
    from coddy.agents.stub_agent import StubAgent

    return StubAgent(min_body_length=0)
