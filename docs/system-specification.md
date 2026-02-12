# Coddy Bot - System Specification

## Overview

Coddy (Community driven development) is an autonomous development bot that integrates with Git hosting platforms (GitHub, GitLab, BitBucket) to automate the software development workflow. The bot works on issues and merge/pull requests when explicitly invoked; it generates code using AI agents, creates pull requests, and responds to code reviews.

## Trigger Model (How the Bot Is Invoked)

The bot does **not** automatically process every new issue. Work is triggered in one of two ways:

1. **Assign bot to an issue**  
   A human assigns the bot as the issue assignee. The bot then picks up that issue, writes a specification in the comments, manages labels, implements the task, and opens a PR.  
   *For the initial version, assignment is the primary trigger; full automation (e.g. auto-pick on every new issue) is out of scope.*

2. **Reference an MR/PR**  
   A user gives the bot a merge request or pull request number (e.g. in a comment or a dedicated command). The bot then works on that MR/PR (e.g. implements review feedback, updates description, or continues implementation).

The bot still manages **issue labels** (tags) for any issue it works on: e.g. `in progress`, `stuck`, `review`, `done`.

## Core Concept

- Users create issues; a human **assigns the bot** to an issue (or points the bot at an MR/PR).
- Coddy Bot analyzes the issue/MR, writes a specification in comments when working on an issue, and keeps issue labels up to date.
- The bot generates code using configurable AI agents and creates or updates pull/merge requests.
- Users review code and give feedback in the PR/MR; the bot applies changes and replies in the same place (line comments, PR comments, or review threads).

## Architecture

### High-Level Components

1. **Git Platform Adapter Layer** - Abstract interface for GitHub/GitLab/BitBucket
2. **Issue Monitor** - Watches for new issues and updates
3. **AI Agent Interface** - Pluggable interface for code generation agents (Cursor CLI, etc.)
4. **Code Generator** - Orchestrates AI agents to generate code
5. **PR Manager** - Creates and manages pull requests
6. **Review Handler** - Processes code reviews and comments
7. **Webhook Server** - Receives events from Git platforms when webhooks are configured
8. **Scheduler (Poller)** - When webhooks are not available, periodically polls the platform API for new assignments, issue comments, and PR/MR review comments

### Technology Stack

- **Language**: Python 3.11+
- **Containerization**: Docker
- **Git Platforms**: GitHub (primary), GitLab, BitBucket (planned)
- **AI Agents**: Cursor CLI (initial), extensible to other agents

## Core Workflow

### Issue Processing Flow

1. **Trigger (Bot Assigned or MR/PR Referenced)**
   - **Option A**: User assigns the bot as assignee on an issue; a **webhook** (if configured) or the **scheduler** (polling the API) detects that the bot was assigned, and the issue is queued for processing.
   - **Option B**: User provides an MR/PR number (e.g. in a comment or command); the bot loads that MR/PR and works on it (e.g. review feedback, or continuing work).
   - Only issues/MRs explicitly assigned or referenced are processed; the bot does not auto-pick every new issue.
   - **New messages in an issue**: If a user adds a comment to an issue the bot is working on, that input must be taken into account (see "Scheduler" and "Issue comments" below). The bot re-reads the issue body and all comments before continuing or when deciding next steps.

2. **Issue Analysis**
   - Bot reads issue description and context
   - Bot creates feature specification in issue comments
   - Bot labels issue (e.g., "in progress", "needs clarification")

3. **Code Generation**
   - Bot creates branch: `issue-{number}`
   - Bot switches to branch
   - Bot calls AI agent with issue context
   - Agent generates code following specification
   - Bot commits changes with descriptive messages referencing issue number
   - Commits are signed with bot identity (configurable)

4. **Pull Request Creation**
   - Bot creates PR from branch to main/master
   - PR description includes:
     - Summary of changes
     - How to test the feature
     - How to use the feature
     - Reference to original issue

5. **Review Handling**
   - Bot monitors PR for comments and reviews
   - For each review comment:
     - Bot analyzes requested changes
     - Bot calls AI agent to implement fixes
     - Bot commits changes
     - Bot responds to comment explaining what was fixed
   - Bot responds in appropriate location:
     - Line comments → response in same thread
     - PR comments → response in PR discussion
     - Review comments → response to review

### Issue Labeling (Tags)

The bot manages issue labels (tags) for any issue it works on. Do not forget to set and update these:

- `in progress` - Bot is actively working on the issue
- `stuck` - Bot needs clarification or cannot proceed
- `review` - Code is ready for review (PR/MR created)
- `done` - Issue is completed and merged

Labels are updated as the workflow progresses (e.g. set `in progress` when starting, `review` when PR is opened, `done` when merged).

## Component Specifications

### Git Platform Adapter

**Purpose**: Abstract interface for different Git hosting platforms

**Interface**:
```python
class GitPlatformAdapter(ABC):
    def create_branch(self, repo: str, branch_name: str) -> None
    def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> PR
    def get_issue(self, repo: str, issue_number: int) -> Issue
    def get_issue_assignees(self, repo: str, issue_number: int) -> List[str]  # to detect bot assignment
    def set_issue_labels(self, repo: str, issue_number: int, labels: List[str]) -> None
    def create_comment(self, repo: str, issue_number: int, body: str) -> Comment
    # For scheduler: list issues where bot is assignee; filter by state=open
    def list_issues_assigned_to(self, repo: str, assignee_username: str) -> List[Issue]
    # For scheduler: fetch issue comments (since optional for incremental poll)
    def get_issue_comments(self, repo: str, issue_number: int, since: Optional[datetime] = None) -> List[Comment]
    def get_pr_comments(self, repo: str, pr_number: int, since: Optional[datetime] = None) -> List[Comment]
    def get_pr_reviews(self, repo: str, pr_number: int) -> List[Review]
    def respond_to_review_comment(self, repo: str, pr_number: int, comment_id: int, body: str) -> None
```

**Implementations**:
- `GitHubAdapter` - GitHub API integration
- `GitLabAdapter` - GitLab API integration (planned)
- `BitBucketAdapter` - BitBucket API integration (planned)

### Issue Monitor

**Purpose**: Detect when the bot should start work (assignment or MR/PR reference), detect new user messages, and track state. It is fed by either the **Webhook Server** or the **Scheduler** (or both).

**Responsibilities**:
- Receive events from webhooks (when configured) or from the scheduler (polling)
- When the bot is **assigned** to an issue, queue that issue for processing
- When a **new comment is added to an issue** the bot is working on (or is assignee of), treat it as new input: re-read issue body and all comments, then continue work or adjust (e.g. clarification, change of scope, or user-provided MR/PR number)
- Optionally: handle user messages that reference an MR/PR number (e.g. "work on MR !42")
- Queue only issues/MRs that are explicitly assigned or referenced
- Track issue and PR state
- Do **not** auto-queue every new issue; full automation is a later phase

**Events Handled** (examples for GitHub; scheduler produces equivalent logical events):
- Bot assigned to an issue → queue this issue
- Issue description or title edited (if bot is assignee) → re-evaluate
- Issue closed → stop or mark done
- **New comment on issue** → take into account: update context, possibly re-run specification or continue implementation with new input
- New comment or review on PR/MR the bot is working on → pass to Review Handler
- User references MR/PR number in a comment → queue that MR/PR for work

### AI Agent Interface

**Purpose**: Pluggable interface for code generation agents

**Interface**:
```python
class AIAgent(ABC):
    def generate_code(self, task: Task, context: CodebaseContext) -> CodeChanges
    def improve_code(self, code: str, feedback: str, context: CodebaseContext) -> CodeChanges
    def write_tests(self, code: str, context: CodebaseContext) -> CodeChanges
```

**Implementations**:
- `CursorCLIAgent` - Uses Cursor CLI for code generation
- Future agents can be added by implementing the interface

### Code Generator

**Purpose**: Orchestrate code generation workflow

**Responsibilities**:
- Prepare context for AI agent (codebase, issue description)
- Call AI agent with task
- Handle agent responses and clarifications
- Manage code changes and commits
- Create commit messages with issue references

### PR Manager

**Purpose**: Create and manage pull requests

**Responsibilities**:
- Create PRs with proper descriptions
- Format PR descriptions with testing instructions
- Monitor PR status
- Handle PR updates

### Review Handler

**Purpose**: Process code reviews and implement changes

**Responsibilities**:
- Parse review comments
- Identify requested changes
- Call AI agent to implement fixes
- Commit changes
- Respond to comments with explanations

### Webhook Server

**Purpose**: Receive and process webhook events from Git platforms when webhooks can be configured (repository or organization has webhook support and the deploy environment is reachable).

**Responsibilities**:
- Listen for webhook events
- Verify webhook signatures
- Route events to Issue Monitor (or equivalent) so they are processed like scheduler-produced events
- Handle authentication

When webhooks are **not** available (e.g. no way to register a URL, or no public URL), the **Scheduler** is used instead (or in addition, for redundancy).

### Scheduler (Poller)

**Purpose**: When webhooks cannot be configured, or as a fallback, periodically poll the Git platform API to discover new work and new user input. Ensures the bot still reacts to assignments, new issue comments, and new code review comments.

**Responsibilities**:
- Run on a configurable interval (e.g. every 1–5 minutes)
- **Poll for issues assigned to the bot**: list issues where the bot is in assignees; any newly assigned issue is queued for processing (same as webhook "issues.assigned")
- **Poll for new issue comments**: for each issue the bot is currently working on (or is assignee of), fetch comments since last check; if there are new comments from users, feed them to Issue Monitor so the bot takes them into account (re-read issue + comments, then continue or clarify)
- **Poll for new PR/MR activity**: for each PR/MR the bot has opened or is responsible for, fetch new review comments and general comments since last check; pass new activity to Review Handler
- Store last-seen timestamps or IDs per issue/PR to avoid duplicate processing
- Produce the same logical events as webhooks (e.g. "issue assigned to bot", "new comment on issue #N", "new review comment on PR #M") so Issue Monitor and Review Handler need not care whether the source was webhook or scheduler
- Respect API rate limits (back off or reduce frequency if needed)

**Configuration**: Polling interval, optional enable/disable of webhook vs scheduler (e.g. use only scheduler, only webhooks, or both with deduplication).

## Data Models

### Issue
```python
class Issue:
    number: int
    title: str
    body: str
    author: str
    labels: List[str]
    state: str  # open, closed
    created_at: datetime
    updated_at: datetime
```

### Pull Request
```python
class PR:
    number: int
    title: str
    body: str
    head_branch: str
    base_branch: str
    state: str  # open, closed, merged
    issue_number: Optional[int]
```

### Code Changes
```python
class CodeChanges:
    files: List[FileChange]
    commit_message: str
    issue_number: int
```

### FileChange
```python
class FileChange:
    path: str
    content: str
    action: str  # create, update, delete
```

## Configuration

### Bot Configuration
```yaml
bot:
  name: "Coddy Bot"
  email: "bot@coddy.dev"
  git_platform: "github"  # github, gitlab, bitbucket
  repository: "owner/repo"
  webhook_secret: "secret"
  ai_agent: "cursor_cli"
  
github:
  token: "ghp_..."
  api_url: "https://api.github.com"
  
gitlab:
  token: "glpat-..."
  api_url: "https://gitlab.com/api/v4"
  
bitbucket:
  token: "..."
  api_url: "https://api.bitbucket.org/2.0"
  
ai_agents:
  cursor_cli:
    command: "cursor"
    args: ["generate"]
    timeout: 300
```

## API Tokens and Platform APIs

The bot needs API tokens (or equivalent credentials) for each Git platform it integrates with:

| Platform   | Credential type              | Usage |
|-----------|-------------------------------|-------|
| **GitHub** | Personal Access Token (PAT) or GitHub App token | Send in header: `Authorization: Bearer <token>`. Scopes/permissions: repo, issues, pull requests (read/write as needed). |
| **GitLab** | Personal / Project / Group Access Token | Send in header: `PRIVATE-TOKEN: <token>` or `Authorization: Bearer <token>`. Scopes: e.g. `api` or minimal read/write for repo, issues, merge requests. |
| **Bitbucket** | API Token (recommended) or App password | Basic Auth: username = account email, password = API token. Scopes: repository, pullrequest, issue (read/write as needed). |

Tokens must be stored in environment variables or a secrets store, not in config files committed to the repo. For MVP only GitHub is required; GitLab and Bitbucket tokens are for future adapters.

**Full API reference and adapter development**: See [Platform APIs](platform-apis.md) for:

- Authentication details and base URLs per platform
- Endpoints for issues, assignees, labels, comments, branches, pull/merge requests, and review comments
- Webhook verification and event types
- Mapping of the same logical operation across GitHub, GitLab, and Bitbucket
- Adapter implementation checklist (config, auth, repo/issue IDs, rate limits, tests)

This document is the single source for developing and maintaining the GitHub, GitLab, and Bitbucket adapters.

## Security Considerations

1. **Webhook Verification**: All webhooks must be verified using platform-specific signatures
2. **Token Management**: Git platform tokens stored securely (environment variables, secrets)
3. **Code Review**: Generated code should be reviewed before merging
4. **Rate Limiting**: Respect API rate limits for Git platforms
5. **Access Control**: Bot should only have necessary permissions

## Error Handling

1. **Agent Failures**: If AI agent fails, bot should comment on issue explaining the problem
2. **API Failures**: Retry logic with exponential backoff
3. **Invalid Code**: If generated code has syntax errors, bot should retry or request clarification
4. **Merge Conflicts**: Bot should detect conflicts and request manual resolution

## Future Enhancements

1. **Full Automation**: Bot picks up new issues automatically (e.g. webhook on `issues.opened`) without requiring assignment; for now, a human assigns the bot to an issue or gives an MR/PR number.
2. **Static Analyzer Integration**: Integrate static analyzer into the backend workflow; analyzer can create issues or send bugs that the bot can be assigned to fix.
3. **Multi-Agent Support**: Support for multiple AI agents simultaneously
4. **Test Generation**: Automatic test generation for generated code
5. **Code Quality Checks**: Integration with linters and formatters
6. **Dependency Management**: Automatic dependency updates
7. **Documentation Generation**: Auto-generate documentation for features
8. **User Attribution**: Sign commits with issue author names
9. **Parallel Processing**: Process multiple issues simultaneously
10. **Custom Workflows**: Configurable workflows per repository (git flow, pipelines vary per project)

## Prototype Scope

### Minimum Viable Product (MVP)

For the initial prototype, focus on:

1. **Trigger: Human Assigns Bot**
   - Bot starts work only when a **human assigns the bot to an issue** (or, optionally, when user provides an MR/PR number).
   - No automatic pickup of every new issue; that is left for a later phase.

2. **GitHub Integration Only**
   - Read issues from GitHub, create branches and PRs
   - **Event source**: Webhook when configurable; otherwise **Scheduler** (polling) to detect when the bot is assigned to an issue, new issue comments, and new PR comments
   - When a user adds a message to an issue, the bot must take it into account (re-read issue + comments, then continue or clarify)
   - Create branches and PRs

3. **Issue Tags (Labels)**
   - Bot must set and update issue labels: e.g. `in progress`, `stuck`, `review`, `done` as the workflow progresses.

4. **Cursor CLI Agent**
   - Single AI agent implementation
   - Basic code generation

5. **Core Workflow**
   - Assigned issue → Specification (in comments) → Code → PR, with labels updated along the way
   - Basic review handling (respond to comments, apply changes)

6. **Bot Identity**
   - Commits signed with bot name/email
   - Simple commit messages

### Out of Scope for MVP

- Full automation (bot picking up every new issue without assignment)
- GitLab/BitBucket support (use adapter pattern for future)
- Multiple AI agents
- Advanced review handling
- User attribution in commits
- Parallel issue processing
- Advanced error recovery
