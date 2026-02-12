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
git clone <repository-url>
cd codda
```

2. Create virtual environment:
```bash
python -m venv .venv
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

6. Run the bot:
```bash
python -m coddy.main
```

### Docker

```bash
docker build -t coddy-bot .
docker run -e GITHUB_TOKEN=... -e WEBHOOK_SECRET=... coddy-bot
```

## Configuration

See [System Specification](docs/system-specification.md) for detailed configuration options. For API tokens and developing adapters for GitHub, GitLab, or Bitbucket, see [Platform APIs](docs/platform-apis.md).

Key configuration areas:
- Git platform settings (GitHub, GitLab, BitBucket)
- AI agent configuration
- Bot identity (name, email)
- Webhook settings

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

[To be determined]

## Roadmap

- [x] System specification
- [ ] GitHub adapter implementation
- [ ] Cursor CLI agent integration
- [ ] Webhook server
- [ ] Issue processing workflow
- [ ] PR creation and management
- [ ] Review handling
- [ ] GitLab support
- [ ] BitBucket support
- [ ] Multiple AI agent support
- [ ] User attribution in commits
