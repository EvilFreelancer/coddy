"""Planner: generate plan, post template message, detect user confirmation.

The agent produces the plan in the same language as the issue. Bot's fixed
phrases (confirmation prompt, work started) are in English.
"""

import logging
import re
from pathlib import Path

from coddy.observer.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.observer.models import Issue
from coddy.services.store import add_comment, set_issue_status
from coddy.worker.agents.base import AIAgent

LOG = logging.getLogger("coddy.observer.planner")

# Phrases that mean user confirms (EN + RU accepted)
AFFIRMATIVE_PATTERNS = [
    r"\b(да|yes|устраивает|ок|ok|okay|go ahead|go|бери в работу|начинай|поехали|"
    r"подходит|согласен|согласна|looks good|good|принято)\b",
    r"^(да|yes|устраивает|ок|ok|go ahead|go|бери в работу|начинай|поехали)\.?$",
]
AFFIRMATIVE_RE = re.compile("|".join(AFFIRMATIVE_PATTERNS), re.IGNORECASE)

TEMPLATE_PLAN_REQUEST = """## Plan

{plan}

---
Does this approach work for you? Reply with **yes** / **go ahead** / **looks good** to start implementation."""

# When plan generation fails (agent error, missing node, etc.)
TEMPLATE_PLAN_ERROR = (
    "A worker error occurred while generating the plan. Please check the server logs or try again later."
)

TEMPLATE_WORK_STARTED = "Work on this task has started. The implementation will appear in a pull request."

# When worker re-evaluates after user reply and data is sufficient
TEMPLATE_PROCEED_REQUEST = (
    "Data is sufficient. Shall I proceed with implementation? "
    "Reply with **yes** / **go ahead** / **поехали** to start."
)


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
    """Generate plan (in issue language), post message, add to issue store, set
    status waiting_confirmation.

    On agent error, log it and post a short error message.
    """
    logger = log or LOG
    comments = adapter.get_issue_comments(repo, issue.number, since=None)
    plan = agent.generate_plan(issue, comments)
    if plan is None:
        logger.warning("Plan generation failed for issue #%s, posting error message", issue.number)
        message = TEMPLATE_PLAN_ERROR
    else:
        message = format_plan_request(plan)
    try:
        adapter.create_comment(repo, issue.number, message)
    except GitPlatformError as e:
        logger.warning("Failed to post plan comment: %s", e)
        return
    name = f"@{bot_username}" if bot_username else "@bot"
    add_comment(repo_dir, issue.number, name, message)
    set_issue_status(repo_dir, issue.number, "waiting_confirmation")
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
    """Add user comment to issue store, set status queued (worker picks from
    .coddy/issues/), post work started."""
    logger = log or LOG
    add_comment(repo_dir, issue_number, f"@{comment_author}", comment_body)
    set_issue_status(repo_dir, issue_number, "queued")
    bot_name = f"@{bot_username}" if bot_username else "@bot"
    add_comment(repo_dir, issue_number, bot_name, TEMPLATE_WORK_STARTED)
    message = TEMPLATE_WORK_STARTED
    try:
        adapter.create_comment(repo, issue_number, message)
    except GitPlatformError as e:
        logger.warning("Failed to post work started: %s", e)
    logger.info("Issue #%s confirmed, status queued and notified", issue_number)
