"""
Cursor CLI agent: headless mode with task file and PR report file.

Writes task to .coddy/task-{n}.md, runs `agent -p --force "..."`, reads .coddy/pr-{n}.md for PR body.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, List, Optional

from coddy.agents.base import AIAgent, SufficiencyResult
from coddy.models import Comment, Issue
from coddy.services.task_file import read_pr_report, report_file_path, write_task_file


class CursorCLIAgent(AIAgent):
    """
    Run Cursor CLI in headless mode (-p --force) with task file context.

    Task is written to .coddy/task-{issue_number}.md; agent is asked to execute it
    and write PR description to .coddy/pr-{issue_number}.md.
    """

    def __init__(
        self,
        command: str = "agent",
        timeout: int = 300,
        working_directory: str = ".",
        token: Optional[str] = None,
        log: Optional[logging.Logger] = None,
    ) -> None:
        self.command = command
        self.timeout = timeout
        self.working_directory = working_directory
        self.token = token
        self._log = log or logging.getLogger("coddy.agents.cursor_cli")

    def evaluate_sufficiency(self, issue: Issue, comments: List[Comment]) -> SufficiencyResult:
        """Use simple heuristic: sufficient if body has some content."""
        if len((issue.body or "").strip()) < 20:
            return SufficiencyResult(
                sufficient=False,
                clarification=("Please add more details: what should be implemented and acceptance criteria."),
            )
        return SufficiencyResult(sufficient=True)

    def generate_code(self, issue: Issue, comments: List[Comment]) -> Optional[str]:
        """
        Write task file, run Cursor CLI headless, read PR report.

        Returns PR description string for create_pr, or None if report missing.
        """
        repo_dir = Path(self.working_directory).resolve()
        task_path = write_task_file(issue, comments, repo_dir)
        report_path = report_file_path(repo_dir, issue.number)

        prompt = (
            f"Read and execute the task described in {task_path}. "
            f"Follow all project rules. As the last step of the task (after linter and tests pass), "
            f"write the PR description to {report_path} "
            f"(markdown: what was done, how to test, reference to issue #{issue.number})."
        )

        cmd = [self.command, "-p", "--force", prompt]
        env = os.environ.copy()
        if self.token:
            env["CURSOR_API_KEY"] = self.token

        self._log.info("Running Cursor CLI (headless): %s (timeout=%ss)", self.command, self.timeout)
        try:
            subprocess.run(
                cmd,
                cwd=self.working_directory,
                env=env,
                timeout=self.timeout,
                check=False,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            self._log.warning("Cursor CLI timed out after %s seconds", self.timeout)
        except FileNotFoundError as e:
            self._log.warning("Cursor CLI not found: %s", e)
            return None

        return read_pr_report(repo_dir, issue.number) or None


def make_cursor_cli_agent(config: Any) -> CursorCLIAgent:
    """Build CursorCLIAgent from app config (ai_agents.cursor_cli and resolved token)."""
    cfg = getattr(config, "ai_agents", {}).get("cursor_cli") or {}
    token = getattr(config, "cursor_agent_token_resolved", None) or getattr(cfg, "token", None)
    return CursorCLIAgent(
        command=getattr(cfg, "command", "agent"),
        timeout=getattr(cfg, "timeout", 300),
        working_directory=getattr(cfg, "working_directory", "."),
        token=token,
    )
