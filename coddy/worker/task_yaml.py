"""Task and PR report in .coddy/ as YAML files.

Task: .coddy/task-{issue_number}.yaml. Agent reads it and either writes
.coddy/pr-{issue_number}.yaml (body) or adds agent_clarification to the task YAML.
Review: .coddy/review-{pr}.yaml and .coddy/review-reply-{pr}-{comment_id}.yaml.
"""

from pathlib import Path
from typing import Any, List

import yaml

from coddy.observer.models import Comment, Issue, ReviewComment

CODDY_DIR = ".coddy"


def task_file_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to task YAML for the issue."""
    return repo_dir / CODDY_DIR / f"task-{issue_number}.yaml"


def report_file_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to PR report YAML written by the agent."""
    return repo_dir / CODDY_DIR / f"pr-{issue_number}.yaml"


def task_log_path(repo_dir: Path, issue_number: int) -> Path:
    """Path to agent run log file for the issue (headless mode)."""
    return repo_dir / CODDY_DIR / f"task-{issue_number}.log"


def write_task_file(
    issue: Issue,
    comments: List[Comment],
    repo_dir: Path,
) -> Path:
    """Write task YAML to .coddy/task-{issue_number}.yaml.

    Returns the path to the task file. Creates .coddy/ if needed.
    """
    path = task_file_path(repo_dir, issue.number)
    path.parent.mkdir(parents=True, exist_ok=True)
    report_path_relative = str(Path(CODDY_DIR) / f"pr-{issue.number}.yaml")
    comments_data = [{"author": c.author, "body": c.body} for c in sorted(comments, key=lambda x: x.created_at or x.id)]
    instructions = (
        "Follow project rules (.cursor/rules, docs).\n\n"
        "If the task description and comments do NOT contain enough information to implement "
        "(e.g. missing acceptance criteria, unclear scope), do NOT implement. Instead add "
        "the key 'agent_clarification' to this task YAML with your specific question(s). "
        "Then stop.\n\n"
        "If the task IS clear enough: implement it, run final verification (linter, tests), "
        "fix and repeat until all pass. As the last step, write the PR description to "
        f"{report_path_relative} with a 'body' key (markdown). Include: What was done; "
        f"How to test; Reference to issue #{issue.number}. Write the report file only after "
        "all other work and checks are complete."
    )
    data: dict[str, Any] = {
        "number": issue.number,
        "title": issue.title,
        "body": issue.body or "(no description)",
        "comments": comments_data,
        "report_path": report_path_relative,
        "instructions": instructions,
    }
    raw = yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(raw, encoding="utf-8")
    return path


def read_agent_clarification(repo_dir: Path, issue_number: int) -> str | None:
    """Read agent_clarification from .coddy/task-{issue_number}.yaml if
    present."""
    path = task_file_path(repo_dir, issue_number)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data or not isinstance(data, dict):
            return None
        return data.get("agent_clarification") or None
    except Exception:
        return None


def read_pr_report(repo_dir: Path, issue_number: int) -> str:
    """Read PR description from .coddy/pr-{issue_number}.yaml if present."""
    path = report_file_path(repo_dir, issue_number)
    if not path.is_file():
        return ""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data or not isinstance(data, dict):
            return ""
        return (data.get("body") or "").strip()
    except Exception:
        return ""


def review_task_file_path(repo_dir: Path, pr_number: int) -> Path:
    """Path to the review task YAML for a PR (overwritten per item)."""
    return repo_dir / CODDY_DIR / f"review-{pr_number}.yaml"


def review_reply_file_path(repo_dir: Path, pr_number: int, comment_id: int) -> Path:
    """Path where the agent writes the reply YAML for a given review
    comment."""
    return repo_dir / CODDY_DIR / f"review-reply-{pr_number}-{comment_id}.yaml"


def write_review_task_file(
    pr_number: int,
    issue_number: int,
    comments: List[ReviewComment],
    current_index: int,
    repo_dir: Path,
) -> Path:
    """Write the review task YAML for the current item (1-based index)."""
    path = review_task_file_path(repo_dir, pr_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(comments)
    todo_lines = []
    for i, c in enumerate(comments, 1):
        line_display = str(c.line) if c.line is not None else "?"
        todo_lines.append(f"{i}. `{c.path}` line {line_display}: {c.body[:60]}{'...' if len(c.body) > 60 else ''}")
    current = comments[current_index - 1]
    line_display = str(current.line) if current.line is not None else "?"
    reply_path = review_reply_file_path(repo_dir, pr_number, current.id)
    data: dict[str, Any] = {
        "pr_number": pr_number,
        "issue_number": issue_number,
        "todo_list": todo_lines,
        "current_index": current_index,
        "total": total,
        "current": {
            "path": current.path,
            "line": current.line,
            "line_display": line_display,
            "author": current.author,
            "body": current.body,
        },
        "reply_path": str(reply_path),
        "instructions": (
            "Either apply a code change to address this comment, then run linter/tests and commit "
            f"with message like #{issue_number} Address review: {current.path}:{line_display}. "
            f"Or only reply: write your reply to {reply_path} as YAML with key 'body'. Then stop."
        ),
    }
    raw = yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(raw, encoding="utf-8")
    return path


def read_review_reply(repo_dir: Path, pr_number: int, comment_id: int) -> str | None:
    """Read the agent's reply for a review comment from the reply YAML."""
    path = review_reply_file_path(repo_dir, pr_number, comment_id)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data or not isinstance(data, dict):
            text = path.read_text(encoding="utf-8").strip()
            return text or None
        return (data.get("body") or "").strip() or None
    except Exception:
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except Exception:
            return None
