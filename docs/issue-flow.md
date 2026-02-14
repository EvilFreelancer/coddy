# Issue flow: from assignment to queue

This document describes how an issue gets from "bot assigned" to the task queue. Only issues where the bot is assigned are processed.

## 1. Webhook: bot assigned to issue

- **Event**: GitHub sends `issues` webhook with `action: assigned` and the bot in `assignees`.
- **Handler**: Daemon receives the webhook and calls the issues handler.
- **Action**: The issue is **not** put in the queue yet. Instead, a **state file** is created:
  - Path: `.coddy/state/{issue_number}.md`
  - Content: `state: pending_plan`, `repo`, `issue_number`, `title`, `assigned_at` (ISO timestamp).
- **Meaning**: The issue is in a "waiting" phase. The bot waits for comments or description updates; if there is no activity for **idle_minutes** (default 10, env `BOT_IDLE_MINUTES`), it proceeds to the next step.

## 2. Waiting for idle_minutes

- The daemon runs a **scheduler** (e.g. every 60 seconds).
- The scheduler lists all issues in state `pending_plan` (by reading `.coddy/state/*.md`).
- For each issue, it checks whether `assigned_at` is at least **idle_minutes** ago.
- If **no**: the scheduler skips this issue (no comments/updates yet, or not enough time passed).
- If **yes**: the scheduler runs the **planner** for this issue (one issue per tick) and stops.

*Note: The system does not currently reset the timer when the issue is updated or commented; the first check after idle_minutes have passed triggers the planner.*

## 3. Planner runs (after idle_minutes)

- The daemon fetches the issue via the Git platform API.
- The **planner agent** (e.g. Cursor CLI or stub) generates a short implementation plan in the **same language as the issue**.
- The daemon posts a comment on the issue:
  - The plan (from the agent).
  - A line asking the user to confirm (e.g. "Reply with **yes** / **go ahead** / **looks good** to start implementation").
- The state file is **updated**:
  - `state: waiting_confirmation`
  - Same path: `.coddy/state/{issue_number}.md` (other fields kept; `plan_posted_at` added).

## 4. User confirms (or does not)

- The daemon listens for **issue_comment** webhook events.
- If the comment is from the **bot**, it is ignored.
- If the issue is in state **waiting_confirmation** and the comment body is **affirmative** (e.g. "yes", "да", "устраивает", "go ahead", "бери в работу"), then:
  - A **task file** is created in the queue: `.coddy/queue/pending/{issue_number}.md` (markdown with `repo`, `issue_number`, `title`, `enqueued_at`).
  - The state file is **removed** (`.coddy/state/{issue_number}.md`).
  - The bot posts a comment: "Work on this task has started. The implementation will appear in a pull request."
- If the user does not confirm (or writes something else), the issue stays in `waiting_confirmation` until a later affirmative comment.

## 5. Worker picks from queue

- The **worker** (separate process) polls `.coddy/queue/pending/` and picks the next task (e.g. by smallest issue number).
- It runs the **ralph loop** for that issue (branch, agent, tests, commit, PR). See [system-specification.md](system-specification.md) and [dialog-template.md](dialog-template.md).

## Summary

| Step | Trigger              | Where it is stored / what happens                          |
|------|----------------------|------------------------------------------------------------|
| 1    | Webhook: assigned    | `.coddy/state/{N}.md` with `state: pending_plan`           |
| 2    | Scheduler (every N s)| Reads state; if `assigned_at` + idle_minutes passed -> run planner |
| 3    | Planner              | Post plan comment; state -> `waiting_confirmation`          |
| 4    | Webhook: comment "yes" | Create `.coddy/queue/pending/{N}.md`; delete state file; post "work started" |
| 5    | Worker               | Process queue; ralph loop; PR                              |

## Configuration

- **idle_minutes**: Minutes of no activity before the planner runs (config `bot.idle_minutes` or env `BOT_IDLE_MINUTES`, default 10).
- **bot.github_username**: Must be set so the bot ignores its own comments and only reacts to user replies.
- **Webhook**: Enable the **issue_comment** event in the GitHub webhook so user confirmations are received.

## Tests

- **Webhook**: `issues.assigned` with bot in assignees creates `.coddy/state/{issue_number}.md` with `pending_plan` (see `test_webhook_issues_assigned_creates_pending_plan_state_file`).
- **Webhook**: `issue_comment` with state `waiting_confirmation` and affirmative body creates `.coddy/queue/pending/{issue_number}.md` and removes the state file (see `test_webhook_issue_comment_affirmative_enqueues_and_clears_state`).
- **Scheduler**: When a `pending_plan` state has `assigned_at` older than `idle_minutes`, the planner is run once per tick (see `test_scheduler_runs_planner_when_pending_plan_older_than_idle_minutes`).
- **Scheduler**: When `assigned_at` is within `idle_minutes`, the planner is not called (see `test_scheduler_skips_pending_plan_when_not_idle_yet`).
