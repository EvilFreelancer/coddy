# Code agent flow: planning, clarification, and run

This document describes how the code agent is started, how it can ask the user for clarification (via the issue YAML and observer), and how the worker runs as a daemon watching `.coddy/issues/` and `.coddy/prs/`.

## Roles

- **Observer**: Webhook server + optional poll of `.coddy/issues/`. Receives platform events; when the agent writes a clarification question into an issue YAML, the observer posts it to the issue and marks it as sent. On user comments it updates the issue file and status.
- **Worker**: Daemon that watches `.coddy/issues/` (and `.coddy/prs/`). Handles issues in status `user_replied` (evaluate sufficiency, post "proceed?" and set `waiting_go`), then picks `queued` issues and runs the ralph loop (code agent). When the agent needs clarification it writes to the issue YAML; the observer then posts that to the platform.

## Trigger: when the agent builds the plan

- When an issue is **assigned to the bot** and (optionally) has been **unchanged for some time** (`issue_stable_seconds`), the observer runs the **planner**: the code agent builds a detailed but concise work plan.
- If `issue_stable_seconds` is 0 (default), the plan is run immediately on assignment. If > 0, the observer only runs the planner for issues with `status=pending_plan`, `assigned_to=bot`, and `updated_at` older than `now - issue_stable_seconds`.

## Status flow (extended)

| status               | Meaning |
|----------------------|--------|
| pending_plan         | Assigned; planner will run (after stable delay if configured). |
| waiting_confirmation | Plan posted; waiting for user to confirm (yes / go ahead). |
| queued               | User confirmed; worker will run the ralph loop. |
| in_progress          | Worker is running the agent. |
| waiting_user_reply   | Agent wrote a clarification question to the issue YAML; observer should post it to the platform. |
| clarification_sent   | Observer posted the question; waiting for user reply. |
| user_replied         | User replied after clarification; worker should re-evaluate and possibly post "proceed?". |
| waiting_go           | Worker posted "Data sufficient, shall I proceed?"; waiting for user to say go (e.g. "поехали"). |
| done / failed / closed | Terminal states. |

## Clarification flow (agent asks, user answers)

1. **Agent needs clarification**  
   During the ralph loop (or before starting), the agent adds a **bot comment** to the issue (with its role/name and the question text) and sets `status: waiting_user_reply` and `updated_at`. Everything is stored in the **comments** thread; no separate clarification fields.

2. **Observer** (polling `.coddy/issues/`) sees an issue with `status=waiting_user_reply`. It:
   - Posts the **last comment**'s content to the issue (platform API).
   - Sets `status: clarification_sent` (and `updated_at`).

3. **User replies** in the issue. Observer receives `issue_comment` webhook:
   - Appends the comment to the issue YAML.
   - Sets `status: user_replied`.

4. **Worker** (polling `.coddy/issues/`) sees `status=user_replied`:
   - Loads issue and comments, runs sufficiency check.
   - If **sufficient**: Posts a comment like "Data is sufficient. Shall I proceed?" to the issue (and adds it to the issue YAML), sets `status: waiting_go`.
   - If **insufficient**: Adds another bot comment with the clarification and sets `status: waiting_user_reply` (another round).

5. **User says "go"** (e.g. "поехали", "yes", "go ahead"). Observer (on `issue_comment` webhook):
   - If `status=waiting_go` and comment is affirmative: sets `status: queued`, optionally posts "Work started."

6. **Worker** sees `status=queued`, runs the ralph loop (branch, task YAML, agent until PR report or clarification).

## Worker as daemon

- The worker runs in a loop. It watches `.coddy/issues/` (and `.coddy/prs/` if needed).
- In each iteration it:
  1. Processes at most one issue with `status=user_replied` (sufficiency, post "proceed?", set `waiting_go`).
  2. Then processes at most one issue with `status=queued` (run ralph loop).
- So "proceed?" is handled first; then one task is run. Both observer and worker use the same issue YAML as the source of truth.

## Observer poll (clarification)

- Besides the webhook server, the observer can run an optional **poll loop** over `.coddy/issues/`: every N seconds it looks for issues with `status=waiting_user_reply`; for each it posts the last comment's content to the platform and sets `status=clarification_sent`.
- Poll interval and enable flag can be configured (e.g. `observer.poll_interval_seconds`, `observer.poll_clarifications`).

## Configuration (optional)

- `bot.issue_stable_seconds`: If > 0, planner runs only for issues that have been unchanged for this many seconds (default 0 = run plan immediately on assignment).
- `observer.poll_interval_seconds`: Interval for scanning `.coddy/issues/` for clarification to post (e.g. 15).
- `observer.poll_clarifications`: Whether to run the clarification poll loop (default true when webhook is enabled).

## References

- [issue-flow.md](issue-flow.md) – Assignment to queue.
- [issue-storage.md](issue-storage.md) – Issue YAML format and status list.
- [system-specification.md](system-specification.md) – Overall architecture.
