# Docker Compose and Secrets

## First run

1. **Copy config from example**:

   ```bash
   cp config.example.yaml config.yaml
   # Edit config.yaml if needed (repo, webhook settings, etc.)
   ```

2. **Create secret files** (never commit `.secrets/`):

   ```bash
   mkdir -p .secrets
   echo "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN" > .secrets/github_token
   echo "YOUR_WEBHOOK_SECRET"             > .secrets/webhook_secret
   chmod 600 .secrets/github_token .secrets/webhook_secret
   ```

3. **Start the bot**:

   ```bash
   docker compose up -d
   ```

3. **Check**:

   ```bash
   curl http://localhost:8000/health
   docker compose logs -f coddy
   ```

## How secrets work

- Docker Compose mounts each secret file into the container at `/run/secrets/<name>`.
- The app is given `GITHUB_TOKEN_FILE=/run/secrets/github_token` and `WEBHOOK_SECRET_FILE=/run/secrets/webhook_secret`.
- The app reads the token/secret from that path and never expects them in the image or in `config.yaml`.

## Cursor Agent token (optional)

For the Cursor CLI agent to call the API, it needs a token. You can pass it via env or a secret file:

1. **Create** `.secrets/cursor_agent_token` with your Cursor Agent token.
2. **Uncomment** in `docker-compose.yml`:
   - under `secrets`: `- cursor_agent_token`
   - under `environment`: `CURSOR_AGENT_TOKEN_FILE: /run/secrets/cursor_agent_token`
   - under `secrets`: the `cursor_agent_token` entry with `file: ./.secrets/cursor_agent_token`

Alternatively set `CURSOR_AGENT_TOKEN` in the environment (e.g. in a non-committed `.env`).

## Config file

The `config.yaml` file is mounted from the host via bind mount in `docker-compose.yml`. Always copy `config.example.yaml` to `config.yaml` before first run - the example contains all available settings with defaults.

**Important**: Never commit `config.yaml` to the repository (it's in `.gitignore`). The `config.example.yaml` stays in the repo as a template with all options documented.

## CLI in container

```bash
docker compose run --rm coddy python -m coddy.main --check
docker compose run --rm coddy python -m coddy.main --config /app/config.yaml
```
