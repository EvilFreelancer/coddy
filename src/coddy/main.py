"""
Coddy Bot entry point.

Loads config from YAML (and env), supports --config path.
Secrets from env or Docker secret files (GITHUB_TOKEN_FILE, WEBHOOK_SECRET_FILE).
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from coddy.config import AppConfig, load_config


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
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


def setup_logging(level: str = "INFO", fmt: Optional[str] = None) -> None:
    """Configure root logger."""
    fmt = fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)


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

    # TODO: start webhook server if config.webhook.enabled
    # TODO: start scheduler if config.scheduler.enabled
    # For prototype: just block with a simple HTTP server or sleep
    if config.webhook.enabled:
        from coddy.webhook.server import run_webhook_server

        run_webhook_server(config)
    else:
        log.info("Webhook disabled; scheduler would run here (not yet implemented)")
        import time

        while True:
            time.sleep(60)


def main(argv: Optional[list[str]] = None) -> int:
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
