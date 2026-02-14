# Dialog template: plan and confirmation

When the bot is assigned to an issue, it waits **idle_minutes** (default 10, env `BOT_IDLE_MINUTES`) with no changes in the issue. Then it runs the **planner agent**, which writes a short implementation plan **in the same language as the issue** and asks the user to confirm. The confirmation prompt and "work started" message are in English.

## Step 1: Plan request (after idle_minutes)

```markdown
## Plan

{plan from agent}

---
Does this approach work for you? Reply with **yes** / **go ahead** / **looks good** to start implementation.
```

## Step 2: User confirms

The system watches for new comments. If the user replies with an affirmative phrase (e.g. "yes", "да", "устраивает", "go ahead", "бери в работу"), the task is enqueued and the bot posts:

"Work on this task has started. The implementation will appear in a pull request."

## State and queue

- **Status** is stored in `.coddy/issues/{issue_number}.yaml` (pending_plan -> waiting_confirmation -> queued).
- **Queue** is in `.coddy/queue/pending/{issue_number}.md` (markdown, human-readable; worker processes and moves to done/failed).

For the full sequence (webhook assign -> state -> idle -> plan -> confirm -> queue), see [issue-flow.md](issue-flow.md).

## Configuration

- `bot.idle_minutes` (default 10) or env `BOT_IDLE_MINUTES` – minutes of inactivity before posting the plan.
- `bot.github_username` – required so the bot ignores its own comments and only reacts to user replies.
