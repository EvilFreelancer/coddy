# Development Guide

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- Docker (optional, for containerized deployment)
- GitHub token with appropriate permissions (for development)

### Setup Development Environment

1. Clone the repository:
```bash
git clone <repository-url>
cd coddy
```

2. Create and activate virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install development dependencies:
```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks (optional):
```bash
pre-commit install
```

5. Copy configuration example:
```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
```

6. Set environment variables:
```bash
export GITHUB_TOKEN=your_token_here
export WEBHOOK_SECRET=your_secret_here
export REPOSITORY=owner/repo
```

## Development Workflow

### Code Style

The project uses `ruff` for linting and formatting:

```bash
# Check code style
ruff check .

# Format code
ruff format .

# Auto-fix issues
ruff check --fix .
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=coddy --cov-report=html

# Run specific test
pytest tests/test_module.py::test_function -v
```

### Type Checking

```bash
mypy coddy/
```

## Project Structure

```
coddy/
├── docs/                    # Documentation
│   ├── system-specification.md
│   ├── architecture.md
│   ├── development-guide.md
│   ├── issue-storage.md
│   ├── issue-flow.md
│   └── ...
├── coddy/                   # Main application code
│   ├── services/            # Shared by observer and worker
│   │   ├── store/           # Issue and PR storage (.coddy/issues/, .coddy/prs/)
│   │   └── git/             # Git operations (branches, commits, push_pull)
│   ├── observer/            # Daemon: adapters, planner, webhook
│   │   ├── adapters/       # Git platform adapters
│   │   ├── models/         # Pydantic models (Issue, PR, Comment, ReviewComment)
│   │   ├── webhook/        # Webhook server and handlers
│   │   ├── planner.py       # Plan and confirmation flow
│   │   └── run.py           # Observer entry point
│   ├── worker/              # Worker: ralph loop, agents
│   │   ├── agents/          # AI agents (base, cursor_cli)
│   │   ├── task_yaml.py     # Task and PR report YAML
│   │   ├── ralph_loop.py    # Development loop
│   │   └── run.py           # Worker entry point
│   ├── utils/               # Re-exports from coddy.services.git (backward compat)
│   ├── config.py            # Configuration management
│   └── main.py              # Application entry point (observer | worker)
├── tests/                   # Test suite
├── .cursor/                 # Cursor IDE rules
├── pyproject.toml
├── pytest.ini
├── ruff.toml
├── config.example.yaml
└── README.md
```

## Architecture

See [Architecture Documentation](architecture.md) for detailed architecture information.

### Key Principles

1. **Layer-based architecture**: Lower layers don't depend on upper layers
2. **Abstract interfaces**: Use abstract base classes for extensibility
3. **Factory pattern**: Use factories for creating adapters and agents
4. **Dependency injection**: Inject dependencies for testability
5. **Configuration-driven**: Load configuration from environment and files

## Adding New Features

Follow the TDD workflow described in `.cursor/rules/workflow.mdc`:

1. Write test first (red)
2. Verify test fails
3. Implement feature
4. Verify test passes (green)
5. Run all tests
6. Run linter
7. Write report

## Adding New Git Platform

1. Create adapter in `coddy/observer/adapters/` implementing the base adapter interface (see `base.py`)
2. Add tests in `tests/test_adapters_*.py`
3. Add configuration in `config.example.yaml`
4. Update documentation

## Adding New AI Agent

1. Create agent in `coddy/worker/agents/` implementing `AIAgent` from `coddy.worker.agents.base`
2. Add tests in `tests/test_agents_*.py`
3. Add factory helper (e.g. `make_*_agent(config)`) and wire in config
4. Add configuration in `config.example.yaml`
5. Update documentation

## Debugging

### Enable Debug Logging

Logging is configured by `coddy.logging` (CoddyLogging) from `config.yaml` and env (LOGGING_LEVEL, LOGGING_FORMAT). Set level to DEBUG in `config.yaml`:
```yaml
logging:
  level: "DEBUG"
```
Or set env: `LOGGING_LEVEL=DEBUG`.

### Run in Debug Mode

```bash
python -m coddy.main --debug
```

### Docker Debugging

```bash
docker build -t coddy-bot .
docker run -it --rm \
  -e GITHUB_TOKEN=... \
  -e WEBHOOK_SECRET=... \
  coddy-bot
```

## Contributing

1. Follow the coding standards in `.cursor/rules/code-style.mdc`
2. Write tests for all new features
3. Ensure all tests pass
4. Run linter and fix all issues
5. Update documentation as needed

## References

- [System Specification](system-specification.md)
- [Architecture Documentation](architecture.md)
- [Issue Storage](issue-storage.md)
- [Issue Flow](issue-flow.md)
- [Cursor Rules](../.cursor/rules/)
