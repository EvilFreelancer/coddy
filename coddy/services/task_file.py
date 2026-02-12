"""Task and report files in .coddy/ for the agent.

We write a markdown task file (issue + comments); the agent executes it
and writes a PR description to a report file that we read for create_pr.
"""

from pathlib import Path
from typing import List

from coddy.models import Comment, Issue, ReviewComment

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
    """Write task markdown to .coddy/task-{issue_number}.md.

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


def read_agent_clarification(repo_dir: Path, issue_number: int) -> str | None:
    """Read agent clarification from .coddy/task-{issue_number}.md if present.

    If the agent appended a section "## Agent clarification request",
    returns its content (until the next ## or EOF). Returns None if file
    missing or section absent.
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
    """Read PR description from .coddy/pr-{issue_number}.md if present.

    Returns empty string if file is missing or unreadable.
    """
    path = report_file_path(repo_dir, issue_number)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# --- Review (PR review comments) task and reply files ---


def review_task_file_path(repo_dir: Path, pr_number: int) -> Path:
    """Path to the review task file for a PR (overwritten per item)."""
    return repo_dir / CODDY_DIR / f"review-{pr_number}.md"


def review_reply_file_path(repo_dir: Path, pr_number: int, comment_id: int) -> Path:
    """Path where the agent writes the reply text for a given review
    comment."""
    return repo_dir / CODDY_DIR / f"review-reply-{pr_number}-{comment_id}.md"


REVIEW_TASK_TEMPLATE = """# PR Review Feedback (PR #{pr_number}, Issue #{issue_number})

## Todo list (items to address)

{todo_list}

---

## Current item: {current_index} of {total}

**File:** `{path}`
**Line:** {line_display}
**Author:** {author}
**Comment:** {body}

---

Either:
1. **Apply a code change** to address this comment, then run linter/tests and commit
   with message like `#{issue_number} Address review: {path}:{line_display}`.
2. **Or only reply** (e.g. user asked a question): write your reply text to:
   {reply_path}

Write only the reply body (markdown allowed). Do not write code in the reply file.
After you are done with this item (code change and/or reply file), stop. Coddy will
commit, push, post the reply, and then run you again for the next item if any.
"""


def write_review_task_file(
    pr_number: int,
    issue_number: int,
    comments: List[ReviewComment],
    current_index: int,
    repo_dir: Path,
) -> Path:
    """Write the review task file for the current item (1-based index).

    The file contains the full todo list and the current item details.
    Agent writes reply to review_reply_file_path(repo_dir, pr_number,
    comment_id).
    """
    path = review_task_file_path(repo_dir, pr_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(comments)
    todo_lines = []
    for i, c in enumerate(comments, 1):
        line_display = str(c.line) if c.line is not None else "?"
        todo_lines.append(f"{i}. `{c.path}` line {line_display}: {c.body[:60]}{'...' if len(c.body) > 60 else ''}")
    todo_list = "\n".join(todo_lines)
    current = comments[current_index - 1]
    line_display = str(current.line) if current.line is not None else "?"
    reply_path = review_reply_file_path(repo_dir, pr_number, current.id)
    content = REVIEW_TASK_TEMPLATE.format(
        pr_number=pr_number,
        issue_number=issue_number,
        todo_list=todo_list,
        current_index=current_index,
        total=total,
        path=current.path,
        line_display=line_display,
        author=current.author,
        body=current.body,
        reply_path=reply_path,
    )
    path.write_text(content, encoding="utf-8")
    return path


def read_review_reply(repo_dir: Path, pr_number: int, comment_id: int) -> str | None:
    """Read the agent's reply for a review comment from the reply file.

    Returns None if file is missing or empty.
    """
    path = review_reply_file_path(repo_dir, pr_number, comment_id)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except Exception:
        return None
