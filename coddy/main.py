"""Coddy Bot entry point.

Loads config from YAML (and env), supports --config path. Secrets from
env or Docker secret files (GITHUB_TOKEN_FILE, WEBHOOK_SECRET_FILE).
"""

import argparse
import logging
import sys
from pathlib import Path

from coddy.config import AppConfig, load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (Pydantic-validated config path)."""
    parser = argparse.ArgumentParser(
        prog="coddy",
        description="Coddy Bot - Community driven development",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.yaml"),
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only load and validate config, then exit",
    )
    return parser.parse_args(argv)


def setup_logging(level: str = "INFO", fmt: str | None = None) -> None:
    """Configure root logger."""
    fmt = fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)


def _make_agent(config: AppConfig, log: logging.Logger):
    """Build AI agent from config (cursor_cli or stub)."""
    if config.bot.ai_agent == "cursor_cli" and getattr(config, "ai_agents", {}).get("cursor_cli"):
        from coddy.agents.cursor_cli_agent import make_cursor_cli_agent

        return make_cursor_cli_agent(config)
    from coddy.agents.stub_agent import StubAgent

    return StubAgent(min_body_length=0)


def _startup_poll_open_issues(config: AppConfig, log: logging.Logger) -> tuple:
    """
    On startup: list open issues and take the first one in work.

    Sets label 'in progress' and returns (adapter, issue) for further processing,
    or (None, None) if no issue or not GitHub.
    """
    token = config.github_token_resolved
    if not token:
        log.debug("Skipping startup issue check: no GitHub token")
        return (None, None)
    if config.bot.git_platform != "github":
        log.debug("Startup issue check only implemented for GitHub")
        return (None, None)

    from coddy.adapters.base import GitPlatformError
    from coddy.adapters.github import GitHubAdapter

    adapter = GitHubAdapter(token=token, api_url=config.github.api_url)
    repo = config.bot.repository
    try:
        issues = adapter.list_open_issues(repo)
    except GitPlatformError as e:
        log.warning("Startup: failed to list open issues: %s", e)
        return (None, None)
    if not issues:
        log.info("Startup: no open issues")
        return (None, None)
    issue = issues[0]
    log.info("Startup: found open issue #%s - %s", issue.number, issue.title)
    try:
        adapter.set_issue_labels(repo, issue.number, ["in progress"])
        log.info("Startup: took issue #%s in work (label 'in progress' set)", issue.number)
    except GitPlatformError as e:
        log.warning("Startup: failed to set labels on issue #%s: %s", issue.number, e)
    return (adapter, issue)


def run(config: AppConfig) -> None:
    """Run the bot (webhook server and/or scheduler)."""
    setup_logging(config.logging.level, config.logging.format)
    log = logging.getLogger("coddy")

    token = config.github_token_resolved
    if not token:
        log.warning("GITHUB_TOKEN / GITHUB_TOKEN_FILE not set; GitHub API calls will fail")

    log.info(
        "Coddy Bot started | repo=%s | platform=%s",
        config.bot.repository,
        config.bot.git_platform,
    )
    if not config.webhook.enabled:
        log.info("Webhooks disabled, events will not be received via HTTP.")

    # On startup: read all open issues, take the first, then run full flow (branch, sufficiency, work)
    adapter, issue = _startup_poll_open_issues(config, log)
    if adapter is not None and issue is not None:
        from pathlib import Path

        from coddy.services.issue_processor import process_one_issue

        agent = _make_agent(config, log)
        process_one_issue(
            adapter,
            agent,
            issue,
            config.bot.repository,
            repo_dir=Path.cwd(),
            bot_username=getattr(config.bot, "github_username", None),
            bot_name=config.bot.name,
            bot_email=config.bot.email,
            default_branch=config.bot.default_branch,
            log=log,
        )

    # TODO: start scheduler loop (periodic poll) when config.scheduler.enabled
    if config.webhook.enabled:
        from coddy.webhook.server import run_webhook_server

        run_webhook_server(config)
    else:
        import time

        while True:
            time.sleep(60)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)

    config_path = args.config
    if not config_path.is_file() and config_path == Path("config.yaml"):
        # Default path missing: try config.example.yaml for dev
        if Path("config.example.yaml").is_file():
            config_path = Path("config.example.yaml")
            logging.basicConfig(level=logging.INFO)
            logging.getLogger("coddy").warning("config.yaml not found, using config.example.yaml")

    config = load_config(config_path)

    if args.check:
        print("Config OK:", config.bot.repository, config.bot.git_platform)
        return 0

    try:
        run(config)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logging.getLogger("coddy").exception("Fatal error: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
