"""
Task and report files in .coddy/ for the agent.

We write a markdown task file (issue + comments); the agent executes it and writes
a PR description to a report file that we read for create_pr.
"""

from pathlib import Path
from typing import List, Optional

from coddy.models import Comment, Issue

CODDY_DIR = ".coddy"
TASK_TEMPLATE = """# Task (Issue #{number})

## Title
{title}

## Description
{body}

## Comments
{comments}

---
Follow project rules (.cursor/rules, docs).

If the task description and comments do NOT contain enough information to implement
(e.g. missing acceptance criteria, unclear scope), do NOT implement. Instead append
a new section at the end of this task file:

## Agent clarification request

Write your specific question(s) here (what is missing, what you need from the user).
Then stop; do not write the PR report file.

If the task IS clear enough to implement: implement it, run final verification
(linter, tests), fix and repeat until all pass. As the last step, write a PR
description to:
{report_path}

Include: What was done; How to test; Reference to issue #{number}.
Use markdown. Do not write code in the report file, only the PR description text.
Write the report file only after all other work and checks are complete.
"""


def task_file_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to task file for the issue."""
    return repo_dir / CODDY_DIR / f"task-{issue_number}.md"


def report_file_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to PR report file written by the agent."""
    return repo_dir / CODDY_DIR / f"pr-{issue_number}.md"


def task_log_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to agent run log file for the issue (headless mode)."""
    return repo_dir / CODDY_DIR / f"task-{issue_number}.log"


def write_task_file(
    issue: Issue,
    comments: List[Comment],
    repo_dir: Path,
) -> Path:
    """
    Write task markdown to .coddy/task-{issue_number}.md.

    Returns the path to the task file. Creates .coddy/ if needed.
    """
    path = task_file_path(repo_dir, issue.number)
    path.parent.mkdir(parents=True, exist_ok=True)
    report_path_relative = Path(CODDY_DIR) / f"pr-{issue.number}.md"
    comments_text = "\n\n".join(
        f"**{c.author}**: {c.body}" for c in sorted(comments, key=lambda x: x.created_at or x.id)
    )
    if not comments_text:
        comments_text = "(none)"
    content = TASK_TEMPLATE.format(
        number=issue.number,
        title=issue.title,
        body=issue.body or "(no description)",
        comments=comments_text,
        report_path=str(report_path_relative),
    )
    path.write_text(content, encoding="utf-8")
    return path


CLARIFICATION_HEADING = "## Agent clarification request"


def read_agent_clarification(repo_dir: Path, issue_number: int) -> Optional[str]:
    """
    Read agent clarification from .coddy/task-{issue_number}.md if present.

    If the agent appended a section "## Agent clarification request", returns its
    content (until the next ## or EOF). Returns None if file missing or section absent.
    """
    path = task_file_path(repo_dir, issue_number)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    if CLARIFICATION_HEADING not in text:
        return None
    start = text.index(CLARIFICATION_HEADING) + len(CLARIFICATION_HEADING)
    rest = text[start:].lstrip()
    # Take until next ## or end
    end = rest.find("\n## ")
    if end >= 0:
        rest = rest[:end]
    return rest.strip() or None


def read_pr_report(repo_dir: Path, issue_number: int) -> str:
    """
    Read PR description from .coddy/pr-{issue_number}.md if present.

    Returns empty string if file is missing or unreadable.
    """
    path = report_file_path(repo_dir, issue_number)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
