#!/usr/bin/env bash
# Create .secrets and config.yaml so "docker compose up -d" can start.
# Run once after clone, then replace placeholders in .secrets/* with real values.
set -e
cd "$(dirname "$0")/.."
SECRETS_DIR=".secrets"
mkdir -p "$SECRETS_DIR"
if [[ ! -f "$SECRETS_DIR/github_token" ]]; then
  echo "REPLACE_WITH_YOUR_GITHUB_PAT" > "$SECRETS_DIR/github_token"
  echo "Created $SECRETS_DIR/github_token (placeholder)"
fi
if [[ ! -f "$SECRETS_DIR/webhook_secret" ]]; then
  echo "REPLACE_WITH_YOUR_WEBHOOK_SECRET" > "$SECRETS_DIR/webhook_secret"
  echo "Created $SECRETS_DIR/webhook_secret (placeholder)"
fi
if [[ ! -f "$SECRETS_DIR/cursor_agent_token" ]]; then
  echo "REPLACE_WITH_CURSOR_AGENT_TOKEN_OR_LEAVE_EMPTY" > "$SECRETS_DIR/cursor_agent_token"
  echo "Created $SECRETS_DIR/cursor_agent_token (optional placeholder)"
fi
chmod 600 "$SECRETS_DIR"/github_token "$SECRETS_DIR"/webhook_secret "$SECRETS_DIR"/cursor_agent_token 2>/dev/null || true
if [[ ! -f config.yaml ]]; then
  cp config.example.yaml config.yaml
  echo "Created config.yaml from config.example.yaml"
fi
echo ""
echo "Next steps:"
echo "  1. Edit .secrets/github_token - put your GitHub Personal Access Token"
echo "  2. Edit .secrets/webhook_secret - put the secret you set in GitHub webhook"
echo "  3. (Optional) Edit .secrets/cursor_agent_token for Cursor CLI agent, or leave placeholder"
echo "  4. Edit config.yaml if needed (repository, webhook path, etc.)"
echo "     For Docker, set webhook.enabled: true so the server listens on port 8000 and /health works."
echo "  5. Run: docker compose up -d"
echo ""
