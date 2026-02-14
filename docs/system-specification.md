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

### Two-Module Design

Coddy is split into two runnable applications that work together:

1. **Observer (coddy observer)** - Task intake and webhooks
   - Listens for webhook events from Git platforms (e.g. GitHub: issue assigned, issue comment, PR review comment).
   - When the bot is assigned to an issue, the observer creates/updates the issue in `.coddy/issues/{n}.yaml` and immediately runs the **planner** (posts a plan and sets status **waiting_confirmation**). When the user confirms via a comment, the observer sets issue status to **queued** (worker picks from .coddy/issues/). See [issue-flow.md](issue-flow.md).
   - Tasks are issues with status=queued in `.coddy/issues/`. Worker picks from them and sets status to done or failed. PRs are tracked in `.coddy/prs/{pr_number}.yaml` with status open/merged/closed. On PR merge or close (webhook), PR status is updated; on issue close, issue status is set to closed.
   - The observer is long-running: HTTP server for webhooks, optional poll loop, and (if desired) a small loop that watches the queue and logs or notifies. It does not execute the development loop.

2. **Worker (coddy worker)** - Development and commit loop (Ralph-style)
   - Polls the task queue (or is triggered by the observer). Picks one task (e.g. "issue 42"), then runs the **ralph loop** for that issue.
   - **Ralph loop** (per issue):
     - Load issue and comments from the platform adapter; evaluate data sufficiency. If insufficient: post clarification comment, set label `stuck`, and exit (task can be re-queued when user comments).
     - Create branch from default (e.g. `42-add-user-login`), checkout, and set label `in progress`.
     - Write task file `.coddy/task-{issue_number}.yaml` with issue title, body, comments, and instructions: plan, clarify if needed, write tests, write code, run tests/linter, commit with `#{number} ...`, and when everything is done write `.coddy/pr-{issue_number}.yaml` (YAML with key `body` for PR description including "Closes #N").
     - **Loop**: Run the AI agent (e.g. Cursor CLI) with the task YAML. After each run, check: (1) if `.coddy/pr-{issue_number}.yaml` exists (with `body`), break and create PR; (2) if the task YAML contains key `agent_clarification`, post it to the issue, set `stuck`, and exit; (3) otherwise repeat up to a configured max iterations (e.g. 10). Each iteration is a fresh agent run; context is preserved via git history and the task/report files.
     - When the PR report file is written: commit and push any remaining changes, create the pull request using the report as body, set label `review`, switch back to the default branch.
   - Code is written **only** by the AI agent (Cursor CLI in the initial version); the worker only orchestrates the loop, git, and platform API (create branch, create PR, labels, comments).
   - After handling one task, the worker picks the next from the queue or exits (e.g. when run as a one-shot or by a process manager that restarts it).

This separation allows:
- Scaling: run one observer and one or more workers.
- Resilience: if the worker crashes during the loop, the observer keeps receiving events and can re-enqueue; the queue is on disk.
- Clarity: observer = "what to do"; worker = "do the development loop".

### High-Level Components (refined)

1. **Git Platform Adapter Layer** (`coddy.observer.adapters`) - Abstract interface for GitHub/GitLab/BitBucket.
2. **Observer** (`coddy.observer.run`): Webhook server only; on assignment runs planner and enqueues tasks (issue status in .coddy/issues/); does not run the development loop.
3. **Tasks** - Issues in `.coddy/issues/` with status=queued; worker picks by issue number and sets status done/failed. PRs in `.coddy/prs/` with status merged/closed updated from webhooks.
4. **Worker** (`coddy.worker.run`) - Reads queue; for each task runs sufficiency check, branch creation, ralph loop (repeated agent runs until PR report YAML or agent_clarification), then PR creation and labels.
5. **AI Agent Interface** (`coddy.worker.agents`) - Pluggable interface; Cursor CLI agent runs one iteration per call (read task YAML, implement, optionally write PR report YAML or add agent_clarification to task YAML).
6. **Review Handler** (`coddy.observer.pr.review_handler`) - Processes PR review comments (triggered by webhook; uses agent for fixes and reply).

### Technology Stack

- **Language**: Python 3.11+
- **Containerization**: Docker
- **Git Platforms**: GitHub (primary), GitLab, BitBucket (planned)
- **AI Agents**: Cursor CLI (initial), extensible to other agents

## Core Workflow

### Issue Processing Flow

**From assignment to queue**: When the bot is assigned to an issue (webhook), it is stored in `.coddy/issues/{issue_number}.yaml` and the planner runs immediately (post plan, status **waiting_confirmation**). When the user replies affirmatively (e.g. "yes", "да"), the issue status is set to **queued** and the worker can pick it up from .coddy/issues/. See [issue-flow.md](issue-flow.md) for the full step-by-step and [dialog-template.md](dialog-template.md) for the plan/confirmation dialog.

1. **Trigger (Bot Assigned or MR/PR Referenced)**
   - **Option A**: User assigns the bot as assignee on an issue; a **webhook** delivers the event. The observer stores the issue and runs the planner (posts plan, waiting_confirmation); once the user confirms, the issue is **queued** for processing.
   - **Option B**: User provides an MR/PR number (e.g. in a comment or command); the bot loads that MR/PR and works on it (e.g. review feedback, or continuing work).
   - Only issues/MRs explicitly assigned or referenced are processed; the bot does not auto-pick every new issue.
   - **New messages in an issue**: If a user adds a comment to an issue the bot is working on, that input must be taken into account (see "Issue comments" below). The bot re-reads the issue body and all comments before continuing or when deciding next steps.

2. **Issue Analysis and Data Sufficiency**
   - Bot reads issue description (title, body) and all issue comments.
   - Bot decides whether the information is **sufficient** to proceed (e.g. clear scope, acceptance criteria, or enough context to implement).
   - **If data is insufficient**:
     - Bot posts a **comment in the issue** asking the user to clarify (what to do, what is expected, which files/repo area, etc.).
     - Bot sets issue label `stuck` (or equivalent "needs clarification") and does **not** create a branch or generate code. Work stops until the user provides more information (new comment); then the bot re-reads the issue and re-evaluates sufficiency.
   - **If data is sufficient**:
     - Bot sets label `in progress`.
     - Optionally writes a short feature specification in issue comments.
     - Proceeds to step 3 (Code Generation).

3. **Code Generation (Ralph loop, in the worker)**
   - Worker creates branch with format: `{number}-short-issue-description-2-3-words`
     - **Branch must be created from the default branch** (e.g. main/master). Before creating: checkout default branch, pull latest, then create and switch to the new branch.
     - Example: `42-add-user-login`
   - Worker writes `.coddy/task-{issue_number}.yaml` and runs the **agent in a loop** (ralph-style):
     - Each iteration: run Cursor CLI (or other agent) with the task YAML. The agent is instructed to: plan, implement, write tests, run tests/linter, commit with `#{number} Description`, and when done write `.coddy/pr-{issue_number}.yaml` (YAML with key `body`).
     - Worker checks after each run: PR report file present with `body` -> create PR and exit loop; key `agent_clarification` in task YAML -> post to issue, set `stuck`, exit; else repeat up to max iterations.
   - **Commit message format**: `#{number} Description of what was done`
   - Commits are signed with bot identity (configurable).
   - When the loop exits with a PR report: worker commits/pushes if needed, creates the pull request using the report as body, sets label `review`, switches back to the default branch.

4. **Pull Request Creation**
   - Bot creates a Pull Request from the new branch to main/master.
   - PR description includes:
     - **What was done** (summary of changes, list of implemented items)
     - How to test the feature
     - How to use the feature (if applicable)
     - Reference to the original issue
     - A line that closes the issue when the PR is merged (e.g. `Closes #42` or `Fixes #42`)
   - Bot updates issue label to `review`.
   - **Bot switches back to the default branch** so the next run or new issue starts from default (do not leave the repo on the feature branch).

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

- `in progress` - Bot has enough data and is actively working (branch created, code generation in progress)
- `stuck` - Bot asked for clarification (data insufficient); work paused until user responds in the issue
- `review` - Code is ready for review (PR/MR created)
- `done` - Issue is completed and merged

Labels are updated as the workflow progresses: set `stuck` when asking for clarification; set `in progress` when starting implementation; set `review` when PR is opened; set `done` when merged.

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

**Purpose**: Detect when the bot should start work (assignment or MR/PR reference), detect new user messages, and track state. It is fed by the **Webhook Server**.

**Responsibilities**:
- Receive events from webhooks
- When the bot is **assigned** to an issue, queue that issue for processing
- When a **new comment is added to an issue** the bot is working on (or is assignee of), treat it as new input: re-read issue body and all comments, then re-evaluate data sufficiency and either continue work, ask for clarification again, or adjust (e.g. change of scope, or user-provided MR/PR number)
- Optionally: handle user messages that reference an MR/PR number (e.g. "work on MR !42")
- Queue only issues/MRs that are explicitly assigned or referenced
- Track issue and PR state
- Do **not** auto-queue every new issue; full automation is a later phase

**Events Handled** (examples for GitHub):
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

**Purpose**: Orchestrate code generation workflow (invoked only when issue data is sufficient).

**Responsibilities**:
- Prepare context for AI agent (codebase, issue description, comments)
- Create branch with format `{issue_number}-short-description-2-3-words` (English, lowercase, dashes; derived from issue title) and switch to it
- Call AI agent with task; handle agent responses and clarifications
- Manage code changes and commits; push branch to remote
- Create commit messages with format `#{issue_number} Description of what was done`
- Support multiple commits per issue (one per edit session); after edits are done, run final linter and tests, fix and commit if needed until all pass

### PR Manager

**Purpose**: Create and manage pull requests

**Responsibilities**:
- Create PR from current branch to main/master after code generation is complete
- PR description must include **what was done** (summary of changes, list of implemented items), how to test, how to use (if applicable), reference to the original issue, and a line that closes the issue (e.g. `Closes #42` or `Fixes #42`)
- Monitor PR status
- Handle PR updates

### Review Handler

**Purpose**: Process code reviews and implement changes

**Responsibilities**:
- Parse review comments
- Identify requested changes
- Call AI agent to implement fixes
- Commit changes with message format `#{issue_number} Description of what was fixed`
- Respond to comments with explanations

### Webhook Server

**Purpose**: Receive and process webhook events from Git platforms when webhooks can be configured (repository or organization has webhook support and the deploy environment is reachable).

**Responsibilities**:
- Listen for webhook events
- Verify webhook signatures
- Route events to Issue Monitor (or equivalent) and dispatch them to the appropriate handlers
- Handle authentication

Webhooks must be configured for the bot to react to assignments and comments (no polling fallback).

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
3. **Forbidden path - `.secrets/`**: The bot (code agent) must **never** access the `.secrets/` directory under any circumstances. No read, list, write, or any reference to files inside `.secrets/`. Tokens and secrets live there; the agent must not touch this folder.
4. **Code Review**: Generated code should be reviewed before merging
5. **Rate Limiting**: Respect API rate limits for Git platforms
6. **Access Control**: Bot should only have necessary permissions

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
   - **Event source**: Webhooks only; the bot reacts to assignment, new issue comments, and new PR comments via webhooks
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
   - Commit messages: `#{issue_number} Description of what was done`

### Out of Scope for MVP

- Full automation (bot picking up every new issue without assignment)
- GitLab/BitBucket support (use adapter pattern for future)
- Multiple AI agents
- Advanced review handling
- User attribution in commits
- Parallel issue processing
- Advanced error recovery
