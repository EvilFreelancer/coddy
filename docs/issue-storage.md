# Issue and PR storage (.coddy/issues/, .coddy/pull_requests/)

Issue and PR data is stored as **YAML files** under `.coddy/`. Status is represented by **folder placement**, not only by a field in the file.

## Layout

- **Issues**: `.coddy/issues/open/{issue_number}.yaml` and `.coddy/issues/closed/{issue_number}.yaml`
  - The folder reflects platform state (open vs closed). Workflow status (pending_plan, queued, etc.) is stored in the YAML `status` field.
- **PRs**: `.coddy/pull_requests/open/{pr_number}.yaml`, `.coddy/pull_requests/merged/{pr_number}.yaml`, `.coddy/pull_requests/rejected/{pr_number}.yaml`
  - The folder reflects PR status: open, merged, or rejected (closed without merge). A `status` field may still be present in YAML for convenience.

When status changes (e.g. issue closed, PR merged), the file is **moved** to the correct folder. On **observer startup**, an optional sync fetches issues and PRs from the platform API and writes/updates these files.

## Issue file format

```yaml
author: @username
created_at: "2024-01-01T12:00:00+00:00"
updated_at: "2024-01-01T12:00:00+00:00"
status: pending_plan   # workflow: pending_plan, waiting_confirmation, queued, in_progress, done, failed, closed
state: open            # platform state: open or closed (matches folder)
title: Issue title
description: >
  Multi-line issue body.

  Second paragraph.
repo: owner/repo
issue_id: 42
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
- **state**: platform state - `open` or `closed`; must match the folder (`open/` or `closed/`).
- **status**: workflow state (pending_plan, waiting_confirmation, queued, in_progress, waiting_user_reply, clarification_sent, user_replied, waiting_go, done, failed, closed). See [code-agent-flow.md](code-agent-flow.md).
- **title**, **description**: issue title and body.
- **comments**: thread of comments; first entry is the issue content (title + description), then user comments and bot replies. Each has **name** (e.g. @user), **content**, **created_at**, **updated_at** (Unix timestamps). When the agent asks for clarification it adds a bot comment and sets status to `waiting_user_reply`; the observer posts the **last comment** to the platform and sets issue status to `clarification_sent` (comment + status identify what was sent).

## Pydantic models (store schemas)

- `coddy.services.store.schemas.issue_comment.IssueComment`: name, content, created_at, updated_at; optional deleted_at.
- `coddy.services.store.schemas.issue_file.IssueFile`: author, created_at, updated_at, state, status, title, description, comments, repo, issue_id, assigned_at.

Re-exported from `coddy.services.store`: `IssueComment`, `IssueFile`, `load_issue`, `save_issue`, `create_issue`, `add_comment`, `set_issue_status`, `set_issue_state`, `list_queued`, `list_pending_plan`, `list_issues_by_status`.

## PR storage

PRs are stored in `.coddy/pull_requests/{open|merged|rejected}/{pr_number}.yaml`. The folder denotes the status. On PR merge (webhook), the file is moved to `merged/`; on PR close without merge, to `rejected/`. Schema: `PRFile` (pr_id, repo, status, issue_id, created_at, updated_at).

## Sync on startup

When `observer.sync_on_startup` is true, the observer at startup:

1. Calls the platform adapter to list issues (open and closed) and pull requests (open, closed with merged_at, closed without merge).
2. Writes or updates YAML files in the correct folders (`.coddy/issues/open/`, `.coddy/issues/closed/`, `.coddy/pull_requests/open/`, `.coddy/pull_requests/merged/`, `.coddy/pull_requests/rejected/`).

Existing local workflow status for issues is preserved when updating from API (e.g. if the issue file already exists with status=queued, sync only updates meta/title/description/state folder, not status).

## Markdown rendering

Both `IssueFile` and `PRFile` have a **`to_markdown() -> str`** method that returns a formatted markdown string.

- **IssueFile.to_markdown()**: Renders title, description, and comments thread. Uses `issue_id` for the header when set.
- **PRFile.to_markdown()**: Renders PR id, repo, status, linked issue (if any), created/updated timestamps.

**Issue format:** `# Issue N`, `## Title`, `## Description`, then `## Comments` with each comment as `### @name`, content, and created_at/updated_at.

**PR format:** `# PR #N`, **Repo**, **Status**, **Linked issue** (if any), **Created**, **Updated**.

Script usage (e.g. from repo root):

```python
from pathlib import Path
from coddy.services.store import load_issue

repo_dir = Path(".")
issue = load_issue(repo_dir, 42)
if issue:
    print(issue.to_markdown())
```

Script: `scripts/issue_to_markdown.py`. Markdown rendering is covered in `tests/test_services_store.py` (TestIssueFileSchema, TestPRFileSchema).

## Status flow (issues)

| status               | Meaning |
|----------------------|--------|
| pending_plan         | Bot assigned; planner will run (or failed to run; optional stable delay). |
| waiting_confirmation | Plan posted; wait for user to confirm (yes/da). |
| queued               | User confirmed; worker will pick this task. |
| in_progress          | Worker is running the agent. |
| waiting_user_reply   | Agent wrote clarification to YAML; observer should post to platform. |
| clarification_sent   | Clarification posted; waiting for user reply. |
| user_replied         | User replied; worker should re-evaluate and maybe post "proceed?". |
| waiting_go           | Worker posted "proceed?"; waiting for user to say go. |
| done / failed        | Set by worker. |
| closed               | Set when issue is closed (e.g. via webhook); file lives in `closed/`. |

Full flow: [code-agent-flow.md](code-agent-flow.md).
