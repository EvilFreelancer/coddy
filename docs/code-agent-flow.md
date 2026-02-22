# Code agent flow: planning, clarification, and run

This document describes how the code agent is started, how it can ask the user for clarification (via the issue YAML and observer), and how the worker runs as a daemon watching `.coddy/issues/` and `.coddy/prs/`.

## Roles

- **Observer**: Webhook server + optional poll of `.coddy/issues/`. Receives platform events; when the agent writes a clarification question into an issue YAML, the observer posts it to the issue and marks it as sent. On user comments it updates the issue file and status.
- **Worker**: Daemon that watches `.coddy/issues/` (and `.coddy/prs/`). Handles issues in status `user_replied` (evaluate sufficiency, post "proceed?" and set `waiting_go`), then picks `queued` issues and runs the ralph loop (code agent). When the agent needs clarification it writes to the issue YAML; the observer then posts that to the platform.

## Trigger: when the plan is built

- When an issue is **assigned to the bot**, the observer only sets `status=pending_plan` in `.coddy/issues/`.
- The **worker** (poll loop) sees `pending_plan`, runs the code agent to build a plan, writes it to the issue YAML and sets `status=plan_ready`. The observer then posts that plan to the platform and sets `waiting_confirmation`.

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

## Worker as daemon (poll)

- The worker runs a **poll loop** over `.coddy/issues/` every N seconds (config: `worker.poll_interval_seconds`, default 10; CLI: `--poll-interval` overrides).
- In each poll pass it:
  1. Drains all `status=pending_plan` (build plan, write to YAML, set `plan_ready`; observer then posts to platform).
  2. Drains all `status=user_replied` (sufficiency, post "proceed?" and set `waiting_go`, or write clarification).
  3. Then processes at most one `status=queued` (run ralph loop).
- So plans and user replies are handled before any implementation task. Both observer and worker use the same issue YAML as the source of truth.

## Observer poll

- Besides the webhook server, the observer runs a **poll loop** over `.coddy/issues/` every N seconds (`observer.poll_interval_seconds`, default 15):
  - Issues with `status=plan_ready`: post last comment (worker's plan) to the platform, set `waiting_confirmation`.
  - Issues with `status=waiting_user_reply`: post last comment (clarification) to the platform, set `clarification_sent`.
- Enable flag: `observer.poll_clarifications` (default true).

## Configuration (optional)

- `observer.poll_interval_seconds`: Interval for observer poll (plan_ready and clarification), e.g. 15.
- `observer.poll_clarifications`: Whether to run the observer poll loop (default true).
- `worker.poll_interval_seconds`: Interval for worker poll of `.coddy/issues/` (pending_plan, user_replied, queued), e.g. 10. Env: `WORKER_POLL_INTERVAL_SECONDS`. CLI `--poll-interval` overrides.

## References

- [issue-flow.md](issue-flow.md) – Assignment to queue.
- [issue-storage.md](issue-storage.md) – Issue YAML format and status list.
- [system-specification.md](system-specification.md) – Overall architecture.
