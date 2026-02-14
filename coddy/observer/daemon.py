"""
Coddy daemon: webhook server and task queue producer.

Listens for GitHub webhooks; on issue assigned (or other configured events)
enqueues a task to .coddy/queue/pending/. Does not run the AI agent or
development loop - that is done by the worker.
"""

import argparse
import logging
import sys
from pathlib import Path

from coddy.config import AppConfig, load_config
from coddy.observer.scheduler import start_scheduler_thread
from coddy.observer.webhook.server import run_webhook_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the daemon."""
    parser = argparse.ArgumentParser(
        prog="coddy daemon",
        description="Coddy daemon - webhook server and task queue",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.yaml"),
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only load and validate config, then exit",
    )
    return parser.parse_args(argv)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger."""
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)


def run_daemon(config: AppConfig) -> None:
    """Run the webhook server and scheduler (plan after idle_minutes)."""
    setup_logging(config.logging.level)
    log = logging.getLogger("coddy.observer.daemon")

    repo_dir = Path.cwd()
    if config.ai_agents and "cursor_cli" in config.ai_agents:
        wd = getattr(config.ai_agents["cursor_cli"], "working_directory", None)
        if wd:
            repo_dir = Path(wd).resolve()

    if not config.webhook.enabled:
        log.warning("Webhook disabled in config; daemon will do nothing useful.")
    log.info(
        "Coddy daemon started | repo=%s | webhook=%s | idle_minutes=%s",
        config.bot.repository,
        config.webhook.enabled,
        getattr(config.bot, "idle_minutes", 10),
    )

    start_scheduler_thread(config, repo_dir)
    run_webhook_server(config)


def main(argv: list[str] | None = None) -> int:
    """Entry point for coddy daemon."""
    args = parse_args(argv)
    config_path = args.config
    if not config_path.is_file() and config_path == Path("config.yaml"):
        if Path("config.example.yaml").is_file():
            config_path = Path("config.example.yaml")
            logging.basicConfig(level=logging.INFO)
            logging.getLogger("coddy.observer.daemon").warning("config.yaml not found, using config.example.yaml")

    config = load_config(config_path)

    if args.check:
        print("Config OK:", config.bot.repository, config.bot.git_platform)
        return 0

    try:
        run_daemon(config)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logging.getLogger("coddy.observer.daemon").exception("Fatal error: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
