"""
Cursor CLI agent: headless mode with task file and PR report file.

Coddy writes .coddy/task-{n}.md. Agent runs and either: (1) implements and writes
.coddy/pr-{n}.md for PR body, or (2) finds data insufficient and appends
"## Agent clarification request" to the task file and stops; Coddy reads that
and posts it to the issue. Run log is in .coddy/task-{n}.log.
"""

import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List

from coddy.agents.base import AIAgent, SufficiencyResult
from coddy.observer.models import Comment, Issue, ReviewComment
from coddy.worker.task_yaml import (
    read_pr_report,
    read_review_reply,
    report_file_path,
    review_reply_file_path,
    task_log_path,
    write_review_task_file,
    write_task_file,
)


class CursorCLIAgent(AIAgent):
    """Run Cursor CLI in headless mode (-p --force) with task file context.

    Task is written to .coddy/task-{issue_number}.md; agent is asked to
    execute it and write PR description to .coddy/pr-{issue_number}.md.
    """

    def __init__(
        self,
        command: str = "agent",
        timeout: int = 300,
        working_directory: str = ".",
        token: str | None = None,
        output_format: str | None = None,
        stream_partial_output: bool = False,
        model: str | None = None,
        mode: str | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self.command = command
        self.timeout = timeout
        self.working_directory = working_directory
        self.token = token
        self.output_format = output_format
        self.stream_partial_output = stream_partial_output
        self.model = model
        self.mode = mode
        self._log = log or logging.getLogger("coddy.agents.cursor_cli")

    def generate_plan(self, issue: Issue, comments: List[Comment]) -> str:
        """Run Cursor CLI with a plan-only prompt; return plan text in issue language."""
        prompt = (
            f"You are a planner. The user created an issue. Output ONLY a short implementation plan "
            f"(bullet points, no code). Use the same language as the issue. "
            f"Issue title: {issue.title!r}\n\nBody:\n{issue.body or '(none)'}\n\n"
            "Output only the plan, nothing else."
        )
        cmd = [self.command, "-p", "--force"]
        if self.output_format:
            cmd.extend(["--output-format", self.output_format])
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.append(prompt)
        env = os.environ.copy()
        if self.token:
            env["CURSOR_API_KEY"] = self.token
        try:
            result = subprocess.run(
                cmd,
                cwd=self.working_directory,
                env=env,
                timeout=min(self.timeout, 120),
                check=False,
                capture_output=True,
                text=True,
            )
            out = (result.stdout or "") + (result.stderr or "")
            return out.strip() or "1. Analyze issue\n2. Implement\n3. Test"
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self._log.warning("Plan generation failed: %s", e)
            return "1. Analyze issue\n2. Implement\n3. Test"

    def evaluate_sufficiency(self, issue: Issue, comments: List[Comment]) -> SufficiencyResult:
        """Use simple heuristic: sufficient if body has some content."""
        if len((issue.body or "").strip()) < 20:
            return SufficiencyResult(
                sufficient=False,
                clarification=("Please add more details: what should be implemented and acceptance criteria."),
            )
        return SufficiencyResult(sufficient=True)

    def generate_code(self, issue: Issue, comments: List[Comment]) -> str | None:
        """Write task file, run Cursor CLI headless, read PR report.

        All run info and CLI stdout/stderr are written to
        .coddy/task-{issue}.log. Returns PR description string for
        create_pr, or None if report missing.
        """
        repo_dir = Path(self.working_directory).resolve()
        task_path = write_task_file(issue, comments, repo_dir)
        report_path = report_file_path(repo_dir, issue.number)
        log_path = task_log_path(repo_dir, issue.number)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        prompt = (
            f"Read and execute the task described in {task_path} (YAML). "
            f"If data is insufficient, add the key 'agent_clarification' to that YAML with your question and stop. "
            f"Otherwise implement and write the PR description to {report_path} (YAML with key 'body')."
        )

        cmd = [self.command, "-p", "--force"]
        if self.output_format:
            cmd.extend(["--output-format", self.output_format])
        if self.stream_partial_output:
            cmd.append("--stream-partial-output")
        if self.model:
            cmd.extend(["--model", self.model])
        if self.mode:
            cmd.extend(["--mode", self.mode])
        cmd.append(prompt)
        env = os.environ.copy()
        if self.token:
            env["CURSOR_API_KEY"] = self.token

        self._log.info("Running Cursor CLI (headless): %s (timeout=%ss)", self.command, self.timeout)
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write(
                    f"[{datetime.now(UTC).isoformat()}] Issue #{issue.number} | "
                    f"command={self.command} timeout={self.timeout}s\n"
                )
                log_file.write(f"Task file: {task_path}\n")
                log_file.write(f"Report file: {report_path}\n")
                log_file.write("-" * 60 + "\n")
                log_file.flush()
                result = subprocess.run(
                    cmd,
                    cwd=self.working_directory,
                    env=env,
                    timeout=self.timeout,
                    check=False,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                log_file.write("-" * 60 + "\n")
                log_file.write(f"Exit code: {result.returncode}\n")
        except subprocess.TimeoutExpired:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write("-" * 60 + "\n")
                log_file.write(f"Timed out after {self.timeout}s\n")
            self._log.warning("Cursor CLI timed out after %s seconds", self.timeout)
        except FileNotFoundError as e:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write("-" * 60 + "\n")
                log_file.write(f"Error: CLI not found: {e}\n")
            self._log.warning("Cursor CLI not found: %s", e)
            return None

        return read_pr_report(repo_dir, issue.number) or None

    def process_review_item(
        self,
        pr_number: int,
        issue_number: int,
        comments: List[ReviewComment],
        current_index: int,
        repo_dir: Path,
    ) -> str | None:
        """Write review task for current item, run Cursor CLI, return reply
        text if any.

        Agent may apply code changes; caller commits and pushes. Reply
        is read from the reply file written by the agent.
        """
        task_path = write_review_task_file(pr_number, issue_number, comments, current_index, Path(repo_dir))
        current = comments[current_index - 1]
        reply_path = review_reply_file_path(Path(repo_dir), pr_number, current.id)
        log_path = Path(repo_dir) / ".coddy" / f"task-{issue_number}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        prompt = (
            f"Read and execute the review task in {task_path} (YAML). "
            f"Address the current item only: apply code changes and/or write your reply to "
            f"{reply_path} (YAML with key 'body'). Then stop."
        )
        cmd = [self.command, "-p", "--force"]
        if self.output_format:
            cmd.extend(["--output-format", self.output_format])
        if self.stream_partial_output:
            cmd.append("--stream-partial-output")
        if self.model:
            cmd.extend(["--model", self.model])
        if self.mode:
            cmd.extend(["--mode", self.mode])
        cmd.append(prompt)
        env = os.environ.copy()
        if self.token:
            env["CURSOR_API_KEY"] = self.token

        self._log.info(
            "Running Cursor CLI for review item %s/%s (timeout=%ss)",
            current_index,
            len(comments),
            self.timeout,
        )
        try:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"[{datetime.now(UTC).isoformat()}] PR #{pr_number} review item {current_index}\n")
                log_file.write(f"Task file: {task_path}\n")
                log_file.write("-" * 60 + "\n")
                log_file.flush()
                result = subprocess.run(
                    cmd,
                    cwd=self.working_directory,
                    env=env,
                    timeout=self.timeout,
                    check=False,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                log_file.write("-" * 60 + "\n")
                log_file.write(f"Exit code: {result.returncode}\n")
        except subprocess.TimeoutExpired:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"Timed out after {self.timeout}s\n")
            self._log.warning("Cursor CLI timed out after %s seconds", self.timeout)
            return None
        except FileNotFoundError as e:
            self._log.warning("Cursor CLI not found: %s", e)
            return None

        return read_review_reply(Path(repo_dir), pr_number, current.id) or None


def make_cursor_cli_agent(config: Any) -> CursorCLIAgent:
    """Build CursorCLIAgent from app config (ai_agents.cursor_cli and resolved
    token)."""
    cfg = getattr(config, "ai_agents", {}).get("cursor_cli") or {}
    token = getattr(config, "cursor_agent_token_resolved", None) or getattr(cfg, "token", None)
    return CursorCLIAgent(
        command=getattr(cfg, "command", "agent"),
        timeout=getattr(cfg, "timeout", 300),
        working_directory=getattr(cfg, "working_directory", "."),
        token=token,
        output_format=getattr(cfg, "output_format", None),
        stream_partial_output=getattr(cfg, "stream_partial_output", False),
        model=getattr(cfg, "model", None),
        mode=getattr(cfg, "mode", None),
    )
