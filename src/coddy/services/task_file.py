"""
Task and report files in .coddy/ for the agent.

We write a markdown task file (issue + comments); the agent executes it and writes
a PR description to a report file that we read for create_pr.
"""

from pathlib import Path
from typing import List

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
Follow project rules (.cursor/rules, docs). When finished, write a PR description to:
{report_path}

Include: What was done; How to test; Reference to issue #{number}.
Use markdown. Do not write code in the report file, only the PR description text.
"""


def task_file_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to task file for the issue."""
    return repo_dir / CODDY_DIR / f"task-{issue_number}.md"


def report_file_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to PR report file written by the agent."""
    return repo_dir / CODDY_DIR / f"pr-{issue_number}.md"


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
    report_path = report_file_path(repo_dir, issue.number)
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
