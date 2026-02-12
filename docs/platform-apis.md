# Git Platform APIs - Authentication and Adapter Development

This document describes how to authenticate and which API endpoints to use for GitHub, GitLab, and Bitbucket. It is intended for developing the platform adapters (`coddy/adapters/`).

## Overview: Tokens Required

For the bot to work with each platform, you need API tokens (or equivalent) with sufficient permissions:

| Platform   | Token / credential type        | Where to create / obtain |
|-----------|---------------------------------|---------------------------|
| GitHub    | Personal Access Token (PAT) or GitHub App token | GitHub: Settings → Developer settings → Personal access tokens (or GitHub App) |
| GitLab    | Personal / Project / Group Access Token       | GitLab: User → Preferences → Access Tokens (or Project/Group settings) |
| Bitbucket | API Token (recommended) or App password       | Bitbucket: Personal settings → App passwords or API tokens |

Tokens must be stored securely (environment variables or secrets). Never commit them to the repository.

---

## GitHub

### Documentation

- **REST API**: https://docs.github.com/en/rest
- **Authentication**: https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api
- **Personal access tokens**: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token
- **Webhooks**: https://docs.github.com/en/webhooks

### Authentication

- **Method**: Send token in the `Authorization` header.
- **Format**: `Authorization: Bearer YOUR_TOKEN` or `Authorization: token YOUR_TOKEN`.
- **Headers**: Use `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28` (or current version).
- **Token types**:
  - **Personal Access Token (classic)**: Requires OAuth scopes (e.g. `repo`, `read:org`).
  - **Fine-grained PAT**: Repository and permission-based; choose "Contents" (read/write), "Issues" (read/write), "Pull requests" (read/write), "Metadata" (read).
- Failed or missing auth: `401 Unauthorized`; after many failures, `403 Forbidden` (temporary lockout).

### Base URL

- `https://api.github.com` (use `GITHUB_API_URL` for enterprise).

### Key Endpoints for the Bot

| Operation | Method | Endpoint |
|----------|--------|----------|
| Get issue | GET | `/repos/{owner}/{repo}/issues/{issue_number}` |
| List issues (e.g. assigned to user) | GET | `/issues?filter=assigned` (authenticated user) or `/repos/{owner}/{repo}/issues` |
| Update issue (incl. labels, body) | PATCH | `/repos/{owner}/{repo}/issues/{issue_number}` |
| Add assignees | POST | `/repos/{owner}/{repo}/issues/{issue_number}/assignees` body: `{"assignees": ["login1", "login2"]}` |
| Remove assignees | DELETE | `/repos/{owner}/{repo}/issues/{issue_number}/assignees` body: `{"assignees": ["login"]}` |
| Set labels on issue | PUT | `/repos/{owner}/{repo}/issues/{issue_number}/labels` body: `{"labels": ["label1", "label2"]}` |
| Add labels | POST | `/repos/{owner}/{repo}/issues/{issue_number}/labels` body: `{"labels": ["label1"]}` |
| Create comment on issue | POST | `/repos/{owner}/{repo}/issues/{issue_number}/comments` body: `{"body": "text"}` |
| List issue comments | GET | `/repos/{owner}/{repo}/issues/{issue_number}/comments` |
| Create branch (create ref) | POST | `/repos/{owner}/{repo}/git/refs` body: `{"ref": "refs/heads/branch-name", "sha": "<commit_sha>"}` |
| Get default branch / repo | GET | `/repos/{owner}/{repo}` (use `default_branch`) |
| Create pull request | POST | `/repos/{owner}/{repo}/pulls` body: `{"title", "head", "base", "body"}` |
| Get pull request | GET | `/repos/{owner}/{repo}/pulls/{pull_number}` |
| List PR review comments | GET | `/repos/{owner}/{repo}/pulls/{pull_number}/comments` |
| Reply to review comment | POST | `/repos/{owner}/{repo}/pulls/{pull_number}/comments` body: `{"body", "in_reply_to": comment_id}` |
| List reviews | GET | `/repos/{owner}/{repo}/pulls/{pull_number}/reviews` |

Note: In GitHub, every pull request is an issue; issue number and pull number are the same for a PR. Use `pull_request` key in issue response to detect PR.

### Webhooks

- **Payload**: JSON; signature in header `X-Hub-Signature-256` (HMAC SHA-256 of body using webhook secret).
- **Events**: `issues` (opened, closed, assigned, edited), `issue_comment`, `pull_request`, `pull_request_review`, `pull_request_review_comment`.
- **Assignment**: On `issues.assigned`, payload includes `assignee`; compare with bot user login to trigger work.

### Rate limits

- Authenticated: 5000 requests/hour (check `X-RateLimit-*` headers). Use conditional requests (`If-None-Match`, `If-Modified-Since`) where possible.

---

## GitLab

### Documentation

- **REST API**: https://docs.gitlab.com/ee/api/
- **Authentication**: https://docs.gitlab.com/ee/api/rest/authentication.html
- **Issues API**: https://docs.gitlab.com/ee/api/issues.html
- **Merge requests API**: https://docs.gitlab.com/ee/api/merge_requests.html
- **Notes (comments)**: https://docs.gitlab.com/ee/api/notes.html
- **Webhooks**: https://docs.gitlab.com/ee/user/project/integrations/webhooks.html

### Authentication

- **Method 1 (recommended)**: Header `PRIVATE-TOKEN: <your_access_token>`.
- **Method 2**: `Authorization: Bearer <your_access_token>`.
- **Token types**: Personal access token, project access token, or group access token. Create under User → Preferences → Access Tokens (scopes: `api`, or minimal: `read_api`, `write_repository` and issue/MR scopes as needed).
- Invalid or missing auth: `401 Unauthorized`.

### Base URL

- GitLab.com: `https://gitlab.com/api/v4`
- Self-hosted: `https://gitlab.example.com/api/v4`

### Project and issue identification

- **Project ID**: Numeric `id` or URL-encoded path `namespace%2Fproject`.
- **Issue**: Identified by project + **IID** (issue iid), not global ID. Merge requests also use **IID** per project.

### Key Endpoints for the Bot

| Operation | Method | Endpoint |
|----------|--------|----------|
| Get issue | GET | `/projects/{id}/issues/{issue_iid}` |
| List project issues | GET | `/projects/{id}/issues` (filter: `assignee_username`, `labels`, `state`) |
| Update issue (assignees, labels, etc.) | PUT | `/projects/{id}/issues/{issue_iid}` body: `assignee_ids[]`, `labels` (comma-separated) |
| Create issue note (comment) | POST | `/projects/{id}/issues/{issue_iid}/notes` body: `{"body": "text"}` |
| List issue notes | GET | `/projects/{id}/issues/{issue_iid}/notes` |
| Create branch | POST | `/projects/{id}/repository/branches` body: `{"branch": "name", "ref": "main"}` |
| Get project (default branch) | GET | `/projects/{id}` |
| Create merge request | POST | `/projects/{id}/merge_requests` body: `{"source_branch", "target_branch", "title", "description"}` |
| Get merge request | GET | `/projects/{id}/merge_requests/{mr_iid}` |
| List MR notes (comments) | GET | `/projects/{id}/merge_requests/{mr_iid}/notes` |
| Create MR note | POST | `/projects/{id}/merge_requests/{mr_iid}/notes` body: `{"body"}` or reply: `{"body", "parent_id": note_id}` |
| List MR "discussions" (threads) | GET | `/projects/{id}/merge_requests/{mr_iid}/discussions` |
| Reply in discussion | POST | `/projects/{id}/merge_requests/{mr_iid}/discussions/{discussion_id}/notes` |

Assignees: use `assignee_ids` (array of user IDs) or single `assignee_id`. For "bot assigned" trigger, filter issues by `assignee_username` equal to bot's username or use webhook payload.

### Webhooks

- **Secret**: Configure in project/group webhook; verify using `X-Gitlab-Token` (or similar) if documented for your version.
- **Events**: `Issue events`, `Merge request events`, `Note events` (comments). Payload includes `object_attributes` and `assignees` for issues.

### Pagination

- Default 20 per page; use `page` and `per_page` (max 100).

---

## Bitbucket Cloud

### Documentation

- **REST API intro**: https://developer.atlassian.com/cloud/bitbucket/rest/intro/
- **Authentication**: https://developer.atlassian.com/cloud/bitbucket/rest/intro/#authentication
- **Issue tracker**: https://developer.atlassian.com/cloud/bitbucket/rest/api-group-issue-tracker/
- **Pull requests**: https://developer.atlassian.com/cloud/bitbucket/rest/api-group-pullrequests/
- **Webhooks**: API group Webhooks on same portal

### Authentication

- **API Token (recommended)**: Basic HTTP Auth; **username** = Atlassian account email, **password** = API token.
  `Authorization: Basic base64(email:api_token)`.
- **App passwords** (deprecated): Same Basic Auth with app password as password.
- **OAuth 2.0**: `Authorization: Bearer <access_token>`. Tokens expire; use refresh token for long-running bots.
- Create API token: Bitbucket → Personal settings → API tokens; set scopes (e.g. repository read/write, pullrequest read/write, issue read/write).

### Base URL

- `https://api.bitbucket.org/2.0`

### Repository and workspace

- **Path**: Repositories and most resources are under `/repositories/{workspace}/{repo_slug}`.
- **Workspace**: User or team slug; **repo_slug**: repository slug (not full name).

### Key Endpoints for the Bot

| Operation | Method | Endpoint |
|----------|--------|----------|
| Get issue | GET | `/repositories/{workspace}/{repo_slug}/issues/{issue_id}` |
| List issues | GET | `/repositories/{workspace}/{repo_slug}/issues` (filter, pagination) |
| Update issue | PUT | `/repositories/{workspace}/{repo_slug}/issues/{issue_id}` (body: title, content, etc.; assignee may be in different endpoint) |
| List / add assignees | GET/PUT | Check Issue tracker API for assignee endpoints (may be under issue or workspace users) |
| Add comment on issue | POST | Issue tracker API: comments resource for issue (exact path in docs) |
| Create branch | POST | `/repositories/{workspace}/{repo_slug}/refs/branches` body: `{"name", "target": {"hash": "commit_or_branch"}}` |
| Get repo (default branch) | GET | `/repositories/{workspace}/{repo_slug}` |
| Create pull request | POST | `/repositories/{workspace}/{repo_slug}/pullrequests` body: `{"title", "source": {"branch": {"name": "branch"}}, "destination": {"branch": {"name": "main"}}, "description"}` |
| Get pull request | GET | `/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}` |
| List PR comments | GET | `/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments` (or activity/diff endpoints) |
| Reply to PR comment | POST | Use same comments resource or thread reply as per Bitbucket docs |

Note: Bitbucket issue IDs can be numeric; pull request ID is also numeric. Assignees and labels may use different endpoints or request shapes - refer to the Issue tracker and Pull requests API groups for the exact schema.

### Webhooks

- Configure at repository or workspace level; verify payload with configured secret (see Bitbucket webhook docs for signature header).

### Pagination

- Bitbucket uses `page` and `pagelen`; responses include `next` link.

---

## Polling (Scheduler)

When webhooks cannot be configured, the **Scheduler** periodically calls the platform API to discover:

1. **Issues assigned to the bot** - to start work on newly assigned issues
2. **New comments on issues** the bot is working on - to take user messages into account (re-read issue + comments, then continue or clarify)
3. **New comments and reviews on PRs/MRs** the bot opened - to process review feedback

Adapters must support:

- **List issues assigned to user**: For the authenticated bot user, list open issues where the bot is in assignees (per repo or across repos, depending on config). Used to detect new assignments since last run.
- **List issue comments (incremental)**: For a given issue, list comments optionally filtered by `since` (timestamp or ISO date) so the scheduler only fetches new comments since last poll.
- **List PR/MR comments (incremental)**: Same idea for pull/merge request comments and review threads; use `since` or sort by `updated_at` and track last-seen id/timestamp to avoid reprocessing.

### GitHub (scheduler)

| What | Endpoint / approach |
|------|----------------------|
| Issues assigned to bot | `GET /repos/{owner}/{repo}/issues?state=open&assignee={bot_login}` or `GET /issues?filter=assigned` (authenticated as bot) |
| Issue comments since | `GET /repos/{owner}/{repo}/issues/{issue_number}/comments?since={ISO8601}` |
| PR comments | `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments` (no `since`; filter by `created_at` or `updated_at` in response, or use `GET .../issues/{pull_number}/comments?since=...` since PR is an issue) |
| PR review list | `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` |

### GitLab (scheduler)

| What | Endpoint / approach |
|------|----------------------|
| Issues assigned to bot | `GET /projects/{id}/issues?state=opened&assignee_username={bot_username}` |
| Issue notes (comments) | `GET /projects/{id}/issues/{issue_iid}/notes` (sort by `updated_at`, filter client-side by timestamp since last poll) |
| MR notes / discussions | `GET /projects/{id}/merge_requests/{mr_iid}/notes` or `.../discussions` (filter by updated_at) |

### Bitbucket (scheduler)

| What | Endpoint / approach |
|------|----------------------|
| Issues | List repo issues; filter by assignee if API supports it; otherwise list and filter client-side |
| Issue comments | Issue tracker API: list comments for issue; use pagination and filter by date |
| PR comments | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments` (filter by date if needed) |

Store last poll time (or last-seen comment id) per resource (repo, issue, PR) to avoid duplicate work and respect rate limits by not over-fetching.

---

## Mapping: Same Operation Across Platforms

Use this to implement a single interface in the adapter (e.g. `get_issue`, `set_issue_labels`, `create_pr`).

| Logical operation        | GitHub | GitLab | Bitbucket |
|--------------------------|--------|--------|-----------|
| Get issue                | GET repo issue by number | GET project issue by IID | GET repo issue by id |
| List issues assigned to  | GET repo issues?assignee= | GET project issues?assignee_username= | List issues, filter assignee |
| List issue comments      | GET issue comments?since= | GET issue notes (sort/filter by date) | Issue comments API |
| List assignees on issue  | In issue response `assignees` | In issue `assignees` / `assignee_ids` | Issue or separate assignee API |
| Set issue labels         | PUT/POST issue labels | PUT issue with `labels` | PUT issue or labels endpoint |
| Add issue comment        | POST issue comments | POST issue notes | POST issue comments |
| Create branch            | POST git/refs | POST repository/branches | POST refs/branches |
| Create PR/MR             | POST pulls | POST merge_requests | POST pullrequests |
| List PR/MR comments      | GET pulls comments, reviews | GET MR notes or discussions | GET pullrequests comments |
| Reply to review comment  | POST pulls comments with in_reply_to | POST MR discussion note with parent_id | POST comment reply |

Repo identifier: GitHub `owner/repo`; GitLab `project id` (numeric or path); Bitbucket `workspace/repo_slug`.

---

## Adapter Development Guide

### Goals

- **Unified interface**: All platform-specific code lives in adapters; the rest of the app uses the abstract `GitPlatformAdapter` (see `docs/system-specification.md`).
- **Same operations**: Each adapter implements the same methods (get issue, set labels, create branch, create PR, comment, reply to review).
- **Token handling**: Adapter receives token (or credentials) via configuration; never log or expose tokens.
- **Errors**: Map platform HTTP/API errors to common exceptions (e.g. `GitPlatformError`) with clear messages.

### Implementation checklist per platform

1. **Config**: Add platform section in `config.example.yaml` (e.g. `github.token`, `gitlab.token`, `bitbucket.api_token` or `bitbucket.username` + `bitbucket.api_token` for Basic).
2. **Auth in requests**:
   - GitHub: `Authorization: Bearer {token}`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version`.
   - GitLab: `PRIVATE-TOKEN: {token}` or `Authorization: Bearer {token}`.
   - Bitbucket: `Authorization: Basic base64(email:api_token)` for API token.
3. **Repo id**: Parse `owner/repo` (GitHub), resolve project id (GitLab), `workspace/repo_slug` (Bitbucket).
4. **Issue id**: GitHub/Bitbucket often use numeric issue number; GitLab uses project + IID.
5. **Labels**: GitHub: list of label names; GitLab: comma-separated or array; Bitbucket: check Issue API for label format.
6. **Webhooks**: Implement signature verification (GitHub: HMAC SHA-256; GitLab/Bitbucket: see their docs) and route events to the same internal events (e.g. "issue assigned to bot", "MR comment").
7. **Scheduler (polling)**: Implement `list_issues_assigned_to`, `get_issue_comments(repo, issue_number, since=...)`, and optional `since` for `get_pr_comments` so the scheduler can poll for new assignments and new user messages without webhooks. See "Polling (Scheduler)" section above.
8. **Rate limits**: Respect `X-RateLimit-*` (GitHub), GitLab/Bitbucket limits; add retries with backoff and optional queuing.
9. **Tests**: Use mocks or recorded responses for API calls; optional integration tests with test repo and token in env.

### References in this repo

- Abstract interface and data models: `docs/system-specification.md` (Git Platform Adapter, Data Models).
- Architecture and layer order: `docs/architecture.md`, `.cursor/rules/architecture.mdc`.
- Implementation order: `.cursor/rules/implementation-order.mdc`.
