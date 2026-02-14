# Docker Compose and Secrets

Coddy runs as two services: **observer** (webhook server, sets issue status in `.coddy/issues/`) and **worker** (dry-run stub: reads queued issues, writes empty PR YAML). They share a **workspace** volume (sources and `.coddy/` with issues and PRs).

## First run

1. **Create secrets and config** (creates `.secrets/` and `config.yaml` from templates):

   ```bash
   chmod +x scripts/setup-docker-secrets.sh
   ./scripts/setup-docker-secrets.sh
   ```

2. **Replace placeholders with real values** (never commit `.secrets/`):

   - Edit `.secrets/github_token` - put your GitHub Personal Access Token
   - Edit `.secrets/webhook_secret` - put the secret you configured in GitHub webhook
   - Edit `config.yaml`: set `webhook.enabled: true`, and under `ai_agents.cursor_cli` set `working_directory: /app/workspace` so both containers use the shared workspace.

3. **Workspace (repo)**
   The worker needs the target repo on disk to run git and the Cursor CLI. Either:
   - Copy `docker-compose.dist.yaml` to `docker-compose.yaml` and add a bind mount for your repo, e.g. under `coddy-worker` and `coddy-daemon` (observer service):
     ```yaml
     volumes:
       - ./config.yaml:/app/config.yaml:ro
       - ./path-to-your-repo:/app/workspace
     ```
     (remove the `coddy-workspace` named volume for those services if you use a bind mount), or
   - Use the default `coddy-workspace` volume and clone the repo into it (e.g. via an init container or one-off run).

4. **Start the bot**:

   ```bash
   docker compose -f docker-compose.dist.yaml up -d
   ```
   Or copy `docker-compose.dist.yaml` to `docker-compose.yaml`, adjust volumes if needed, then:
   ```bash
   docker compose up -d
   ```

5. **Check**:

   ```bash
   curl http://localhost:8000/health
   docker compose logs -f coddy-daemon
   docker compose logs -f coddy-worker
   ```

## How secrets work

- Docker Compose mounts each secret file into the container at `/run/secrets/<name>`.
- The app is given `GITHUB_TOKEN_FILE=/run/secrets/github_token` and `WEBHOOK_SECRET_FILE=/run/secrets/webhook_secret`.
- The app reads the token/secret from that path and never expects them in the image or in `config.yaml`.

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
- Set `bot.github_username` in config (e.g. the GitHub user that runs the bot) so the bot ignores its own comments and only reacts to assignees and user confirmations.
- **Plan on assignment**: when the bot is assigned to an issue (webhook), the observer runs the planner immediately and posts a plan, then waits for user confirmation. See [dialog-template.md](dialog-template.md) for the plan/confirmation flow.

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
