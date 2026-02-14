"""
Coddy observer: webhook server and task intake.

Listens for GitHub webhooks; on issue assigned creates/updates .coddy/issues/,
runs planner (posts plan, waiting_confirmation); on user confirmation sets
issue status to queued (worker picks from .coddy/issues/). On PR/issue closed
updates status in .coddy/prs/ and .coddy/issues/. Does not run the AI agent
or development loop - that is done by the worker.
"""

import argparse
import logging
import sys
from pathlib import Path

from coddy.config import AppConfig, load_config
from coddy.observer.webhook.server import run_webhook_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the observer."""
    parser = argparse.ArgumentParser(
        prog="coddy observer",
        description="Coddy observer - webhook server and task queue",
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


def run_observer(config: AppConfig) -> None:
    """Run the webhook server (plan on assignment, no polling)."""
    setup_logging(config.logging.level)
    log = logging.getLogger("coddy.observer.run")

    if not config.webhook.enabled:
        log.warning("Webhook disabled in config; observer will do nothing useful.")
    log.info(
        "Coddy observer started | repo=%s | webhook=%s",
        config.bot.repository,
        config.webhook.enabled,
    )

    run_webhook_server(config)


def main(argv: list[str] | None = None) -> int:
    """Entry point for coddy observer."""
    args = parse_args(argv)
    config_path = args.config
    if not config_path.is_file() and config_path == Path("config.yaml"):
        if Path("config.example.yaml").is_file():
            config_path = Path("config.example.yaml")
            logging.basicConfig(level=logging.INFO)
            logging.getLogger("coddy.observer.run").warning("config.yaml not found, using config.example.yaml")

    config = load_config(config_path)

    if args.check:
        print("Config OK:", config.bot.repository, config.bot.git_platform)
        return 0

    try:
        run_observer(config)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logging.getLogger("coddy.observer.run").exception("Fatal error: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
