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

messages:
  - name: @username
    content: |
      Title and description (first message) or user comment.
    timestamp: 1704110400
  - name: @botname
    content: Bot reply (e.g. plan or "work started").
    timestamp: 1704110500
```

- **author**, **created_at**, **updated_at**: meta from the issue.
- **status**: current state (pending_plan → waiting_confirmation → queued; worker may use in_progress, done, failed).
- **title**, **description**: issue title and body.
- **messages**: thread of messages; first entry is the issue content (title + description), then user comments and bot replies. Each has **name** (e.g. @user), **content**, **timestamp** (unix).

## Pydantic models

- `coddy.observer.issues.IssueMessage`: name, content, timestamp.
- `coddy.observer.issues.IssueFile`: author, created_at, updated_at, status, title, description, messages, repo, issue_number, assigned_at.

## Converter: YAML → Markdown (for agent)

The coddy agent reads issue context as markdown. Use `coddy.utils.issue_to_markdown.issue_to_markdown(issue, issue_number)` to convert an `IssueFile` to a single markdown string:

- `# Issue N`, `## Title`, `## Description`, then `## Messages` with each message as `### @name`, content, and timestamp.

Script usage (e.g. from repo root):

```python
from pathlib import Path
from coddy.observer.issues import load_issue
from coddy.utils.issue_to_markdown import issue_to_markdown

repo_dir = Path(".")
issue = load_issue(repo_dir, 42)
if issue:
    md = issue_to_markdown(issue, 42)
    print(md)
```

Tests: `tests/test_issue_to_markdown.py`.

## Status flow

| status              | Meaning |
|---------------------|--------|
| pending_plan        | Bot assigned; wait idle_minutes, then run planner. |
| waiting_confirmation| Plan posted; wait for user to confirm (yes/да). |
| queued              | User confirmed; worker will pick this task (or already in .coddy/queue/). |
| in_progress / done / failed | Set by worker. |
| closed | Set when issue is closed (e.g. via webhook). |

PRs are stored in `.coddy/prs/{pr_number}.yaml` with status **open**, **merged**, or **closed** (updated on PR merge/close webhook).
