# Docker Compose and Secrets

## First run

1. **Create secrets and config** (creates `.secrets/` and `config.yaml` from templates):

   ```bash
   chmod +x scripts/setup-docker-secrets.sh
   ./scripts/setup-docker-secrets.sh
   ```

2. **Replace placeholders with real values** (never commit `.secrets/`):

   - Edit `.secrets/github_token` - put your GitHub Personal Access Token
   - Edit `.secrets/webhook_secret` - put the secret you configured in GitHub webhook
   - Edit `config.yaml` if needed (repository, webhook path, etc.). For Docker, set `webhook.enabled: true` so the HTTP server listens on port 8000 and the health check succeeds.

3. **Start the bot**:

   ```bash
   docker compose up -d
   ```

4. **Check**:

   ```bash
   curl http://localhost:8000/health
   docker compose logs -f coddy
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

## Config file

The `config.yaml` file is mounted from the host via bind mount in `docker-compose.yml`. Always copy `config.example.yaml` to `config.yaml` before first run - the example contains all available settings with defaults.

**Important**: Never commit `config.yaml` to the repository (it's in `.gitignore`). The `config.example.yaml` stays in the repo as a template with all options documented.

## CLI in container

```bash
docker compose run --rm coddy python -m coddy.main --check
docker compose run --rm coddy python -m coddy.main --config /app/config.yaml
```
