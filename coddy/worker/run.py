"""
Coddy worker: daemon watching .coddy/issues/ and .coddy/pull_requests/.

Processes user_replied (evaluate sufficiency, post "proceed?" or write clarification),
then queued (run ralph loop with agent). Uses adapter and agent when configured.
"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List, Tuple

import yaml

from coddy.config import AppConfig, LoggingConfig, load_config
from coddy.logging import CoddyLogging
from coddy.observer.models import Comment, Issue
from coddy.services.store import (
    IssueFile,
    PRFile,
    add_comment,
    list_issues_by_status,
    list_pending_plan,
    list_prs_by_workflow_status,
    list_queued,
    set_agent_clarification,
    set_issue_status,
    set_pr_workflow_status,
)
from coddy.worker.ralph_loop import run_ralph_loop_for_issue
from coddy.worker.review_loop import run_review_loop_for_pr
from coddy.worker.task_yaml import report_file_path


def _issue_file_to_issue_and_comments(issue_number: int, issue_file: IssueFile) -> Tuple[Issue, List[Comment]]:
    """Build Issue and Comment list from IssueFile for
    agent.evaluate_sufficiency."""
    created = datetime.fromtimestamp(issue_file.created_at, tz=UTC)
    updated = datetime.fromtimestamp(issue_file.updated_at, tz=UTC)
    issue = Issue(
        number=issue_number,
        title=issue_file.title or "",
        body=issue_file.description or "",
        author=issue_file.author or "",
        labels=[],
        state="open",
        created_at=created,
        updated_at=updated,
    )
    comments: List[Comment] = []
    for c in issue_file.comments:
        comments.append(
            Comment(
                id=c.comment_id or 0,
                body=c.content or "",
                author=c.name.lstrip("@") if c.name else "",
                created_at=datetime.fromtimestamp(c.created_at, tz=UTC),
                updated_at=datetime.fromtimestamp(c.updated_at, tz=UTC),
            )
        )
    return issue, comments


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the worker."""
    parser = argparse.ArgumentParser(
        prog="coddy worker",
        description="Coddy worker - dry run stub (read issues, write empty PR YAML)",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.yaml"),
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one task then exit",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=None,
        help="Seconds between .coddy/issues/ poll runs (default from config worker.poll_interval_seconds or 15)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only load and validate config, then exit",
    )
    return parser.parse_args(argv)


def _filter_by_assignment(
    items: list[tuple[int, IssueFile]], assignment_only: bool, bot_username: str | None
) -> list[tuple[int, IssueFile]]:
    """Filter to issues assigned to bot when assignment_only is True."""
    if not assignment_only:
        return items
    if not bot_username:
        return []
    return [(n, i) for n, i in items if i.assigned_to == bot_username]


def run_worker_poll(
    config: AppConfig,
    repo_dir: Path,
    adapter: Any,
    agent: Any,
    log: logging.Logger,
) -> bool:
    """One pass over .coddy/issues/: drain pending_plan, drain user_replied,
    then one queued.

    Returns True if any work was done.
    """
    repo = config.bot.repository
    assignment_only = getattr(config.bot, "assignment_only", True)
    bot_username = getattr(config.bot, "username", None)
    default_branch = getattr(config.bot, "default_branch", "main")
    did_work = False

    while True:
        pending_plan = _filter_by_assignment(list_pending_plan(repo_dir), assignment_only, bot_username)
        if not pending_plan or not agent:
            break
        pending_plan.sort(key=lambda t: t[0])
        issue_number, issue_file = pending_plan[0]
        issue, comments = _issue_file_to_issue_and_comments(issue_number, issue_file)
        from coddy.observer.planner import TEMPLATE_PLAN_ERROR, format_plan_request

        plan = agent.generate_plan(issue, comments)
        message = format_plan_request(plan) if plan else TEMPLATE_PLAN_ERROR
        bot_name = f"@{bot_username}" if bot_username else "@bot"
        add_comment(repo_dir, issue_number, bot_name, message)
        set_issue_status(repo_dir, issue_number, "plan_ready")
        log.info("Issue #%s: plan written to YAML, status -> plan_ready", issue_number)
        did_work = True

    while True:
        user_replied = _filter_by_assignment(
            list_issues_by_status(repo_dir, "user_replied"), assignment_only, bot_username
        )
        if not user_replied or not adapter or not agent:
            break
        user_replied.sort(key=lambda t: t[0])
        issue_number, issue_file = user_replied[0]
        issue, comments = _issue_file_to_issue_and_comments(issue_number, issue_file)
        result = agent.evaluate_sufficiency(issue, comments)
        if result.sufficient:
            from coddy.observer.planner import TEMPLATE_PROCEED_REQUEST

            msg = TEMPLATE_PROCEED_REQUEST
            try:
                adapter.create_comment(repo, issue_number, msg)
                bot_name = f"@{bot_username}" if bot_username else "@bot"
                add_comment(repo_dir, issue_number, bot_name, msg)
                set_issue_status(repo_dir, issue_number, "waiting_go")
                log.info("Issue #%s: data sufficient, posted proceed request, status -> waiting_go", issue_number)
            except Exception as e:
                log.warning("Failed to post proceed request for #%s: %s", issue_number, e)
        else:
            bot_comment_name = f"@{bot_username}" if bot_username else "@bot"
            set_agent_clarification(repo_dir, issue_number, result.clarification, bot_name=bot_comment_name)
            log.info("Issue #%s: data insufficient, wrote clarification to YAML", issue_number)
        did_work = True

    queued = _filter_by_assignment(list_queued(repo_dir), assignment_only, bot_username)
    if not did_work and queued:
        queued.sort(key=lambda t: t[0])
        issue_number, _ = queued[0]
        if adapter and agent:
            try:
                platform_issue = adapter.get_issue(repo, issue_number)
                comments = adapter.get_issue_comments(repo, issue_number, since=None)
                set_issue_status(repo_dir, issue_number, "in_progress")
                result_kind = run_ralph_loop_for_issue(
                    adapter,
                    agent,
                    platform_issue,
                    repo,
                    repo_dir,
                    bot_name=getattr(config.bot, "name", None),
                    bot_email=getattr(config.bot, "email", None),
                    bot_username=bot_username,
                    default_branch=default_branch,
                    log=log,
                )
                if result_kind == "success":
                    set_issue_status(repo_dir, issue_number, "done")
                elif result_kind == "clarification":
                    pass
                else:
                    set_issue_status(repo_dir, issue_number, "failed")
            except Exception as e:
                log.exception("Ralph loop failed for #%s: %s", issue_number, e)
                set_issue_status(repo_dir, issue_number, "failed")
        else:
            log.info("Dry run: processing issue #%s", issue_number)
            report_path = report_file_path(repo_dir, issue_number)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            body = "# Dry run\n\nNo agent configured; worker wrote empty PR YAML."
            report_path.write_text(
                yaml.dump({"body": body}, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            set_issue_status(repo_dir, issue_number, "done")
            log.info("Dry run: wrote empty PR YAML for issue #%s", issue_number)
        did_work = True

    if not did_work:
        did_work = _process_pr_reviews(config, repo_dir, adapter, agent, log)

    return did_work


def _process_pr_reviews(
    config: AppConfig,
    repo_dir: Path,
    adapter: Any,
    agent: Any,
    log: logging.Logger,
) -> bool:
    """Process PRs with workflow_status=pending_plan or in_progress.

    pending_plan: generate review response plan, post as PR comment, set waiting_confirmation.
    in_progress: run review loop (apply fixes via agent), set idle.
    """
    repo = config.bot.repository
    bot_username = getattr(config.bot, "username", None)
    did_work = False

    pending = list_prs_by_workflow_status(repo_dir, "pending_plan")
    for pr_id, pr_file in pending:
        if not adapter or not agent:
            break
        try:
            review_comments = _collect_review_comments(pr_file)
            if not review_comments:
                set_pr_workflow_status(repo_dir, pr_id, "idle")
                continue
            plan = _build_review_plan(review_comments)
            confirmation_msg = (
                f"## Review response plan\n\n{plan}\n\n---\n\n"
                "Does this look good? Reply with **yes** / **go ahead** to start applying fixes."
            )
            try:
                adapter.create_pr_comment(repo, pr_id, confirmation_msg)
            except Exception as e:
                log.warning("PR #%s: failed to post review plan: %s", pr_id, e)
            set_pr_workflow_status(repo_dir, pr_id, "waiting_confirmation")
            log.info("PR #%s: posted review response plan, workflow_status -> waiting_confirmation", pr_id)
            did_work = True
        except Exception as e:
            log.warning("PR #%s: review plan failed: %s", pr_id, e)

    in_progress = list_prs_by_workflow_status(repo_dir, "in_progress")
    for pr_id, pr_file in in_progress:
        if not adapter or not agent:
            break
        try:
            result = run_review_loop_for_pr(
                adapter=adapter,
                agent=agent,
                pr_file=pr_file,
                repo=repo,
                repo_dir=repo_dir,
                bot_username=bot_username,
                bot_name=getattr(config.bot, "name", None),
                bot_email=getattr(config.bot, "email", None),
                default_branch=getattr(config.bot, "default_branch", "main"),
                log=log,
            )
            if result == "success":
                set_pr_workflow_status(repo_dir, pr_id, "idle")
                log.info("PR #%s: review fixes applied, workflow_status -> idle", pr_id)
            else:
                set_pr_workflow_status(repo_dir, pr_id, "idle")
                log.warning("PR #%s: review loop result=%s, workflow_status -> idle", pr_id, result)
            did_work = True
        except Exception as e:
            log.exception("PR #%s: review loop failed: %s", pr_id, e)
            set_pr_workflow_status(repo_dir, pr_id, "idle")

    return did_work


def _collect_review_comments(pr_file: PRFile) -> list[dict[str, Any]]:
    """Extract all review comments with file/line info from a PR file."""
    items: list[dict[str, Any]] = []
    for review in pr_file.reviews:
        for comment in review.comments:
            if comment.in_reply_to_id is not None:
                continue
            items.append(
                {
                    "comment_id": comment.comment_id,
                    "author": comment.name,
                    "body": comment.content,
                    "path": comment.path,
                    "line": comment.line,
                    "review_id": review.review_id,
                }
            )
    return items


def _build_review_plan(review_comments: list[dict[str, Any]]) -> str:
    """Build a markdown plan summarizing review comments to address."""
    lines = []
    for i, item in enumerate(review_comments, 1):
        line_display = str(item["line"]) if item.get("line") is not None else "file-level"
        body_preview = item["body"][:80] + ("..." if len(item["body"]) > 80 else "")
        lines.append(f"{i}. `{item['path']}` line {line_display} (@{item['author']}): {body_preview}")
    return "\n".join(lines)


def run_worker(config: AppConfig, once: bool = False, poll_interval: int = 15) -> None:
    """Daemon: poll .coddy/issues/ every poll_interval seconds; process pending_plan, user_replied, queued."""
    CoddyLogging(config.logging).setup()
    log = logging.getLogger("coddy.worker")

    # Only bot.workspace_path is used for .coddy/issues/ (same as observer).
    workspace = getattr(config.bot, "workspace_path", ".") or "."
    repo_dir = Path(workspace).resolve()
    if (repo_dir / ".secrets").exists():
        log.warning(
            "Workspace contains .secrets/ - tokens may be visible to anyone with access to the workspace. "
            "Use a workspace path that does not contain .secrets/ (see docs/docker-and-secrets.md)."
        )

    repo = config.bot.repository
    assignment_only = getattr(config.bot, "assignment_only", True)
    bot_username = getattr(config.bot, "username", None)
    token = getattr(config, "github_token_resolved", None)

    adapter = None
    agent = None
    if token and getattr(config.bot, "git_platform", "") == "github":
        from coddy.observer.adapters.github import GitHubAdapter

        adapter = GitHubAdapter(token=token, api_url=getattr(config.github, "api_url", "https://api.github.com"))
        selected_agent = getattr(config.bot, "ai_agent", "acp")
        if selected_agent == "acp":
            from coddy.worker.agents.acp_agent import make_acp_agent

            agent = make_acp_agent(config)

    log.info(
        "Coddy worker started | repo=%s | workspace=%s | once=%s | assignment_only=%s | agent=%s",
        repo,
        repo_dir,
        once,
        assignment_only,
        "yes" if agent else "no",
    )
    log.info("Worker poll started (interval=%ss)", poll_interval)

    while True:
        if assignment_only and not bot_username:
            log.warning("assignment_only is True but bot username is not set; skipping issues. Set BOT_USERNAME.")
            if once:
                return
            time.sleep(poll_interval)
            continue

        try:
            did_work = run_worker_poll(config, repo_dir, adapter, agent, log)
        except Exception as e:
            log.warning("Worker poll error: %s", e)
            did_work = False

        if once:
            return
        if not did_work:
            time.sleep(poll_interval)


def main(argv: list[str] | None = None) -> int:
    """Entry point for coddy worker."""
    args = parse_args(argv)
    config_path = args.config
    if not config_path.is_file() and config_path == Path("config.yaml"):
        if Path("config.example.yaml").is_file():
            config_path = Path("config.example.yaml")
            CoddyLogging(LoggingConfig()).setup()
            logging.getLogger("coddy.worker").warning("config.yaml not found, using config.example.yaml")

    config = load_config(config_path)

    if args.check:
        print("Config OK:", config.bot.repository, config.bot.git_platform)
        return 0

    poll_interval = (
        args.poll_interval if args.poll_interval is not None else getattr(config.worker, "poll_interval_seconds", 15)
    )
    try:
        run_worker(
            config,
            once=args.once,
            poll_interval=poll_interval,
        )
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logging.getLogger("coddy.worker").exception("Fatal error: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
