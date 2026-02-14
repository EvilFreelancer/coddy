# Issue flow: from assignment to queue

This document describes how an issue gets from "bot assigned" to the task queue. Only issues where the bot is assigned are processed.

## 1. Webhook: bot assigned to issue

- **Event**: GitHub sends `issues` webhook with `action: assigned` and the bot in `assignees`.
- **Handler**: Observer receives the webhook and calls the issues handler.
- **Action**: The issue is stored in `.coddy/issues/{issue_number}.yaml` with status **pending_plan**.
- **Meaning**: The issue is in a "waiting" phase. The bot waits for comments or description updates; if there is no activity for **idle_minutes** (default 10, env `BOT_IDLE_MINUTES`), it proceeds to the next step.

## 2. Waiting for idle_minutes

- The observer runs a **scheduler** (e.g. every 60 seconds).
- The scheduler lists issues with status **pending_plan** from `.coddy/issues/*.yaml` (via `list_pending_plan`).
- For each issue, it checks whether `assigned_at` is at least **idle_minutes** ago.
- If **no**: the scheduler skips this issue (no comments/updates yet, or not enough time passed).
- If **yes**: the scheduler runs the **planner** for this issue (one issue per tick) and stops.

*Note: The system does not currently reset the timer when the issue is updated or commented; the first check after idle_minutes have passed triggers the planner.*

## 3. Planner runs (after idle_minutes)

- The observer fetches the issue via the Git platform API.
- The **planner agent** (e.g. Cursor CLI or stub) generates a short implementation plan in the **same language as the issue**.
- The observer posts a comment on the issue:
  - The plan (from the agent).
  - A line asking the user to confirm (e.g. "Reply with **yes** / **go ahead** / **looks good** to start implementation").
- The issue status in `.coddy/issues/{issue_number}.yaml` is set to **waiting_confirmation**.

## 4. User confirms (or does not)

- The observer listens for **issue_comment** webhook events.
- If the comment is from the **bot**, it is ignored.
- If the issue has status **waiting_confirmation** and the comment body is **affirmative** (e.g. "yes", "да", "устраивает", "go ahead", "бери в работу"), then:
  - The issue status in `.coddy/issues/{issue_number}.yaml` is set to **queued** (worker picks from issues with status=queued).
  - The bot posts a comment: "Work on this task has started. The implementation will appear in a pull request."
- If the user does not confirm (or writes something else), the issue stays in `waiting_confirmation` until a later affirmative comment.

## 5. Worker picks from queue

- The **worker** (separate process, `coddy worker` or `python -m coddy.worker`) picks the next task from `.coddy/issues/` (issues with status=queued, smallest issue number first).
- It runs the **ralph loop** for that issue (branch, task YAML, agent loop until `.coddy/pr-{n}.yaml` or `agent_clarification`). See [system-specification.md](system-specification.md) and [dialog-template.md](dialog-template.md).

## Summary

| Step | Trigger              | Where it is stored / what happens                          |
|------|----------------------|------------------------------------------------------------|
| 1    | Webhook: assigned    | Observer creates `.coddy/issues/{N}.yaml` with status **pending_plan** |
| 2    | Scheduler (every N s)| List issues with status pending_plan; if `assigned_at` + idle_minutes passed -> run planner |
| 3    | Planner              | Post plan comment; issue status -> **waiting_confirmation** |
| 4    | Webhook: comment "yes" | Observer sets issue status to **queued** in `.coddy/issues/{N}.yaml`; post "work started" |
| 5    | Worker               | Pick queued issue from .coddy/issues/; ralph loop; set status done/failed; PR in .coddy/prs/ on merge/close |

## Configuration

- **idle_minutes**: Minutes of no activity before the planner runs (config `bot.idle_minutes` or env `BOT_IDLE_MINUTES`, default 10).
- **bot.github_username**: Must be set so the bot ignores its own comments and only reacts to user replies.
- **Webhook**: Enable the **issue_comment** event in the GitHub webhook so user confirmations are received.

## Tests

- **Webhook**: `issues.assigned` with bot in assignees creates `.coddy/issues/{issue_number}.yaml` with status **pending_plan** (see `test_webhook_issues_assigned_creates_issue_file`).
- **Webhook**: `issue_comment` with state `waiting_confirmation` and affirmative body sets issue status to **queued** in `.coddy/issues/` (see `test_webhook_issue_comment_affirmative_sets_queued`).
- **Scheduler**: When a `pending_plan` state has `assigned_at` older than `idle_minutes`, the planner is run once per tick (see `test_scheduler_runs_planner_when_pending_plan_older_than_idle_minutes`).
- **Scheduler**: When `assigned_at` is within `idle_minutes`, the planner is not called (see `test_scheduler_skips_pending_plan_when_not_idle_yet`).
