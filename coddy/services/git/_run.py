"""Internal helpers: run git commands, GitRunnerError."""

import logging
import subprocess
from pathlib import Path


class GitRunnerError(Exception):
    """Raised when a git command fails."""

    pass


def _run_git(args: list[str], cwd: Path, log: logging.Logger | None = None) -> None:
    """Run git command; raise GitRunnerError on non-zero exit."""
    cmd = ["git"] + args
    try:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, timeout=60)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip()
        if log:
            log.warning("Git %s failed: %s", args, err)
        raise GitRunnerError(f"git {' '.join(args)}: {err}") from e
    except FileNotFoundError as e:
        raise GitRunnerError("git not found") from e
