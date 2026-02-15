# Coddy Bot

**Community Driven Development Bot**

Coddy Bot is an autonomous development assistant that integrates with Git hosting platforms (GitHub, GitLab, BitBucket). You assign the bot to an issue (or give it an MR/PR number), and it generates code using AI agents, creates pull requests, and responds to code reviews. Full automation (e.g. picking up every new issue) is planned for later.

## Features

- **Trigger by Assignment or MR/PR**: Bot starts work when a human assigns it to an issue, or when given a merge/pull request number (no auto-pick of all new issues in the first version)
- **Issue Labels (Tags)**: Bot sets and updates issue labels (e.g. `in progress`, `stuck`, `review`, `done`)
- **Code Generation**: Uses AI agents (Cursor CLI, etc.) to generate code
- **Pull Request Management**: Creates PRs with generated code and documentation
- **Review Handling**: Responds to code reviews and implements requested changes
- **Multi-Platform Support**: GitHub (primary), GitLab and BitBucket (planned)
- **Extensible Agents**: Pluggable AI agent interface for different code generators

## Architecture

The system follows a modular architecture with clear separation of concerns:

- **Platform Adapters**: Abstract interfaces for Git hosting platforms
- **AI Agent Interface**: Pluggable interface for code generation agents
- **Core Services**: Business logic and orchestration
- **Webhook Server**: Receives and processes Git platform events

See [Architecture Documentation](docs/architecture.md) for details.

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional)
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
python -m coddy worker       # dry-run stub (read issues, write empty PR YAML)
python -m coddy --config /path/to/config.yaml
python -m coddy --check      # validate config and exit
```

### Docker (recommended)

The easiest way to run the bot is with Docker Compose. Tokens are passed via **Docker secrets** (files in `.secrets/`), not in the image or compose file.

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
docker compose logs -f coddy
```

See [Docker and Secrets](docs/docker-and-secrets.md) for details (Cursor Agent token, config mount, CLI in container).

### Docker (single run)

```bash
docker build -t coddybot .
docker run -e GITHUB_TOKEN=... -e WEBHOOK_SECRET=... -v $(pwd)/config.yaml:/app/config.yaml:ro coddybot
```

Or mount secret files and pass `*_FILE` env vars; see `docker-compose.yml` for the exact variable names.

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
│   │   ├── store/          # Issue and PR storage (.coddy/issues/, .coddy/prs/)
│   │   └── git/            # Git operations (branches, commits, push_pull)
│   ├── observer/           # Observer: adapters, planner, webhook
│   │   ├── adapters/       # Git platform adapters (GitHub, etc.)
│   │   ├── models/         # Pydantic models (Issue, PR, Comment, ReviewComment)
│   │   ├── webhook/        # Webhook server and handlers
│   │   ├── planner.py      # Plan and user confirmation
│   │   └── run.py          # Observer entry point
│   ├── worker/             # Worker: ralph loop, agents
│   │   ├── agents/         # AI agents (base, cursor_cli)
│   │   ├── task_yaml.py    # Task/PR report YAML paths and helpers
│   │   ├── ralph_loop.py   # Development loop
│   │   └── run.py         # Worker entry point
│   ├── config.py           # Configuration
│   ├── main.py             # CLI (observer | worker)
│   ├── daemon.py           # Thin wrapper (legacy): python -m coddy.daemon -> observer.run
│   └── worker.py           # Thin wrapper for python -m coddy.worker
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
  - [x] GitHub (partially: issues, issue comments, PR merged)
  - [ ] GitLab
  - [ ] Bitbucket
- [x] **Issues** – stored for all events; planner runs only when assignee is the bot
  - [x] `opened` – create issue in store
  - [x] `assigned` – create or update issue, set `assigned_at` / `assigned_to`; run planner if assignee is bot
  - [x] `unassigned` – clear `assigned_at` / `assigned_to` in store
  - [x] `edited` – update title/description, `updated_at`
  - [x] `closed` – set status to closed
- [x] **Issue comments** – stored; used for confirmation flow
  - [x] Created – append comment
  - [x] Edited – update comment by `comment_id`
  - [x] Deleted – soft delete (set `deleted_at`)
- [x] **Pull request**
  - [x] Merged – `git pull` in workspace and exit (for restart)
  - [ ] Reacting to PR reviews – not implemented
  - [ ] Reacting to PR comments – not implemented
- [x] Planner (post plan, wait for user confirmation, set status to queued)

### Worker (development loop, AI agent)

Picks queued issues, runs agent, creates branches/commits/PRs.

- [x] Task/PR YAML paths and workspace under `bot.workspace`
- [x] Ralph loop (sufficiency, branch, agent loop) – structure in place
- [x] **Agents**
  - [x] Cursor CLI agent (partial integration)
  - [ ] Other agents / multiple agents
- [ ] Full PR creation and push from worker – not ready
- [ ] Review handling – not implemented
- [ ] PR comment handling – not implemented

### Services (shared by observer and worker)

- [x] **Store** – meta for issues and PRs
  - [x] Issue store (`.coddy/issues/` – one YAML per issue, status, comments, `assigned_at` / `assigned_to`)
  - [x] PR store (`.coddy/prs/`)
- [x] **Git** – branches, commits, push/pull (used by observer on PR merged and by worker)
- [x] **Workspace** – single working directory per bot (`BOT_WORKSPACE`), repo cloned there

### Other

- [x] System specification and config (env + YAML)
- [ ] User attribution in commits
- [ ] GitLab / Bitbucket adapters and webhook events
