"""Scheduler: every interval, check pending_plan issues and run planner after idle_minutes."""

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger("coddy.scheduler")


def _parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def run_scheduler_loop(
    config: Any,
    repo_dir: Path,
    interval_seconds: int = 60,
) -> None:
    """Loop: every interval_seconds, find pending_plan older than idle_minutes and run planner."""
    log = logging.getLogger("coddy.scheduler")
    idle_minutes = getattr(config.bot, "idle_minutes", 10)
    token = getattr(config, "github_token_resolved", None)
    if not token or getattr(config.bot, "git_platform", "") != "github":
        return

    from coddy.adapters.github import GitHubAdapter
    from coddy.issue_store import list_pending_plan
    from coddy.services.planner import run_planner

    adapter = GitHubAdapter(token=token, api_url=getattr(config.github, "api_url", "https://api.github.com"))
    agent = _make_agent(config)
    repo = config.bot.repository
    bot_username = getattr(config.bot, "github_username", "") or ""

    while True:
        try:
            pending = list_pending_plan(repo_dir)
            now = datetime.now(UTC)
            for issue_number, issue_file in pending:
                assigned_at_str = issue_file.assigned_at
                if not assigned_at_str:
                    continue
                assigned_at = _parse_iso(assigned_at_str)
                if not assigned_at:
                    continue
                delta_minutes = (now - assigned_at).total_seconds() / 60
                if delta_minutes < idle_minutes:
                    continue
                try:
                    issue = adapter.get_issue(repo, issue_number)
                except Exception as e:
                    log.warning("Scheduler: failed to get issue #%s: %s", issue_number, e)
                    continue
                log.info("Scheduler: running planner for issue #%s (idle %.0f min)", issue_number, delta_minutes)
                run_planner(adapter, agent, issue, repo, repo_dir, bot_username=bot_username, log=log)
                # Only one per tick to avoid burst
                break
        except Exception as e:
            log.exception("Scheduler tick error: %s", e)
        time.sleep(interval_seconds)


def _make_agent(config: Any) -> Any:
    if getattr(config.bot, "ai_agent", "") == "cursor_cli" and getattr(config, "ai_agents", {}).get("cursor_cli"):
        from coddy.agents.cursor_cli_agent import make_cursor_cli_agent

        return make_cursor_cli_agent(config)
    from coddy.agents.stub_agent import StubAgent

    return StubAgent(min_body_length=0)


def start_scheduler_thread(config: Any, repo_dir: Path) -> threading.Thread:
    """Start scheduler in a daemon thread. Call after config and repo_dir are set."""
    interval = getattr(config.scheduler, "interval_seconds", 60)
    thread = threading.Thread(
        target=run_scheduler_loop,
        args=(config, repo_dir),
        kwargs={"interval_seconds": min(interval, 60)},
        daemon=True,
    )
    thread.start()
    return thread
