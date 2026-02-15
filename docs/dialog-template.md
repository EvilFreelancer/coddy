# Dialog template: plan and confirmation

When the bot is assigned to an issue (via webhook), the observer immediately runs the **planner agent**, which writes a short implementation plan **in the same language as the issue** and asks the user to confirm. The confirmation prompt and "work started" message are in English.

## Step 1: Plan request (on assignment)

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

- **Status** is stored in `.coddy/issues/{issue_number}.yaml` (pending_plan -> waiting_confirmation -> queued). Worker picks issues with status=queued.

For the full sequence (webhook assign -> plan -> confirm -> queue), see [issue-flow.md](issue-flow.md).

## Configuration

- `bot.username` – required so the bot ignores its own comments and only reacts to user replies.
- GitHub token – required for the observer to post the plan on assignment.
