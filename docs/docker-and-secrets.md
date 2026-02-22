# Docker Compose and Secrets

Coddy runs as two services: **observer** (webhook server, sets issue status in `.coddy/issues/`) and **worker** (dry-run stub: reads queued issues, writes empty PR YAML). They share a **workspace** volume (sources and `.coddy/` with issues and PRs).

## First run

1. **Create secrets and config** (creates `.secrets/` and `config.yaml` from templates):

   ```bash
   chmod +x scripts/setup-docker-secrets.sh
   ./scripts/setup-docker-secrets.sh
   ```

2. **Replace placeholders with real values** (never commit `.secrets/`):

   - Edit `.secrets/github_token` - put your GitHub Personal Access Token **with push access** to the repo (see [GitHub token (push access)](#github-token-push-access) below).
   - Edit `.secrets/webhook_secret` - put the secret you configured in GitHub webhook
   - Edit `.secrets/cursor_agent_token` - put your Cursor User API Key (required for worker; observer does not run the agent)
   - Edit `config.yaml`: set `webhook.enabled: true` and `bot.workspace_path: /app/workspace` (or set env `BOT_WORKSPACE_PATH=/app/workspace`) so both containers use the same workspace.
   - Docker Compose sets `BOT_WORKSPACE_PATH=/app/workspace` so that `.coddy/` (issues, PRs) is created inside the workspace volume, not in the container cwd.

3. **SSH for git (fetch/push)**
   If the workspace repo uses an SSH remote (`git@github.com:...`), the worker (and observer) need access to your SSH keys and `known_hosts`. The dist compose mounts the host `.ssh` directory read-only into the container:
   - `${HOME}/.ssh` → `/home/coddy/.ssh:ro`
   - Ensure `HOME` is set when you run `docker compose` (normal when run from your shell), or set `CODDY_SSH_DIR` in `.env` to the path of your `.ssh` directory.
   - Without this mount, `git fetch` / `git push` will fail with "Host key verification failed" or "Permission denied (publickey)".

4. **Workspace (repo)**
   The worker needs the target repo on disk to run git and the Cursor CLI. Either:
   - Copy `docker-compose.dist.yaml` to `docker-compose.yaml` and add a bind mount for your repo, e.g. under `coddy-worker` and `coddy-daemon` (observer service):
     ```yaml
     volumes:
       - ./config.yaml:/app/config.yaml:ro
       - ./path-to-your-repo:/app/workspace
     ```
     (remove the `coddy-workspace` named volume for those services if you use a bind mount), or
   - Use the default `coddy-workspace` volume and clone the repo into it (e.g. via an init container or one-off run).

5. **Start the bot**:

   ```bash
   docker compose -f docker-compose.dist.yaml up -d
   ```
   Or copy `docker-compose.dist.yaml` to `docker-compose.yaml`, adjust volumes if needed, then:
   ```bash
   docker compose up -d
   ```

6. **Check**:

   ```bash
   curl http://localhost:8000/health
   docker compose logs -f coddy-daemon
   docker compose logs -f coddy-worker
   ```

## GitHub token (push access)

The app uses the GitHub token to create branches, push commits, open PRs, and post comments. **Do not forget** to create a token that has **write (push) access** to the repository; otherwise the worker will create a branch via API but `git fetch` / `git push` (or API push) will fail.

### How to create the token

1. **Open GitHub → Settings → Developer settings → Personal access tokens**
   - Classic: [github.com/settings/tokens](https://github.com/settings/tokens)
   - Fine-grained: [github.com/settings/tokens?type=fine_grained](https://github.com/settings/tokens?type=fine_grained)

2. **Create a token with access to the target repo**
   - **Classic token**: enable scope **repo** (full control of private repositories), or at least **public_repo** for public repos.
   - **Fine-grained token**: grant **Contents** (Read and write), **Pull requests** (Read and write), **Issues** (Read and write), **Metadata** (Read) for the repository Coddy works on.

3. **Put the token into the secret file**
   - Copy the token and write it into `.secrets/github_token` (no trailing newline):
     ```bash
     echo -n "YOUR_GITHUB_TOKEN" > .secrets/github_token
     ```
   - Or edit `.secrets/github_token` and replace the placeholder.

Without a token that can push, the bot will not be able to push branches or open PRs after working on an issue.

## How secrets work

- Docker Compose mounts each secret file into the container at `/run/secrets/<name>`.
- The app is given `GITHUB_TOKEN_FILE` and `WEBHOOK_SECRET_FILE`; the worker also gets `CURSOR_AGENT_TOKEN_FILE` (only the worker runs the planner and agent).
- The app reads the token/secret from that path and never expects them in the image or in `config.yaml`.

## Running the worker without exposing secrets

The **workspace** is mounted into the container as a volume. Whatever is inside the workspace path on the host is visible inside the container (e.g. to anyone who can `docker exec` into it or to other processes). To avoid exposing secrets:

1. **Do not use as workspace a directory that contains `.secrets/`.**
   If you set `REPO_PATH=.` (default) and your current directory is the Coddy repo (where `.secrets/` lives), then `/app/workspace` in the container will contain `.secrets/` and tokens can be read.
   **Use a dedicated workspace path instead:**
   - Clone the **target repo** (the one Coddy works on) into a separate directory, e.g. `~/coddy-workspace` or `/tmp/my-repo`, and set `REPO_PATH` to that path. That directory must not contain `.secrets/`.
   - Example: `REPO_PATH=/home/user/coddy-workspace docker compose -f docker-compose.dist.yaml up -d`, where `/home/user/coddy-workspace` is a clone of the target repo and has no `.secrets/`.

2. **Secrets only via env or Docker/Kubernetes secrets.**
   Pass tokens via `GITHUB_TOKEN`, `CURSOR_AGENT_TOKEN` or `*_FILE` (e.g. `GITHUB_TOKEN_FILE=/run/secrets/github_token`). Do not put secret files inside the workspace; keep `.secrets/` only on the host and let Docker Compose mount them as Docker secrets into `/run/secrets/`.

3. **CI or shared runners.**
   Run the worker with a workspace that is a clean checkout of the target repo (no `.secrets/` in that checkout). Inject tokens via environment or your platform’s secret store (e.g. GitHub Actions secrets, Kubernetes secrets).

## Cursor Agent token (optional)

For the Cursor CLI agent to call the API, it needs a token. The setup script creates `.secrets/cursor_agent_token` with a placeholder; `docker-compose.yml` mounts it. Replace the placeholder with your Cursor Agent token to enable the agent, or leave it as is if you use `stub_agent`. Alternatively set `CURSOR_AGENT_TOKEN` in the environment (e.g. in a non-committed `.env`).

### How to obtain the Cursor API key

The token is **not** stored anywhere on your system by default. You must create a **User API Key** in the Cursor dashboard and then put it into the secret file for Docker.

1. **Open the Cursor dashboard**
   Go to [cursor.com/dashboard](https://cursor.com/dashboard) and sign in.

2. **Open Integrations and User API Keys**
   In the dashboard, go to **Integrations → User API Keys**, or open:
   [cursor.com/dashboard?tab=integrations](https://cursor.com/dashboard?tab=integrations)

3. **Create a User API Key**
   Create a new key and copy it. This is the token used for the headless Cursor CLI (and for Coddy in Docker).

4. **Put the key into the Docker secret**
   Either overwrite the secret file with the key (no trailing newline):
   ```bash
   echo -n "YOUR_COPIED_KEY" > .secrets/cursor_agent_token
   ```
   or edit `.secrets/cursor_agent_token` and replace the placeholder with the key.

The app passes this token to the Cursor CLI as the `CURSOR_API_KEY` environment variable. If you only use `agent login` on the host, that stores credentials locally in Cursor's config but does not give you a file to copy; for Docker you need the **User API Key** from the dashboard.

## Webhook and bot behaviour

- In the GitHub repo webhook settings, enable the **issue_comment** event so the bot receives user replies (e.g. "yes" / "да") after posting the plan.
- Set `bot.username` in config (platform account name) so the bot ignores its own comments and only reacts to assignees and user confirmations.
- **Plan on assignment**: when the bot is assigned to an issue (webhook), the observer sets status pending_plan; the worker builds the plan and writes it to the issue file; the observer poll posts it to the issue and waits for user confirmation. See [dialog-template.md](dialog-template.md) for the plan/confirmation flow.

## Config file

The `config.yaml` file is mounted from the host via bind mount in `docker-compose.yml`. Always copy `config.example.yaml` to `config.yaml` before first run - the example contains all available settings with defaults.

**Important**: Never commit `config.yaml` to the repository (it's in `.gitignore`). The `config.example.yaml` stays in the repo as a template with all options documented.

## CLI in container

```bash
# Validate config
docker compose run --rm coddy-daemon python -m coddy.main --check

# Run observer (default; subcommand "daemon" is accepted as alias)
docker compose run --rm coddy-daemon python -m coddy.main observer --config /app/config.yaml

# Run worker (one task then exit)
docker compose run --rm coddy-worker python -m coddy.main worker --config /app/config.yaml --once
```
