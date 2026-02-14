"""Configuration loading from YAML and environment.

Secrets (tokens) are taken from environment variables or from files
(Docker secrets). Never put real tokens in config files committed to the
repo.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret(env_key: str, file_env_key: str) -> str | None:
    """Read secret from env var or from file path in env (e.g. Docker
    secrets)."""
    value = _current_env.get(env_key)
    if value:
        return value.strip()
    file_path = _current_env.get(file_env_key)
    if file_path:
        return Path(file_path).read_text().strip()
    return None


# Injected by load_config so validators can read env/file
_current_env: dict[str, str] = {}


class BotConfig(BaseSettings):
    """Bot identity and target repo."""

    model_config = SettingsConfigDict(env_prefix="BOT_", extra="ignore")

    name: str = Field(default="Coddy Bot", description="Bot display name")
    email: str = Field(default="bot@coddy.dev", description="Bot email for commits")
    git_platform: str = Field(default="github", description="github, gitlab, bitbucket")
    repository: str = Field(default="owner/repo", description="Target repo e.g. EvilFreelancer/coddy")
    default_branch: str = Field(default="main", description="Default branch for pull and PR base (e.g. main)")
    github_username: str | None = Field(
        default=None, description="Bot GitHub login (to skip own comments when polling)"
    )
    webhook_secret: str = Field(default="", description="Secret for webhook verification")
    ai_agent: str = Field(default="cursor_cli", description="AI agent key from ai_agents")
    # Minutes of issue inactivity before posting plan and asking for confirmation (env: BOT_IDLE_MINUTES)
    idle_minutes: int = Field(default=10, ge=1, le=1440, description="Idle minutes before taking issue in work")


class GitHubConfig(BaseSettings):
    """GitHub API and webhook settings."""

    model_config = SettingsConfigDict(env_prefix="GITHUB_", extra="ignore")

    token: str | None = Field(default=None, description="PAT or app token; use env or secret file")
    api_url: str = Field(default="https://api.github.com", description="API base URL")
    webhook_path: str = Field(default="/webhook/github", description="Webhook URL path")


class GitLabConfig(BaseSettings):
    """GitLab API settings (optional)."""

    model_config = SettingsConfigDict(env_prefix="GITLAB_", extra="ignore")

    token: str | None = Field(default=None, description="Access token")
    api_url: str = Field(default="https://gitlab.com/api/v4", description="API base URL")
    webhook_path: str = Field(default="/webhook/gitlab", description="Webhook URL path")


class BitbucketConfig(BaseSettings):
    """Bitbucket API settings (optional)."""

    model_config = SettingsConfigDict(env_prefix="BITBUCKET_", extra="ignore")

    token: str | None = Field(default=None, description="API token or app password")
    api_url: str = Field(default="https://api.bitbucket.org/2.0", description="API base URL")
    webhook_path: str = Field(default="/webhook/bitbucket", description="Webhook URL path")


class CursorCLIAgentConfig(BaseSettings):
    """Cursor CLI agent settings (cursor.com/cli,
    cursor.com/docs/cli/headless)."""

    command: str = Field(default="agent", description="CLI command name (agent from Cursor install)")
    args: list[str] = Field(default_factory=lambda: ["generate"], description="CLI args")
    timeout: int = Field(default=300, ge=1, description="Timeout in seconds")
    working_directory: str = Field(default=".", description="CWD for agent")
    token: str | None = Field(default=None, description="Agent token; prefer env or secret file")
    # Headless CLI options (docs: cursor.com/docs/cli/reference/parameters, output-format)
    output_format: str | None = Field(
        default=None,
        description="--output-format: text (default), json, or stream-json",
    )
    stream_partial_output: bool = Field(
        default=False,
        description="--stream-partial-output (only with output_format=stream-json)",
    )
    model: str | None = Field(default=None, description="--model: model to use")
    mode: str | None = Field(default=None, description="--mode: agent (default), plan, or ask")


class WebhookConfig(BaseSettings):
    """Webhook server settings."""

    model_config = SettingsConfigDict(env_prefix="WEBHOOK_", extra="ignore")

    host: str = Field(default="0.0.0.0", description="Bind host")
    port: int = Field(default=8000, ge=1, le=65535, description="Bind port")
    debug: bool = Field(default=False, description="Debug mode")
    enabled: bool = Field(default=True, description="Enable webhook server")


class SchedulerConfig(BaseSettings):
    """Scheduler (polling) settings."""

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_", extra="ignore")

    enabled: bool = Field(default=True, description="Enable polling when webhooks unavailable")
    interval_seconds: int = Field(default=120, ge=30, description="Poll interval in seconds")


class LoggingConfig(BaseSettings):
    """Logging settings."""

    model_config = SettingsConfigDict(env_prefix="LOGGING_", extra="ignore")

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format",
    )


class AppConfig(BaseSettings):
    """Root application config from YAML + env."""

    model_config = SettingsConfigDict(extra="ignore")

    bot: BotConfig = Field(default_factory=BotConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    gitlab: GitLabConfig = Field(default_factory=GitLabConfig)
    bitbucket: BitbucketConfig = Field(default_factory=BitbucketConfig)
    ai_agents: dict[str, Any] = Field(default_factory=dict)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @property
    def github_token_resolved(self) -> str | None:
        """Resolve GitHub token from env or Docker secret file."""
        t = self.github.token
        if t and not t.startswith("${") and t != "your-webhook-secret-here":
            return t
        return _read_secret("GITHUB_TOKEN", "GITHUB_TOKEN_FILE")

    @property
    def webhook_secret_resolved(self) -> str | None:
        """Resolve webhook secret from env or Docker secret file."""
        s = self.bot.webhook_secret
        if s and not s.startswith("${") and s != "your-webhook-secret-here":
            return s
        return _read_secret("WEBHOOK_SECRET", "WEBHOOK_SECRET_FILE") or ""

    @property
    def cursor_agent_token_resolved(self) -> str | None:
        """Resolve Cursor Agent token from env or Docker secret file (for agent
        CLI)."""
        t = None
        if self.ai_agents and "cursor_cli" in self.ai_agents:
            cfg = self.ai_agents["cursor_cli"]
            if hasattr(cfg, "token") and cfg.token:
                t = cfg.token
        if t and not str(t).startswith("${"):
            return t
        return _read_secret("CURSOR_AGENT_TOKEN", "CURSOR_AGENT_TOKEN_FILE")


def _substitute_env(value: Any) -> Any:
    """Replace ${VAR} and $VAR in strings with os.environ."""
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            key = value[2:-1].strip()
            return _current_env.get(key, value)
        # Simple $VAR
        if value.startswith("$") and not value.startswith("${"):
            key = value[1:].strip()
            return _current_env.get(key, value)
        return value
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML file and environment.

    Secrets: GITHUB_TOKEN or GITHUB_TOKEN_FILE, WEBHOOK_SECRET or WEBHOOK_SECRET_FILE.
    """
    global _current_env
    import os

    _current_env = dict(os.environ)

    path = config_path or Path("config.yaml")
    if not path.is_file():
        return AppConfig()

    raw = yaml.safe_load(path.read_text()) or {}
    raw = _substitute_env(raw)

    # Env overrides for nested values (e.g. BOT_REPOSITORY)
    bot_raw = raw.get("bot") or {}
    if _current_env.get("BOT_REPOSITORY"):
        bot_raw = {**bot_raw, "repository": _current_env.get("BOT_REPOSITORY")}

    # Build nested models from raw dict
    bot = BotConfig(**bot_raw)
    github = GitHubConfig(**(raw.get("github") or {}))
    gitlab = GitLabConfig(**(raw.get("gitlab") or {}))
    bitbucket = BitbucketConfig(**(raw.get("bitbucket") or {}))
    webhook = WebhookConfig(**(raw.get("webhook") or {}))
    scheduler = SchedulerConfig(**(raw.get("scheduler") or {}))
    logging = LoggingConfig(**(raw.get("logging") or {}))

    ai_agents_raw = raw.get("ai_agents") or {}
    ai_agents: dict[str, Any] = {}
    for key, val in ai_agents_raw.items():
        if key == "cursor_cli":
            ai_agents[key] = CursorCLIAgentConfig(**(val or {}))
        else:
            ai_agents[key] = val

    return AppConfig(
        bot=bot,
        github=github,
        gitlab=gitlab,
        bitbucket=bitbucket,
        ai_agents=ai_agents,
        webhook=webhook,
        scheduler=scheduler,
        logging=logging,
    )
