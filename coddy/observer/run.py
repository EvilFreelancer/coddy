"""
Coddy observer: webhook server and task intake.

Listens for GitHub webhooks; on issue assigned creates/updates .coddy/issues/
and sets status pending_plan (worker builds plan and writes to files). Polls
.coddy/issues/ for plan_ready (posts worker's plan to GitHub) and
waiting_user_reply (posts clarification). On user confirmation sets issue
status to queued. Does not run the AI agent or development loop - that is done by the worker.
"""

import argparse
import logging
import sys
import threading
import time
from pathlib import Path

from coddy.config import AppConfig, LoggingConfig, load_config
from coddy.logging import CoddyLogging
from coddy.observer.clarification_poll import run_clarification_poll, run_plan_post_poll
from coddy.observer.sync import run_sync
from coddy.observer.webhook.handlers import _working_dir_from_config
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


def _clarification_poll_loop(config: AppConfig, work_dir: Path, log: logging.Logger) -> None:
    """Background loop: every poll_interval_seconds run plan post and clarification poll."""
    interval = getattr(config.observer, "poll_interval_seconds", 15)
    while True:
        time.sleep(interval)
        try:
            run_plan_post_poll(config, work_dir, log=log)
            run_clarification_poll(config, work_dir, log=log)
        except Exception as e:
            log.warning("Poll error: %s", e)


def run_observer(config: AppConfig) -> None:
    """Run the webhook server and optional clarification poll thread."""
    CoddyLogging(config.logging).setup()
    log = logging.getLogger("coddy.observer.run")

    if not config.webhook.enabled:
        log.warning("Webhook disabled in config; observer will do nothing useful.")

    work_dir = _working_dir_from_config(config)
    if (getattr(config.bot, "workspace_path", ".") or ".") == ".":
        log.warning(
            "bot.workspace_path not set; .coddy (issues, prs) will be under cwd. "
            "Set BOT_WORKSPACE_PATH or bot.workspace_path to the repo root for a predictable path.",
        )

    sync_on_startup = getattr(config.observer, "sync_on_startup", False)
    if sync_on_startup:
        try:
            run_sync(config, work_dir, log=log)
        except Exception as e:
            log.warning("Startup sync failed: %s", e)

    poll_clarifications = getattr(config.observer, "poll_clarifications", True)
    if poll_clarifications:
        thread = threading.Thread(
            target=_clarification_poll_loop,
            args=(config, work_dir, log),
            daemon=True,
        )
        thread.start()
        interval = getattr(config.observer, "poll_interval_seconds", 15)
        log.info("Observer poll thread started (interval=%ss)", interval)

    log.info(
        "Coddy observer started | repo=%s | webhook=%s | workspace=%s",
        config.bot.repository,
        config.webhook.enabled,
        work_dir,
    )

    run_webhook_server(config)


def main(argv: list[str] | None = None) -> int:
    """Entry point for coddy observer."""
    args = parse_args(argv)
    config_path = args.config
    if not config_path.is_file() and config_path == Path("config.yaml"):
        if Path("config.example.yaml").is_file():
            config_path = Path("config.example.yaml")
            CoddyLogging(LoggingConfig()).setup()
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
