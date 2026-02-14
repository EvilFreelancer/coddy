"""Coddy Bot entry point.

Two modes: daemon (webhook server, enqueues tasks) and worker (runs ralph
loop for queued issues). Usage: coddy daemon | coddy worker.
"""

import argparse
import logging
import sys
from pathlib import Path

from coddy.config import load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI with optional subcommand (daemon | worker)."""
    argv = argv if argv is not None else sys.argv[1:]
    sub = "daemon"
    rest = list(argv)
    if argv and not argv[0].startswith("-"):
        if argv[0] in ("daemon", "worker"):
            sub = argv[0]
            rest = argv[1:]

    parser = argparse.ArgumentParser(
        prog="coddy",
        description="Coddy Bot - daemon (webhooks + queue) or worker (ralph loop)",
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
    parsed, _ = parser.parse_known_args(rest)
    parsed.subcommand = sub
    parsed.rest = rest
    return parsed


def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch to daemon or worker."""
    args = parse_args(argv)

    config_path = args.config
    if not config_path.is_file() and config_path == Path("config.yaml"):
        if Path("config.example.yaml").is_file():
            config_path = Path("config.example.yaml")
            logging.basicConfig(level=logging.INFO)
            logging.getLogger("coddy").warning("config.yaml not found, using config.example.yaml")

    config = load_config(config_path)

    if args.check:
        print("Config OK:", config.bot.repository, config.bot.git_platform)
        return 0

    if args.subcommand == "worker":
        from coddy.worker.run import parse_args as worker_parse
        from coddy.worker.run import run_worker

        worker_args = worker_parse(args.rest)
        try:
            run_worker(
                config,
                once=worker_args.once,
                poll_interval=worker_args.poll_interval,
            )
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            logging.getLogger("coddy.worker").exception("Fatal error: %s", e)
            return 1
        return 0

    # daemon (default)
    from coddy.observer.daemon import run_daemon

    try:
        run_daemon(config)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logging.getLogger("coddy.daemon").exception("Fatal error: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
