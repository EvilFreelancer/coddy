# Coddy Bot - Architecture Documentation

## System Architecture

### Overview

Coddy Bot follows a **two-module** design: an **observer** that receives webhooks and enqueues tasks, and a **worker** that runs the development loop (Ralph-style) using an AI agent (e.g. Cursor CLI). Code is written only by the agent in iterative runs; the worker orchestrates the loop, git, and GitHub API.

**Trigger model**: The bot does not auto-process every new issue. Work is started when (1) a human assigns the bot to an issue, or (2) a user gives the bot an MR/PR number. The observer receives these events via **webhooks** and enqueues a task; the worker picks tasks and runs the ralph loop.

### Observer

- **Entry point**: `coddy observer` (or `python -m coddy.observer`)
- **Implementation**: `coddy.observer.run`
- **Responsibilities**: Run HTTP server for webhooks; verify signatures; on issue assigned to bot, create issue file and run planner (post plan, set waiting_confirmation); on user confirmation set issue status to queued. Does **not** run the development loop - that is done by the worker.

### Worker

- **Entry point**: `coddy worker` (or `python -m coddy.worker`)
- **Implementation**: `coddy.worker.run`
- **Responsibilities**: Poll the task queue; for each task (e.g. issue number): ensure branch exists and checkout; evaluate sufficiency (agent or heuristic); if insufficient, post clarification and exit; if sufficient, write task YAML and run the **ralph loop**: repeatedly run the Cursor CLI agent until `.coddy/pr-{issue_number}.yaml` exists or `agent_clarification` appears in task YAML or max iterations reached; then create PR, set labels, switch to default branch. Uses platform adapter for API calls and agent for a single run per iteration.

### Task source and status

- **Issues**: `.coddy/issues/{issue_number}.yaml` - one YAML per issue. Status: pending_plan, waiting_confirmation, queued, in_progress, done, failed, closed. Worker picks issues with status=queued; on success/failure sets status to done/failed. On issue closed (webhook), status is set to closed.
- **PRs**: `.coddy/prs/{pr_number}.yaml` - one YAML per PR. Status: open, merged, closed. On PR closed (webhook), status is set to merged or closed.
- **Legacy**: `.coddy/queue/` (pending/done/failed) is no longer used; queue logic uses issue status only.

## Package Layout

The codebase is organized into services (shared), observer, worker, and utils.

### Services (`coddy/services/`)

Shared layer used by both observer and worker.

| Path | Description |
|------|-------------|
| `services/store/` | Issue and PR storage (`.coddy/issues/*.yaml`, `.coddy/prs/*.yaml`). Schemas: IssueFile, IssueComment, PRFile. Functions: create_issue, load_issue, save_issue, set_issue_status, list_queued, list_pending_plan, add_comment; load_pr, save_pr, set_pr_status. |
| `services/git/` | Git operations: `branches.py` (branch name sanitization, checkout, fetch); `commits.py` (stage and commit); `push_pull.py` (pull, push, commit_all_and_push). Used by observer (webhook, review) and worker (ralph loop). |

**Dependencies**: Standard lib, third-party (pydantic, yaml). No observer or worker imports.

### Observer (`coddy/observer/`)

Everything that observes events, stores state, and enqueues work. Does not run the AI agent.

| Path | Description |
|------|-------------|
| `observer/adapters/` | Git platform adapters (base, GitHub). |
| `observer/models/` | Pydantic models: Issue, Comment, PR, ReviewComment. |
| `observer/planner.py` | Plan generation and user confirmation flow. |
| `observer/webhook/` | Webhook server and event handlers. |
| `observer/run.py` | Observer entry: webhook server only (plan on assignment). |

**Dependencies**: config, standard lib, third-party, `coddy.services.store`, `coddy.services.git`.

### Worker (`coddy/worker/`)

Runs the development loop and uses the AI agent.

| Path | Description |
|------|-------------|
| `worker/task_yaml.py` | Task and PR report YAML (`.coddy/task-{n}.yaml`, `.coddy/pr-{n}.yaml`), review task/reply files, log path. |
| `worker/agents/` | AI agent interface: `base.py` (AIAgent, SufficiencyResult), `cursor_cli_agent.py` (Cursor CLI headless). |
| `worker/ralph_loop.py` | Ralph loop: sufficiency, branch, repeated agent runs until PR report or clarification. |
| `worker/run.py` | Worker entry: reads queued issues from store, currently dry-run stub (writes empty PR YAML). |

**Dependencies**: observer (models), `coddy.services.store`, `coddy.services.git`, utils.

### Utils (`coddy/utils/`)

Shared utilities; no business logic.

| Path | Description |
|------|-------------|
| `utils/__init__.py` | Re-exports git helpers from `coddy.services.git` (branch name, checkout, pull, commit_and_push). |

**Dependencies**: `coddy.services.git`.

### Application Entry (`coddy/`)

- `main.py` - CLI: `coddy observer` | `coddy worker`; loads config, dispatches to observer.run or worker.run.
- `config.py` - Configuration (YAML + env).
- `logging.py` - Logging setup from config and env (CoddyLogging, levels: DEBUG, INFO, WARNING, ERROR; LOGGING_LEVEL, LOGGING_FORMAT).
- `daemon.py` - Thin wrapper (legacy): `python -m coddy.daemon` calls observer.run.main.
- `worker.py` - Thin wrapper: `python -m coddy.worker` calls worker.run.main.

## Architecture Layers (Logical)

### Layer 1: Platform Adapters

**Location**: `coddy/observer/adapters/`

Abstract interfaces and implementations for Git hosting platforms. Authentication, endpoints, and mapping of operations across GitHub, GitLab, and Bitbucket are described in [Platform APIs](platform-apis.md).

- `base.py` - Abstract base classes for platform adapters
- `github.py` - GitHub API implementation
- GitLab / Bitbucket (planned)

**Dependencies**: None (lowest layer)

### Layer 2: AI Agent Interface

**Location**: `coddy/worker/agents/`

Pluggable interface for AI code generation agents.

- `base.py` - Abstract base class (AIAgent, SufficiencyResult)
- `cursor_cli_agent.py` - Cursor CLI agent implementation
- `make_cursor_cli_agent(config)` - Build agent from config

**Dependencies**: Observer models (Issue, Comment, ReviewComment), worker.task_yaml

### Layer 3: Observer Services

**Location**: `coddy/observer/`

Business logic for events, state, queue, and planning. No agent execution.

- `planner.py` - Plan generation, confirmation flow
- `webhook/` - Event handling

**Dependencies**: Adapters, coddy.services.store, worker.agents (for planner)

### Layer 4: Worker

**Location**: `coddy/worker/`

Orchestrates the development loop and uses the agent.

- `ralph_loop.py` - Sufficiency, branch, loop until PR report or clarification
- `run.py` - Queue polling, run ralph loop per task

**Dependencies**: Observer (adapters, queue, models), utils, worker.agents, worker.task_yaml

## Component Interactions

```
  OBSERVER (observer.run)
  Webhook Server -> on assigned: planner -> .coddy/issues/ (waiting_confirmation -> queued)
  Worker (worker.run) polls .coddy/issues/ (status=queued) -> for each task: ralph loop -> Cursor CLI (per iteration)
  -> PR report (.coddy/pr-{n}.yaml) or agent_clarification -> Create PR / post comment; labels; checkout default.
```

## Design Patterns

### Factory Pattern

Used for:
- Creating AI agents (`make_cursor_cli_agent(config)`)

### Strategy Pattern

Used for:
- Different Git platform implementations (adapters)
- Different AI agent implementations

### Observer Pattern

Used for:
- Webhook event handling
- Issue state changes (pending_plan, waiting_confirmation, queued)

## Data Flow

### Issue Processing Flow

1. **Trigger Event** -> Webhook "bot assigned to issue"; issue stored in `.coddy/issues/{n}.yaml`, planner runs, plan posted, status -> waiting_confirmation
2. **User confirms** -> Webhook issue_comment (affirmative); issue status set to queued in `.coddy/issues/{n}.yaml`
3. **Worker** -> Picks queued issue; ralph loop: sufficiency, branch, write `.coddy/task-{n}.yaml`, run agent until `.coddy/pr-{n}.yaml` or agent_clarification
4. **PR Creation** -> Worker creates PR from report body, sets label, checkout default branch

## Configuration Management

Configuration is loaded from:
1. Environment variables (highest priority)
2. Configuration file (`config.yaml`)
3. Default values

See [System Specification](system-specification.md) for the full configuration structure.

## Error Handling Strategy

1. **Transient Errors**: Retry with exponential backoff
2. **Permanent Errors**: Log and notify (issue comment)
3. **Agent Failures**: Fallback or request clarification (agent_clarification in task YAML)
4. **API Rate Limits**: Queue and retry later

## Testing Strategy

- **Unit Tests**: Each component tested in isolation; mocks for adapters and agents
- **Integration Tests**: Component interactions (e.g. webhook -> handler -> issue store)
- **Mock Platform**: Mock Git platform API and agent in tests

Tests live in `tests/`; import from `coddy.observer.*`, `coddy.worker.*`, `coddy.utils.*`.

## Deployment

### Docker Container

- Single container with all dependencies
- Environment variables for configuration
- Health check endpoint
- Logging to stdout/stderr

### Environment Variables

- `GITHUB_TOKEN` - GitHub API token
- `WEBHOOK_SECRET` - Webhook verification secret
- `BOT_NAME` - Bot name for commits
- `BOT_EMAIL` - Bot email for commits
- `REPOSITORY` - Target repository (owner/repo)
- AI agent config via `config.yaml` (e.g. cursor_cli)
