"""Planner: generate plan, post template message, detect user confirmation.

The agent produces the plan in the same language as the issue. Bot's fixed
phrases (confirmation prompt, work started) are in English.
"""

import logging
import re
from pathlib import Path

from coddy.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.agents.base import AIAgent
from coddy.issue_store import add_message, set_status
from coddy.models import Issue
from coddy.queue import enqueue

LOG = logging.getLogger("coddy.planner")

# Phrases that mean user confirms (EN + RU accepted)
AFFIRMATIVE_PATTERNS = [
    r"\b(да|yes|устраивает|ок|ok|okay|go ahead|бери в работу|начинай|"
    r"подходит|согласен|согласна|looks good|good|принято)\b",
    r"^(да|yes|устраивает|ок|ok|go ahead|бери в работу|начинай)\.?$",
]
AFFIRMATIVE_RE = re.compile("|".join(AFFIRMATIVE_PATTERNS), re.IGNORECASE)

TEMPLATE_PLAN_REQUEST = """## Plan

{plan}

---
Does this approach work for you? Reply with **yes** / **go ahead** / **looks good** to start implementation."""

TEMPLATE_WORK_STARTED = "Work on this task has started. The implementation will appear in a pull request."


def format_plan_request(plan: str) -> str:
    """Format plan (in issue language) + confirmation prompt in English."""
    return TEMPLATE_PLAN_REQUEST.format(plan=plan)


def is_affirmative_comment(body: str) -> bool:
    """True if comment body indicates user confirmation (yes / да / etc.)."""
    if not body or not body.strip():
        return False
    return bool(AFFIRMATIVE_RE.search(body.strip()))


def run_planner(
    adapter: GitPlatformAdapter,
    agent: AIAgent,
    issue: Issue,
    repo: str,
    repo_dir: Path,
    bot_username: str = "",
    log: logging.Logger | None = None,
) -> None:
    """Generate plan (in issue language), post message, add to issue store, set status waiting_confirmation."""
    logger = log or LOG
    comments = adapter.get_issue_comments(repo, issue.number, since=None)
    plan = agent.generate_plan(issue, comments)
    message = format_plan_request(plan)
    try:
        adapter.create_comment(repo, issue.number, message)
    except GitPlatformError as e:
        logger.warning("Failed to post plan comment: %s", e)
        return
    name = f"@{bot_username}" if bot_username else "@bot"
    add_message(repo_dir, issue.number, name, message)
    set_status(repo_dir, issue.number, "waiting_confirmation")
    logger.info("Posted plan for issue #%s, waiting for user confirmation", issue.number)


def on_user_confirmed(
    adapter: GitPlatformAdapter,
    issue_number: int,
    repo: str,
    title: str,
    repo_dir: Path,
    comment_author: str,
    comment_body: str,
    bot_username: str = "",
    log: logging.Logger | None = None,
) -> None:
    """Add user comment to issue store, set status queued, enqueue for worker, post work started."""
    logger = log or LOG
    add_message(repo_dir, issue_number, f"@{comment_author}", comment_body)
    set_status(repo_dir, issue_number, "queued")
    enqueue(repo_dir, repo, issue_number, title=title)
    bot_name = f"@{bot_username}" if bot_username else "@bot"
    add_message(repo_dir, issue_number, bot_name, TEMPLATE_WORK_STARTED)
    message = TEMPLATE_WORK_STARTED
    try:
        adapter.create_comment(repo, issue_number, message)
    except GitPlatformError as e:
        logger.warning("Failed to post work started: %s", e)
    logger.info("Issue #%s confirmed, status queued and notified", issue_number)
