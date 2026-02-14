# Issue flow: from assignment to queue

This document describes how an issue gets from "bot assigned" to the task queue. Only issues where the bot is assigned are processed. All triggers are via **webhooks** (no polling).

## 1. Webhook: bot assigned to issue

- **Event**: GitHub sends `issues` webhook with `action: assigned` and the bot in `assignees`.
- **Handler**: Observer receives the webhook and:
  - Stores the issue in `.coddy/issues/{issue_number}.yaml` with status **pending_plan**.
  - Immediately runs the **planner** (if GitHub token is configured): fetches issue via API, generates plan, posts comment, sets status to **waiting_confirmation**.
- If no token or planner fails, the issue stays **pending_plan** (plan is not posted).

## 2. Planner runs (on assignment)

- The observer fetches the issue via the Git platform API.
- The **planner agent** (e.g. Cursor CLI) generates a short implementation plan in the **same language as the issue**.
- The observer posts a comment on the issue:
  - The plan (from the agent).
  - A line asking the user to confirm (e.g. "Reply with **yes** / **go ahead** / **looks good** to start implementation").
- The issue status in `.coddy/issues/{issue_number}.yaml` is set to **waiting_confirmation**.

## 3. User confirms (or does not)

- The observer listens for **issue_comment** webhook events.
- If the comment is from the **bot**, it is ignored.
- If the issue has status **waiting_confirmation** and the comment body is **affirmative** (e.g. "yes", "да", "устраивает", "go ahead", "бери в работу"), then:
  - The issue status in `.coddy/issues/{issue_number}.yaml` is set to **queued** (worker picks from issues with status=queued).
  - The bot posts a comment: "Work on this task has started. The implementation will appear in a pull request."
- If the user does not confirm (or writes something else), the issue stays in `waiting_confirmation` until a later affirmative comment.

## 4. Worker picks from queue

- The **worker** (separate process, `coddy worker` or `python -m coddy.worker`) picks the next task from `.coddy/issues/` (issues with status=queued, smallest issue number first).
- It runs the **ralph loop** for that issue (branch, task YAML, agent loop until `.coddy/pr-{n}.yaml` or `agent_clarification`). See [system-specification.md](system-specification.md) and [dialog-template.md](dialog-template.md).

## Summary

| Step | Trigger              | Where it is stored / what happens                          |
|------|----------------------|------------------------------------------------------------|
| 1    | Webhook: assigned    | Observer creates `.coddy/issues/{N}.yaml`, runs planner, status -> **waiting_confirmation** |
| 2    | Webhook: comment "yes" | Observer sets issue status to **queued** in `.coddy/issues/{N}.yaml`; post "work started" |
| 3    | Worker               | Pick queued issue from .coddy/issues/; ralph loop; set status done/failed; PR in .coddy/prs/ on merge/close |

## Configuration

- **bot.github_username**: Must be set so the bot ignores its own comments and only reacts to user replies.
- **GITHUB_TOKEN**: Required for the observer to run the planner on assignment (fetch issue, post plan).
- **Webhook**: Enable **issues** and **issue_comment** events in the GitHub webhook so assignments and user confirmations are received.

## Tests

- **Webhook**: `issues.assigned` with bot in assignees creates `.coddy/issues/{issue_number}.yaml` (see `test_webhook_issues_assigned_creates_issue_file`). Without token, status stays **pending_plan**.
- **Webhook**: `issues.assigned` with token runs planner and status becomes **waiting_confirmation** (see `test_webhook_issues_assigned_runs_planner_when_token_set`).
- **Webhook**: `issue_comment` with state `waiting_confirmation` and affirmative body sets issue status to **queued** (see `test_webhook_issue_comment_affirmative_sets_queued`).
