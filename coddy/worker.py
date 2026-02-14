"""
Coddy worker: poll task queue and run the ralph loop for each task.

Dequeues from .coddy/queue/pending/, runs ralph loop (branch, repeated
Cursor CLI runs until PR report or clarification), then marks task done
or failed.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from coddy.config import AppConfig, load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the worker."""
    parser = argparse.ArgumentParser(
        prog="coddy worker",
        description="Coddy worker - run ralph loop for queued issues",
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


def _make_agent(config: AppConfig) -> object:
    """Build AI agent from config (cursor_cli only)."""
    from coddy.agents.cursor_cli_agent import make_cursor_cli_agent

    return make_cursor_cli_agent(config)


def run_worker(config: AppConfig, once: bool = False, poll_interval: int = 10) -> None:
    """Poll queue and process tasks with the ralph loop."""
    setup_logging(config.logging.level)
    log = logging.getLogger("coddy.worker")

    token = config.github_token_resolved
    if not token:
        log.warning("GITHUB_TOKEN not set; GitHub API calls will fail")
    if config.bot.git_platform != "github":
        log.error("Worker only supports GitHub")
        return

    from coddy.adapters.github import GitHubAdapter
    from coddy.observer.queue import mark_done, mark_failed, take_next
    from coddy.services.ralph_loop import run_ralph_loop_for_issue

    repo_dir = Path.cwd()
    if config.ai_agents and "cursor_cli" in config.ai_agents:
        wd = getattr(config.ai_agents["cursor_cli"], "working_directory", None)
        if wd:
            repo_dir = Path(wd).resolve()

    adapter = GitHubAdapter(token=token, api_url=config.github.api_url)
    agent = _make_agent(config)
    repo = config.bot.repository

    log.info("Coddy worker started | repo=%s | once=%s", repo, once)

    while True:
        task = take_next(repo_dir)
        if not task:
            if once:
                log.info("No pending tasks, exiting (--once)")
                return
            time.sleep(poll_interval)
            continue

        issue_number = task["issue_number"]
        repo_name = task.get("repo", repo)
        log.info("Processing task: issue #%s", issue_number)

        try:
            issue = adapter.get_issue(repo_name, issue_number)
        except Exception as e:
            log.warning("Failed to get issue #%s: %s", issue_number, e)
            mark_failed(repo_dir, issue_number)
            if once:
                return
            continue

        result = run_ralph_loop_for_issue(
            adapter,
            agent,
            issue,
            repo_name,
            repo_dir,
            bot_name=config.bot.name,
            bot_email=config.bot.email,
            default_branch=config.bot.default_branch,
            max_iterations=10,
            log=log,
        )

        if result == "success":
            mark_done(repo_dir, issue_number)
            log.info("Task issue #%s completed successfully", issue_number)
        else:
            mark_failed(repo_dir, issue_number)
            log.info("Task issue #%s finished with status: %s", issue_number, result)

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
