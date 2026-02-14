"""
Coddy worker stub: read queued issues from .coddy/issues/, write empty PR YAML, log dry run.

Full ralph loop is not run yet; worker only demonstrates the flow.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

from coddy.config import AppConfig, load_config
from coddy.services.store import list_queued, set_status
from coddy.worker.task_yaml import report_file_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the worker."""
    parser = argparse.ArgumentParser(
        prog="coddy worker",
        description="Coddy worker - dry run stub (read issues, write empty PR YAML)",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.yaml"),
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one task then exit",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Seconds to wait when queue is empty (default 10)",
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


def run_worker(config: AppConfig, once: bool = False, poll_interval: int = 10) -> None:
    """Dry run: poll queued issues, write empty PR YAML, set status done, log."""
    setup_logging(config.logging.level)
    log = logging.getLogger("coddy.worker")

    workspace = getattr(config.bot, "workspace", ".") or "."
    repo_dir = Path(workspace).resolve()
    if config.ai_agents and "cursor_cli" in config.ai_agents:
        wd = getattr(config.ai_agents["cursor_cli"], "working_directory", None)
        if wd:
            repo_dir = Path(wd).resolve()

    repo = config.bot.repository
    log.info("Coddy worker started (dry run) | repo=%s | workspace=%s | once=%s", repo, repo_dir, once)

    while True:
        queued = list_queued(repo_dir)
        if not queued:
            if once:
                log.info("No queued issues, exiting (--once)")
                return
            time.sleep(poll_interval)
            continue

        queued.sort(key=lambda t: t[0])
        issue_number, issue_file = queued[0]
        log.info("Dry run: processing issue #%s (%s)", issue_number, issue_file.title or "")

        report_path = report_file_path(repo_dir, issue_number)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        body = "# Dry run\n\nNo implementation yet; worker is a stub."
        report_path.write_text(
            yaml.dump({"body": body}, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        set_status(repo_dir, issue_number, "done")
        log.info("Dry run: wrote empty PR YAML for issue #%s -> %s", issue_number, report_path.name)

        if once:
            return


def main(argv: list[str] | None = None) -> int:
    """Entry point for coddy worker."""
    args = parse_args(argv)
    config_path = args.config
    if not config_path.is_file() and config_path == Path("config.yaml"):
        if Path("config.example.yaml").is_file():
            config_path = Path("config.example.yaml")
            logging.basicConfig(level=logging.INFO)
            logging.getLogger("coddy.worker").warning("config.yaml not found, using config.example.yaml")

    config = load_config(config_path)

    if args.check:
        print("Config OK:", config.bot.repository, config.bot.git_platform)
        return 0

    try:
        run_worker(
            config,
            once=args.once,
            poll_interval=args.poll_interval,
        )
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logging.getLogger("coddy.worker").exception("Fatal error: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
