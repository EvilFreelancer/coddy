# Coddy Bot - Architecture Documentation

## System Architecture

### Overview

Coddy Bot follows a modular architecture with clear separation of concerns. The system is designed to be extensible, allowing easy addition of new Git platforms and AI agents.

**Trigger model**: The bot does not auto-process every new issue. Work is started when (1) a human assigns the bot to an issue, or (2) a user gives the bot an MR/PR number. The Issue Monitor reacts to these events only; full automation is a later phase.

## Architecture Layers

### Layer 1: Platform Adapters

**Location**: `src/coddy/adapters/`

Abstract interfaces and implementations for Git hosting platforms. Authentication, endpoints, and mapping of operations across GitHub, GitLab, and Bitbucket are described in [Platform APIs](platform-apis.md).

- `base.py` - Abstract base classes for platform adapters
- `github/` - GitHub API implementation
- `gitlab/` - GitLab API implementation (planned)
- `bitbucket/` - BitBucket API implementation (planned)

**Dependencies**: None (lowest layer)

### Layer 2: AI Agent Interface

**Location**: `src/coddy/agents/`

Pluggable interface for AI code generation agents.

- `base.py` - Abstract base class for AI agents
- `cursor_cli.py` - Cursor CLI agent implementation
- `factory.py` - Agent factory for creating agent instances

**Dependencies**: Layer 1 (may need Git platform for context)

### Layer 3: Core Services

**Location**: `src/coddy/services/`

Business logic and orchestration services.

- `issue_monitor.py` - Consumes events (from webhooks or scheduler) and tracks issues/PRs to work on; reacts to new issue comments
- `code_generator.py` - Orchestrates code generation
- `pr_manager.py` - Manages pull request lifecycle
- `review_handler.py` - Processes code reviews
- `specification_generator.py` - Generates feature specifications
- `scheduler.py` - Optional poller: when webhooks are not available, periodically fetches issues assigned to bot, new issue comments, and new PR/MR comments; produces same logical events as webhooks

**Dependencies**: Layers 1, 2

### Layer 4: Webhook Server and Scheduler

**Location**: `src/coddy/webhook/`, `src/coddy/scheduler/` (or under `services/`)

Event sources for the Issue Monitor.

- **Webhook** (`webhook/`): `server.py`, `handlers.py`, `verification.py` - receives platform events when webhooks are configured
- **Scheduler** (e.g. `scheduler/poller.py`): runs on an interval; calls platform adapter to list issues assigned to bot, get issue comments since last run, get PR comments/reviews; pushes events into Issue Monitor so the rest of the pipeline is unchanged

**Dependencies**: Layers 1, 3

### Layer 5: Application Entry Point

**Location**: `src/coddy/`

Main application entry point and configuration.

- `main.py` - Application entry point
- `config.py` - Configuration management
- `models.py` - Data models

**Dependencies**: All layers

## Component Interactions

```
                    ┌─────────────────┐
                    │ Webhook Server  │ (when configured)
                    └────────┬────────┘
                             │
                             ▼
┌─────────────────┐   ┌─────────────────┐
│   Scheduler     │──▶│  Issue Monitor  │
│   (poller)      │   │                 │
└────────┬────────┘   └─────────┬───────┘
         │                      │
         │  (no webhooks /      │  new assignment, new issue
         │   fallback)          │  comment, new PR comment
         │                      ▼
         │              Specification Generator → Issue Comments
         │                      │
         │                      ▼
         │              Code Generator
         │                      │
         │                      ▼
         │              AI Agent (Cursor CLI)
         │                      │
         │                      ▼
         └─────────────▶ PR Manager → Pull Request
                                │
                                ▼
                        Review Handler ← PR Comments/Reviews
                                │
                                ▼
                        Code Generator (for fixes)
```

## Design Patterns

### Factory Pattern

Used for:
- Creating Git platform adapters (`GitPlatformFactory`)
- Creating AI agents (`AIAgentFactory`)

### Strategy Pattern

Used for:
- Different Git platform implementations
- Different AI agent implementations

### Observer Pattern

Used for:
- Webhook event handling
- Issue state changes

## Data Flow

### Issue Processing Flow

1. **Trigger Event** → Webhook or **Scheduler** (polling) produces "bot assigned to issue" or "user provided MR/PR number"; only then is work queued
2. **New comment on issue** → If the scheduler (or webhook) detects a new comment on an issue the bot is working on, Issue Monitor passes full issue + comments to the pipeline so the bot takes user input into account (re-evaluate sufficiency, re-spec, or continue)
3. **Event Parsing** → Handler parses event type and confirms it is an assignment or MR reference
4. **Issue/PR Retrieval** → Platform adapter fetches issue or MR/PR details (and all comments when processing new comment)
5. **Data Sufficiency** → Bot evaluates whether issue description and comments contain enough information to implement. If not: post comment in issue asking for clarification, set label `stuck`, stop. If yes: set label `in progress`, optionally write spec in comments, proceed
6. **Code Generation** → Code generator creates branch, switches to it, calls AI agent, commits, pushes
7. **PR Creation** → Code agent writes PR description (what was done, how to test, reference to issue) to `.coddy/pr-{issue_number}.md` as the last step of the task; PR manager creates pull request using that description; issue label set to `review`
8. **Monitoring** → Webhook or scheduler monitors PR for new reviews and comments

### Review Processing Flow

1. **Review Event** → Webhook or **Scheduler** (polling PR comments/reviews) delivers new review or comment
2. **Comment Parsing** → Review handler parses comment
3. **Change Identification** → Handler identifies requested changes
4. **Code Improvement** → Code generator calls AI agent with feedback
5. **Commit** → Changes committed
6. **Response** → Handler responds to comment

## Configuration Management

Configuration is loaded from:
1. Environment variables (highest priority)
2. Configuration file (`config.yaml`)
3. Default values

Configuration structure:
```python
class Config:
    bot: BotConfig
    github: GitHubConfig
    gitlab: GitLabConfig  # Optional
    bitbucket: BitBucketConfig  # Optional
    ai_agents: Dict[str, AgentConfig]
```

## Error Handling Strategy

1. **Transient Errors**: Retry with exponential backoff
2. **Permanent Errors**: Log and notify (issue comment)
3. **Agent Failures**: Fallback or request clarification
4. **API Rate Limits**: Queue and retry later

## Testing Strategy

- **Unit Tests**: Each component tested in isolation
- **Integration Tests**: Test component interactions
- **E2E Tests**: Test full workflow with mock Git platform
- **Mock Platform**: Mock Git platform API for testing

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
- `AI_AGENT_TYPE` - AI agent to use (cursor_cli)
