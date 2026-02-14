"""Stage and commit changes with bot identity."""

import logging
from pathlib import Path

from coddy.services.git._run import GitRunnerError, _run_git


def add_all_and_commit(
    commit_message: str,
    bot_name: str,
    bot_email: str,
    repo_dir: Path | None = None,
    log: logging.Logger | None = None,
) -> bool:
    """Stage all changes and commit with bot identity.

    If there is nothing to commit (working tree clean), returns False without
    raising. Returns True if a commit was made. Raises GitRunnerError on failure.

    Args:
        commit_message: Commit message.
        bot_name: Git user.name for the commit.
        bot_email: Git user.email for the commit.
        repo_dir: Repository directory; uses cwd if None.
        log: Optional logger.

    Returns:
        True if a commit was made, False if nothing to commit.
    """
    cwd = Path(repo_dir) if repo_dir is not None else Path.cwd()
    _run_git(["add", "-A"], cwd=cwd, log=log)
    try:
        _run_git(
            [
                "-c",
                f"user.name={bot_name}",
                "-c",
                f"user.email={bot_email}",
                "commit",
                "-m",
                commit_message,
            ],
            cwd=cwd,
            log=log,
        )
        return True
    except GitRunnerError as e:
        if "nothing to commit" in str(e).lower() or "no changes" in str(e).lower():
            if log:
                log.info("Nothing to commit, working tree clean")
            return False
        raise
