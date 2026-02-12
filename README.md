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
pip install -r requirements.txt
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
python -m coddy.main
# or
python -m coddy.main --config /path/to/config.yaml
python -m coddy.main --check   # validate config and exit
```

### Docker Compose (recommended)

Tokens are passed via **Docker secrets** (files), not in the image or compose file.

1. **Copy config from example**:

```bash
cp config.example.yaml config.yaml
# Edit config.yaml if needed (repo, webhook settings, etc.)
```

2. **Create secret files** (do not commit them; `.secrets/` is in `.gitignore`):

```bash
mkdir -p .secrets
echo "YOUR_GITHUB_PAT" > .secrets/github_token
echo "YOUR_WEBHOOK_SECRET" > .secrets/webhook_secret
chmod 600 .secrets/github_token .secrets/webhook_secret
```

3. **Start the bot**:

```bash
docker compose up -d
```

4. **Health check**: `curl http://localhost:8000/health`

**Config**: `config.yaml` is mounted from the host via bind mount. Always copy `config.example.yaml` to `config.yaml` before first run - the example contains all available settings with defaults. Never commit `config.yaml` (it's in `.gitignore`).

### Docker (single run)

```bash
docker build -t coddy-bot .
docker run -e GITHUB_TOKEN=... -e WEBHOOK_SECRET=... coddy-bot
```

Or with secret files: `-e GITHUB_TOKEN_FILE=/run/secrets/gt -v $(pwd)/.secrets/github_token:/run/secrets/gt:ro`

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
codda/
├── docs/              # Documentation
├── src/
│   └── coddy/        # Main application code
│       ├── adapters/ # Git platform adapters
│       ├── agents/   # AI agent implementations
│       ├── services/ # Core services
│       └── webhook/  # Webhook server
├── tests/            # Test suite
├── .cursor/          # Cursor IDE rules
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

- [x] System specification
- [x] GitHub adapter implementation
- [x] Cursor CLI agent integration
- [ ] Webhook server
- [ ] Issue processing workflow
- [ ] PR creation and management
- [ ] Review handling
- [ ] GitLab support
- [ ] BitBucket support
- [ ] Multiple AI agent support
- [ ] User attribution in commits
