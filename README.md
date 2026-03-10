# Coddy Bot

**Community Driven Development Bot**

Coddy Bot is an autonomous development assistant that integrates with Git hosting platforms (GitHub, GitLab, BitBucket). You assign the bot to an issue (or give it an MR/PR number), and it generates code using AI agents, creates pull requests, and responds to code reviews. Full automation (e.g. picking up every new issue) is planned for later.

## Features

- **Trigger by Assignment or MR/PR** - bot starts work when a human assigns it to an issue, or when given a merge/pull request number (no auto-pick of all new issues in the first version)
- **Issue Labels (Tags)** - bot sets and updates issue labels (e.g. `in progress`, `stuck`, `review`, `done`)
- **Code Generation** - uses AI agents (Cursor CLI, etc.) to generate code
- **Pull Request Management** - creates PRs with generated code and documentation
- **Review Loop** - responds to PR reviews and line comments, implements requested changes via AI agent, replies in review threads
- **Draft PR Support** - handles `converted_to_draft` / `ready_for_review` webhook events, tracks draft status in store
- **Sync on Startup** - syncs issues and PRs from the platform API into `.coddy/` when the observer starts
- **Review Idle Timeout** - automatically triggers re-planning when a PR sits in `review_received` state past the idle timeout
- **Multi-Platform Support** - GitHub (primary), GitLab and BitBucket (planned)
- **Extensible Agents** - pluggable AI agent interface for different code generators
- **Russian Confirmation Support** - planner recognizes Russian affirmative phrases ("da", "ustroit", "poekhali", etc.) for plan approval

## Architecture

The system follows a modular architecture with clear separation of concerns:

- **Platform Adapters**: Abstract interfaces for Git hosting platforms
- **AI Agent Interface**: Pluggable interface for code generation agents
- **Core Services**: Business logic and orchestration
- **Webhook Server**: Receives and processes Git platform events

See [Architecture Documentation](docs/architecture.md) for details.

## Quick Start

### Prerequisites

- Python 3.14+ (3.14-slim in Docker)
- Node.js 24 (required by Cursor CLI agent, needs Node 23.8+ for `--use-system-ca`)
- Docker (optional, recommended)
- GitHub token with appropriate permissions
- Cursor CLI (or other AI agent)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/EvilFreelancer/coddy.git
cd coddy
```

2. Create virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -e ".[dev]"
```

4. Configure the bot:

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
```

5. Set environment variables:

```bash
export GITHUB_TOKEN=your_github_token
export WEBHOOK_SECRET=your_webhook_secret
export REPOSITORY=owner/repo
```

6. Run the bot (optional `--config` path):

```bash
python -m coddy              # observer (default) or worker subcommand
python -m coddy observer     # webhook server (plan on assignment)
python -m coddy worker       # development loop (pick queued issues, run agent, create PRs)
python -m coddy --config /path/to/config.yaml
python -m coddy --check      # validate config and exit
```

Key CLI flags

- `--config`, `-c` - path to YAML config file (default `config.yaml`)
- `--check` - validate config and exit (both observer and worker)
- `--once` - process at most one task and exit (worker only)
- `--poll-interval` - polling interval for `.coddy/issues/` in seconds (worker only)

Key configuration options

- `observer.sync_on_startup` - sync issues/PRs from API on observer start (env `OBSERVER_SYNC_ON_STARTUP`, default `false`)
- `observer.assignment_only` - only trigger planner when bot is assigned to an issue
- `logging` - logging level and format (CoddyLogging)

### Docker (recommended)

Coddy consists of **two modules** that can run in one or two processes:

- **Observer** – webhook server; receives GitHub events, runs the planner on assignment, writes issue/PR metadata to `.coddy/`. Command: `python -m coddy observer --config /app/config.yaml`.
- **Worker** – development loop; picks queued issues, runs the AI agent, creates branches and PRs. Command: `python -m coddy worker --config /app/config.yaml`.

The easiest way to run both is with Docker Compose. Tokens are passed via **Docker secrets** (files in `.secrets/`), not in the image or compose file.

1. **Create secrets and config** (creates `.secrets/` and `config.yaml` from templates):

```bash
chmod +x scripts/setup-docker-secrets.sh
./scripts/setup-docker-secrets.sh
```

2. **Replace placeholders** with real values (do not commit `.secrets/`):

- Edit `.secrets/github_token` - your GitHub Personal Access Token
- Edit `.secrets/webhook_secret` - the secret from your GitHub webhook
- (Optional) Edit `.secrets/cursor_agent_token` for Cursor CLI agent, or leave the placeholder
- Edit `config.yaml` if needed (repository, webhook path). Set `webhook.enabled: true` so the server listens on port 8000 and the health check works.

3. **Start the bot**:

```bash
docker compose up -d
```

4. **Check**:

```bash
curl http://localhost:8000/health
docker compose logs -f coddy-observer
docker compose logs -f coddy-worker
```

Key environment variables (see `docker-compose.yml` for defaults)

- `REPO_PATH` - host path to the repository (default `.`)
- `OBSERVER_SYNC_ON_STARTUP` - sync issues/PRs from API on start (default `false`)
- `CURSOR_CLI_TIMEOUT` - Cursor agent timeout in seconds (default `600`)
- `CODDY_PORT` - observer HTTP port (default `8000`)
- `SSH_DIR` - path to SSH keys for git push (default `~/.ssh`)
- `BOT_WORKSPACE_PATH` - workspace path inside container (default `/app/workspace`)
- `BOT_REPOSITORY` - repository in `owner/repo` format

The observer container includes a health check at `/health` (HTTP, port 8000, 30s interval).

See [Docker and Secrets](docs/docker-and-secrets.md) for details (Cursor Agent token, config mount, CLI in container). To run the worker without exposing secrets, use a workspace path that does not contain `.secrets/` (same doc).

### Docker (single run)

One container runs only one module. Use the same image and volumes; only the command differs.

**Observer** (webhook server, port 8000):

```bash
docker build -t coddybot .
docker run --rm -p 8000:8000 \
  -e GITHUB_TOKEN=your_github_token \
  -e WEBHOOK_SECRET=your_webhook_secret \
  -e BOT_WORKSPACE_PATH=/app/workspace \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v /path/to/your/target-repo:/app/workspace:rw \
  coddybot \
  python -m coddy observer --config /app/config.yaml
```

**Worker** (development loop, no port):

```bash
docker run --rm \
  -e GITHUB_TOKEN=your_github_token \
  -e CURSOR_AGENT_TOKEN=your_cursor_agent_token \
  -e BOT_WORKSPACE_PATH=/app/workspace \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v /path/to/your/target-repo:/app/workspace:rw \
  coddybot \
  python -m coddy worker --config /app/config.yaml
```

Use the same `/path/to/your/target-repo` for both so they share the workspace and `.coddy/`. Or use Docker secrets and `*_FILE` env vars; see `docker-compose.dist.yaml` for variable names.

## Configuration

See [System Specification](docs/system-specification.md) for detailed configuration options. For API tokens and developing adapters for GitHub, GitLab, or Bitbucket, see [Platform APIs](docs/platform-apis.md).

Key configuration areas:

- Git platform settings (GitHub, GitLab, BitBucket)
- AI agent configuration
- Bot identity (name, email, default branch)
- Webhook settings

### PR merged webhook and restart

When a pull request is merged (GitHub `pull_request` event with `action: closed` and `merged: true`), the bot runs `git pull origin <default_branch>` in its working directory and then exits with code 0 so that a process manager can restart it.

- **Console**: Run the bot under a supervisor that restarts on exit (e.g. systemd, or a shell loop like `while true; do python -m coddy.main; done`).
- **Docker**: Use a restart policy (e.g. `restart: unless-stopped` in Compose) so the container restarts after the bot exits and picks up the latest code.

## Development

### Project Structure

```
coddy/
├── coddy/                  # Main application code
│   ├── services/           # Shared services (observer + worker)
│   │   ├── store/          # Issue and PR storage (.coddy/issues/, .coddy/pull_requests/)
│   │   │   └── schemas/    # Pydantic schemas (IssueFile, PRFile, PRReview, PendingPRRequest)
│   │   └── git/            # Git operations (branches, commits, push_pull)
│   ├── observer/           # Observer: adapters, planner, webhook, sync
│   │   ├── adapters/       # Git platform adapters (GitHub, etc.)
│   │   ├── models/         # Pydantic models (Issue, PR, Comment, ReviewComment)
│   │   ├── webhook/        # Webhook server and handlers
│   │   ├── planner.py      # Plan and user confirmation (supports Russian)
│   │   ├── sync.py         # Sync issues/PRs from API on startup
│   │   ├── clarification_poll.py  # Polls for plan posting, PR creation, review idle
│   │   └── run.py          # Observer entry point
│   ├── worker/             # Worker: ralph loop, agents, review loop
│   │   ├── agents/         # AI agents (base, cursor_cli)
│   │   ├── task_yaml.py    # Task/PR report YAML paths and helpers
│   │   ├── ralph_loop.py   # Development loop
│   │   ├── review_loop.py  # Review comment handling via AI agent
│   │   └── run.py          # Worker entry point
│   ├── config.py           # Configuration
│   ├── logging.py          # Logging from config and env (CoddyLogging)
│   ├── main.py             # CLI (observer | worker)
│   ├── daemon.py           # Thin wrapper (legacy): python -m coddy.daemon -> observer.run
│   └── worker.py           # Thin wrapper for python -m coddy.worker
├── .coddy/                 # Runtime data (managed by bot)
│   ├── issues/             # open/, closed/ - one YAML per issue
│   ├── pull_requests/      # open/, merged/, rejected/, draft/, pending/
│   ├── logs/               # Agent logs per issue
│   ├── task-{N}.yaml       # Task file for agent
│   ├── pr-{N}.yaml         # PR report from agent
│   └── review-{N}.yaml     # Review task for agent
├── docs/                   # Documentation
├── tests/                  # Test suite
├── scripts/                # Setup scripts
├── .cursor/                # Cursor IDE rules
└── README.md
```

### Running Tests

```bash
pytest tests/ -v
```

### Code Style

The project uses `ruff` for linting and formatting:

```bash
ruff check .
ruff format .
```

## Workflow

1. **User creates issue** → A human **assigns the bot** to the issue (or gives the bot an MR/PR number)
2. **Bot picks up work** → Starts only for assigned/referenced issues or MRs
3. **Bot analyzes** → Writes specification in issue comments and sets labels (e.g. `in progress`)
4. **Bot generates code** → Uses AI agent to create code, updates labels as needed
5. **Bot creates PR** → Opens pull request with code, sets label e.g. `review`
6. **User reviews** → Comments on PR
7. **Bot responds** → Implements changes, responds to comments, updates labels (e.g. `done` when merged)

## Contributing

See [Development Rules](.cursor/rules/) for coding standards and workflow.

## License

\[To be determined\]

## Roadmap

Done vs planned. Only **GitHub** is supported; GitLab and Bitbucket are not implemented.

### Observer (webhook server, planning, no agent)

Runs as a daemon: receives webhooks, stores events, runs planner when the bot is assigned.

- [x] Webhook server (HTTP, signature verification, JSON and form-urlencoded body)
- [x] **Adapters** (Git platform API)
  - [x] GitHub (issues, comments, PR creation, review comments, reply_to_review_comment)
  - [ ] GitLab
  - [ ] Bitbucket
- [x] **Issues** - stored for all events; planner runs only when assignee is the bot
  - [x] `opened` - create issue in store
  - [x] `assigned` - create or update issue, set `assigned_at` / `assigned_to`; run planner if assignee is bot
  - [x] `unassigned` - clear `assigned_at` / `assigned_to` in store
  - [x] `edited` - update title/description, `updated_at`
  - [x] `closed` - set status to closed
- [x] **Issue comments** - stored; used for confirmation flow
  - [x] Created - append comment
  - [x] Edited - update comment by `comment_id`
  - [x] Deleted - soft delete (set `deleted_at`)
- [x] **Pull request**
  - [x] Merged - `git pull` in workspace and exit (for restart)
  - [x] Reacting to PR reviews - `pull_request_review` webhook, saves review to PR store
  - [x] Reacting to PR comments - `pull_request_review_comment` and `issue_comment` on PR
  - [x] Draft PR support - `converted_to_draft` / `ready_for_review` events, draft status in store
- [x] Planner (post plan, wait for user confirmation, set status to queued)
  - [x] Russian confirmation support ("da", "ustroit", "poekhali", etc.)
- [x] Sync on startup - sync issues/PRs from API into `.coddy/` (`observer.sync_on_startup`)
- [x] Clarification poll - plan posting, PR creation via API, review idle timeout

### Worker (development loop, AI agent)

Picks queued issues, runs agent, creates branches/commits/PRs.

- [x] Task/PR YAML paths and workspace under `bot.workspace_path`
- [x] Ralph loop (sufficiency, branch, agent loop) - structure in place
- [x] **Agents**
  - [x] Cursor CLI agent (partial integration)
  - [ ] Other agents / multiple agents
- [x] Full PR creation and push from worker - worker writes `PendingPRRequest`, observer creates PR via API
- [x] Review handling - review_loop.py processes review comments via AI agent, replies in threads
- [x] PR comment handling - stored comments, workflow status transitions

### Services (shared by observer and worker)

- [x] **Store** - meta for issues and PRs
  - [x] Issue store (`.coddy/issues/` - one YAML per issue, status, comments, `assigned_at` / `assigned_to`)
  - [x] PR store (`.coddy/pull_requests/` - open, merged, rejected, draft, pending)
  - [x] PR review schemas (PRReview, PRReviewComment)
- [x] **Git** - branches, commits, push/pull (used by observer on PR merged and by worker)
- [x] **Workspace** - single working directory per bot (`BOT_WORKSPACE_PATH`), repo cloned there

### Other

- [x] System specification and config (env + YAML)
- [x] Review idle timeout - auto-transitions `review_received` to `pending_plan` after timeout
- [x] PR workflow statuses - `idle`, `review_received`, `pending_plan`, `waiting_confirmation`, `in_progress`
- [ ] User attribution in commits
- [ ] GitLab / Bitbucket adapters and webhook events
