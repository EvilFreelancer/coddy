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
    workspace_path: str = Field(
        default=".",
        description="Path to workspace (sources and .coddy/ with issues and PRs); env BOT_WORKSPACE_PATH",
    )
    username: str | None = Field(
        default=None,
        description="Platform login (e.g. coddybot on GitHub); assignment check and mentions; env BOT_USERNAME",
    )
    assignment_only: bool = Field(
        default=True,
        description="When True, worker only processes issues assigned to bot; env BOT_ASSIGNMENT_ONLY",
    )
    webhook_secret: str = Field(default="", description="Secret for webhook verification")


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


class ACPAgentConfig(BaseSettings):
    """ACP agent settings for any ACP-compatible backend."""

    command: list[str] = Field(default_factory=lambda: ["agent", "acp"], description="ACP launcher command")
    timeout: int = Field(default=600, ge=1, description="Prompt timeout in seconds")
    env: dict[str, str] = Field(default_factory=dict, description="Extra environment variables for ACP process")


class WebhookConfig(BaseSettings):
    """Webhook server settings."""

    model_config = SettingsConfigDict(env_prefix="WEBHOOK_", extra="ignore")

    host: str = Field(default="0.0.0.0", description="Bind host")
    port: int = Field(default=8000, ge=1, le=65535, description="Bind port")
    debug: bool = Field(default=False, description="Debug mode")
    enabled: bool = Field(default=True, description="Enable webhook server")


class ObserverConfig(BaseSettings):
    """Observer-specific settings (clarification poll)."""

    model_config = SettingsConfigDict(env_prefix="OBSERVER_", extra="ignore")

    poll_clarifications: bool = Field(
        default=True,
        description="When True, poll .coddy/issues/ for waiting_user_reply and post to platform",
    )
    poll_interval_seconds: int = Field(
        default=15,
        ge=1,
        description="Seconds between clarification poll runs",
    )
    sync_on_startup: bool = Field(
        default=False,
        description="When True, on start fetch issues and PRs from API into .coddy/issues/ and .coddy/pull_requests/",
    )


class WorkerConfig(BaseSettings):
    """Worker-specific settings (.coddy/issues/ poll)."""

    model_config = SettingsConfigDict(env_prefix="WORKER_", extra="ignore")

    poll_interval_seconds: int = Field(
        default=15,
        ge=1,
        description="Seconds between .coddy/issues/ poll runs (pending_plan, user_replied, queued)",
    )


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
    acp: ACPAgentConfig = Field(default_factory=ACPAgentConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    observer: ObserverConfig = Field(default_factory=ObserverConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
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
        """Resolve ACP/Cursor token from env or Docker secret file."""
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

    # Env overrides for nested values (e.g. BOT_REPOSITORY, BOT_WORKSPACE_PATH)
    bot_raw = raw.get("bot") or {}
    if _current_env.get("BOT_REPOSITORY"):
        bot_raw = {**bot_raw, "repository": _current_env.get("BOT_REPOSITORY")}
    if _current_env.get("BOT_WORKSPACE_PATH"):
        bot_raw = {**bot_raw, "workspace_path": _current_env.get("BOT_WORKSPACE_PATH")}

    # Build nested models from raw dict
    bot = BotConfig(**bot_raw)
    github = GitHubConfig(**(raw.get("github") or {}))
    gitlab = GitLabConfig(**(raw.get("gitlab") or {}))
    bitbucket = BitbucketConfig(**(raw.get("bitbucket") or {}))
    webhook = WebhookConfig(**(raw.get("webhook") or {}))
    observer = ObserverConfig(**(raw.get("observer") or {}))
    worker = WorkerConfig(**(raw.get("worker") or {}))
    logging = LoggingConfig(**(raw.get("logging") or {}))

    acp_raw = dict(raw.get("acp") or {})
    if _current_env.get("ACP_TIMEOUT"):
        acp_raw["timeout"] = int(_current_env["ACP_TIMEOUT"])
    acp = ACPAgentConfig(**acp_raw)

    return AppConfig(
        bot=bot,
        github=github,
        gitlab=gitlab,
        bitbucket=bitbucket,
        acp=acp,
        webhook=webhook,
        observer=observer,
        worker=worker,
        logging=logging,
    )
