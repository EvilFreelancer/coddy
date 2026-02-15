"""CLI entry point: coddy observer | worker."""

import sys

from coddy.observer import run as observer_run
from coddy.worker import run as worker_run


def main(argv: list[str] | None = None) -> int:
    """Dispatch to observer or worker subcommand.

    Default: observer.
    """
    args = argv if argv is not None else sys.argv[1:]
    if args and args[0] == "worker":
        return worker_run.main(args[1:])
    if args and args[0] == "observer":
        return observer_run.main(args[1:])
    # No subcommand or unknown: run observer (e.g. "coddy" -> observer)
    return observer_run.main(args)
