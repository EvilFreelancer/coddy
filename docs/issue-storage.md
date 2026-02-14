# Issue storage (.coddy/issues/)

All issue data is stored in **YAML files** under `.coddy/issues/`, one file per issue: `{issue_number}.yaml`. No files are moved between folders; only the **status** field is updated. This acts as a simple database for the bot.

## File format

```yaml
author: @username
created_at: "2024-01-01T12:00:00+00:00"
updated_at: "2024-01-01T12:00:00+00:00"
status: pending_plan   # or waiting_confirmation, queued, in_progress, done, failed, closed
title: Issue title
description: >
  Multi-line issue body.

  Second paragraph.
repo: owner/repo
issue_number: 42
assigned_at: "2024-01-01T12:00:00+00:00"

comments:
  - name: @username
    content: |
      Title and description (first comment) or user comment.
    created_at: 1704110400
    updated_at: 1704110400
  - name: @botname
    content: Bot reply (e.g. plan or "work started").
    created_at: 1704110500
    updated_at: 1704110500
```

- **author**, **created_at**, **updated_at**: meta from the issue (ISO or unix).
- **status**: current state (pending_plan -> waiting_confirmation -> queued; worker may use in_progress, done, failed).
- **title**, **description**: issue title and body.
- **comments**: thread of comments; first entry is the issue content (title + description), then user comments and bot replies. Each has **name** (e.g. @user), **content**, **created_at** and **updated_at** (Unix timestamps).

## Pydantic models (store schemas)

- `coddy.observer.store.schemas.issue_comment.IssueComment`: name, content, created_at, updated_at (all required).
- `coddy.observer.store.schemas.issue_file.IssueFile`: author, created_at, updated_at, status, title, description, comments, repo, issue_number, assigned_at.

Re-exported from `coddy.observer.store` and `coddy.observer.issues`: `IssueComment`, `IssueFile`, `load_issue`, `save_issue`, `create_issue`, `add_message`, `set_status`, `list_queued`, `list_pending_plan`, `list_issues_by_status`.

## Converter: YAML to Markdown (for agent)

The coddy agent reads issue context as markdown. Use `coddy.utils.issue_to_markdown.issue_to_markdown(issue, issue_number)` to convert an `IssueFile` to a single markdown string:

- `# Issue N`, `## Title`, `## Description`, then `## Comments` with each comment as `### @name`, content, and created_at/updated_at.

Script usage (e.g. from repo root):

```python
from pathlib import Path
from coddy.observer.store import load_issue
from coddy.utils.issue_to_markdown import issue_to_markdown

repo_dir = Path(".")
issue = load_issue(repo_dir, 42)
if issue:
    md = issue_to_markdown(issue, 42)
    print(md)
```

Tests: `tests/test_issue_to_markdown.py`.

## Status flow

| status               | Meaning |
|----------------------|--------|
| pending_plan         | Bot assigned; planner will run (or failed to run). |
| waiting_confirmation | Plan posted; wait for user to confirm (yes/da). |
| queued               | User confirmed; worker will pick this task. |
| in_progress / done / failed | Set by worker. |
| closed               | Set when issue is closed (e.g. via webhook). |

PRs are stored in `.coddy/prs/{pr_number}.yaml` with status **open**, **merged**, or **closed** (updated on PR merge/close webhook).
