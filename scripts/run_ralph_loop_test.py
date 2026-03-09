#!/usr/bin/env python3
"""Standalone script to run only the ralph loop logic with verbose logging.

Usage:
  python scripts/run_ralph_loop_test.py [--workspace DIR] [--max-iterations N] [--use-real-agent]
  python -m scripts.run_ralph_loop_test --workspace /path/to/repo

Uses a mock GitHub adapter (no real API calls). By default uses a mock agent
that returns None then a fake PR body (to exercise two iterations). With
--use-real-agent, runs the real Cursor CLI if "agent" is in PATH; skips otherwise.
Without a Cursor API token the CLI will hang or timeout (no auth). Pass --cursor-token
or set CURSOR_API_KEY / CURSOR_AGENT_TOKEN in the environment.
"""

import argparse
import logging
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure coddy is importable when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coddy.observer.models import Issue
from coddy.worker.agents.base import AIAgent, SufficiencyResult
from coddy.worker.ralph_loop import run_ralph_loop_for_issue


def _setup_verbose_logging(level: int = logging.DEBUG) -> logging.Logger:
    """Configure root and coddy loggers for detailed output."""
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S")
    for name in (
        "coddy.worker.ralph_loop",
        "coddy.worker.agents.cursor_cli",
        "coddy.services.git",
        "coddy.services.store",
    ):
        logging.getLogger(name).setLevel(level)
    return logging.getLogger("coddy.worker.ralph_loop")


def _issue(number: int = 1, body: str = "Add a single line to README with the word Hello.") -> Issue:
    return Issue(
        number=number,
        title="Add a comment to README",
        body=body,
        author="user",
        labels=[],
        state="open",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_mock_adapter(repo: str = "owner/repo") -> MagicMock:
    adapter = MagicMock()
    adapter.get_issue_comments.return_value = []
    adapter.get_default_branch.return_value = "main"
    adapter.create_branch.side_effect = None
    adapter.set_issue_labels.side_effect = None
    adapter.create_pr.side_effect = None
    adapter.get_issue.return_value = _issue()
    return adapter


def _make_mock_agent(
    first_returns_none: int = 1,
    then_pr_body: str = "Test PR body (mock). Closes #1",
) -> tuple[AIAgent, list[int]]:
    """Mock agent: first N calls to generate_code return None, then return pr_body.
    Returns (agent, call_count_list) so caller can read call_count_list[0]."""
    call_count: list[int] = [0]

    class MockAgent(AIAgent):
        def evaluate_sufficiency(self, issue: Issue, comments: list) -> SufficiencyResult:
            return SufficiencyResult(sufficient=True, clarification="")

        def generate_plan(self, issue: Issue, comments: list) -> str | None:
            return "1. Do A\n2. Do B"

        def generate_code(self, issue: Issue, comments: list) -> str | None:
            call_count[0] += 1
            if call_count[0] <= first_returns_none:
                return None
            return then_pr_body

        def process_review_item(
            self, pr_number: int, issue_number: int, comments: list, current_index: int, repo_dir: Path
        ) -> str | None:
            return None

    return MockAgent(), call_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run ralph loop with verbose logs (mock adapter, optional real agent)."
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Workspace directory (default: temp dir)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Max ralph loop iterations (default: 3)",
    )
    parser.add_argument(
        "--use-real-agent",
        action="store_true",
        help="Use real Cursor CLI if 'agent' in PATH; otherwise skip",
    )
    parser.add_argument(
        "--mock-iterations",
        type=int,
        default=1,
        help="When using mock agent: number of generate_code calls that return None before PR body (default: 1)",
    )
    parser.add_argument(
        "--cursor-token",
        type=str,
        default=os.environ.get("CURSOR_API_KEY") or os.environ.get("CURSOR_AGENT_TOKEN"),
        help="Cursor API key for --use-real-agent (default: CURSOR_API_KEY or CURSOR_AGENT_TOKEN env)",
    )
    parser.add_argument(
        "--show-agent-log",
        action="store_true",
        default=None,
        help="After run, print .coddy/logs/N.log (default: on when --use-real-agent)",
    )
    parser.add_argument(
        "--no-show-agent-log",
        action="store_false",
        dest="show_agent_log",
        help="Do not print agent log file after run",
    )
    parser.add_argument(
        "--stream-agent-output",
        action="store_true",
        help="Stream agent stdout/stderr to script log in real time (DEBUG lines 'agent: ...')",
    )
    args = parser.parse_args()
    if args.show_agent_log is None:
        args.show_agent_log = args.use_real_agent

    log = _setup_verbose_logging()
    workspace = args.workspace or Path(__file__).resolve().parent.parent / ".ralph_loop_test_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".coddy").mkdir(parents=True, exist_ok=True)

    repo = "owner/repo"
    issue = _issue(number=1)
    adapter = _make_mock_adapter(repo)
    adapter.get_issue.return_value = issue
    mock_call_count: list[int] = [0]

    if args.use_real_agent:
        if not shutil.which("agent"):
            log.warning("Cursor CLI (agent) not found in PATH; skipping real agent run.")
            return 0
        if not args.cursor_token:
            log.warning(
                "No Cursor API token (--cursor-token or CURSOR_API_KEY / CURSOR_AGENT_TOKEN). "
                "CLI will likely hang or timeout."
            )
        from coddy.services.store import create_issue
        from coddy.worker.agents.cursor_cli_agent import CursorCLIAgent

        create_issue(
            workspace,
            issue_id=1,
            repo=repo,
            title=issue.title,
            description=issue.body or "",
            author=issue.author,
        )
        agent = CursorCLIAgent(
            command="agent",
            timeout=60,
            working_directory=str(workspace),
            stream_output_to_log=args.stream_agent_output,
        )
        log.info("Using real Cursor CLI agent (timeout=60s, token=%s)", "set" if args.cursor_token else "not set")
        agent_log_path = workspace / ".coddy" / "logs" / "1.log"
        task_yaml_path = workspace / ".coddy" / "task-1.yaml"
        log.info("Agent log file: %s (tail -f in another terminal for live output)", agent_log_path)
        log.info("Task YAML: %s", task_yaml_path)
    else:
        agent, mock_call_count = _make_mock_agent(first_returns_none=args.mock_iterations)
        log.info("Using mock agent (first %s generate_code returns None, then PR body)", args.mock_iterations)

    def _noop(*args: object, **kwargs: object) -> None:
        pass

    with (
        patch("coddy.worker.ralph_loop.fetch_and_checkout_branch", side_effect=_noop),
        patch("coddy.worker.ralph_loop.checkout_branch", side_effect=_noop),
        patch("coddy.worker.ralph_loop.commit_all_and_push", side_effect=_noop),
    ):
        log.info(
            "Workspace: %s | repo=%s | issue #%s | max_iterations=%s",
            workspace,
            repo,
            issue.number,
            args.max_iterations,
        )
        log.info("--- Starting ralph loop ---")
        result = run_ralph_loop_for_issue(
            adapter,
            agent,
            issue,
            repo,
            workspace,
            default_branch="main",
            max_iterations=args.max_iterations,
            log=log,
        )
        log.info("--- Ralph loop finished: result=%s ---", result)

    print(f"\nResult: {result}")
    if not args.use_real_agent:
        print(f"generate_code called: {mock_call_count[0]} time(s)")
    if adapter.create_pr.called:
        body = adapter.create_pr.call_args[1].get("body", "")
        print(f"create_pr called with body: {body[:200]}{'...' if len(body) > 200 else ''}")

    if args.show_agent_log and args.use_real_agent:
        agent_log_path = workspace / ".coddy" / "logs" / "1.log"
        task_yaml_path = workspace / ".coddy" / "task-1.yaml"
        if task_yaml_path.exists():
            print("\n--- Task YAML (input to agent) ---")
            print(task_yaml_path.read_text(encoding="utf-8"))
        if agent_log_path.exists():
            print("\n--- Agent log (logs/1.log) ---")
            print(agent_log_path.read_text(encoding="utf-8"))
        else:
            print("\n(No agent log file yet: logs/1.log not found)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
