"""
Cursor CLI agent: headless mode with task YAML and PR report YAML.

Coddy writes .coddy/task-{n}.yaml. Agent runs and either: (1) implements and writes
.coddy/pr-{n}.yaml for PR body, or (2) finds data insufficient and adds
agent_clarification to the task YAML and stops; Coddy reads that
and posts it to the issue. Run log is in .coddy/logs/{n}.log.
"""

import json
import logging
import os
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List


def _extract_plan_from_cli_output(raw: str) -> str | None:
    """Extract final plan text from Cursor CLI output (JSON lines or stream-
    json).

    Looks for type 'assistant' with message.content[].type 'text', or
    type 'result' with a string result. Returns the last such text so
    the issue comment shows only the plan, not raw JSON.
    """
    last_plan: str | None = None
    for line in (raw or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind == "assistant":
            msg = obj.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            t = item.get("text")
                            if isinstance(t, str):
                                parts.append(t)
                    if parts:
                        last_plan = "\n".join(parts)
        elif kind == "result" and obj.get("subtype") == "success":
            result = obj.get("result")
            if isinstance(result, str):
                last_plan = result
    return last_plan.strip() if (last_plan and last_plan.strip()) else None


# Substrings in CLI stderr that suggest a transient error (worth retrying).
_TRANSIENT_PLAN_ERRORS = (
    "Connection stalled",
    "ECONNRESET",
    "ETIMEDOUT",
    "Connection reset",
    "timeout",
    "T: Connection stalled",
)

from coddy.observer.models import Comment, Issue, ReviewComment
from coddy.worker.agents.base import AIAgent, SufficiencyResult
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
    """Run Cursor CLI in headless mode (-p --force) with task YAML context.

    Task is written to .coddy/task-{issue_number}.yaml; agent is asked
    to execute it and write PR description to
    .coddy/pr-{issue_number}.yaml.
    """

    def __init__(
        self,
        command: str = "agent",
        timeout: int = 600,
        working_directory: str = ".",
        token: str | None = None,
        output_format: str | None = "stream-json",
        stream_partial_output: bool = False,
        stream_output_to_log: bool = False,
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
        self.stream_output_to_log = stream_output_to_log
        self.model = model
        self.mode = mode
        self._log = log or logging.getLogger("coddy.worker.agents.cursor_cli")

    def generate_plan(self, issue: Issue, comments: List[Comment]) -> str | None:
        """Run Cursor CLI with a plan-only prompt; return plan text in issue
        language.

        Retries on transient errors (e.g. connection stalled).
        """
        prompt = (
            f"You are a planner. The user created an issue. Output ONLY a short implementation plan "
            f"(bullet points, no code). Use the same language as the issue. "
            f"Issue title: {issue.title!r}\n\nBody:\n{issue.body or '(none)'}\n\n"
            "Output only the plan, nothing else."
        )
        cmd = [self.command, "--print", "--force"]
        if self.output_format:
            cmd.extend(["--output-format", self.output_format])
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.append(prompt)
        env = os.environ.copy()
        if self.token:
            env["CURSOR_API_KEY"] = self.token

        max_attempts = 3
        retry_delay_sec = 10
        last_out = ""
        last_code: int | None = None

        for attempt in range(1, max_attempts + 1):
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
                last_out = out.strip() or "(no output)"
                last_code = result.returncode

                if result.returncode == 0:
                    plan = _extract_plan_from_cli_output(out)
                    if plan:
                        return plan
                    # Plain text format or unparseable
                    return out.strip() or "1. Analyze issue\n2. Implement\n3. Test"

                is_transient = any(
                    phrase in (result.stdout or "") or phrase in (result.stderr or "")
                    for phrase in _TRANSIENT_PLAN_ERRORS
                )
                if is_transient and attempt < max_attempts:
                    self._log.warning(
                        "Issue #%s: plan generation attempt %s/%s failed (exit %s, transient): %s; retrying in %ss",
                        issue.number,
                        attempt,
                        max_attempts,
                        result.returncode,
                        last_out[:200],
                        retry_delay_sec,
                    )
                    time.sleep(retry_delay_sec)
                    continue

                self._log.error(
                    "Issue #%s: plan generation failed (exit %s): %s",
                    issue.number,
                    result.returncode,
                    last_out,
                )
                return None
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                self._log.exception("Issue #%s: plan generation failed: %s", issue.number, e)
                return None

        self._log.error(
            "Issue #%s: plan generation failed after %s attempts (exit %s): %s",
            issue.number,
            max_attempts,
            last_code,
            last_out,
        )
        return None

    def evaluate_sufficiency(self, issue: Issue, comments: List[Comment]) -> SufficiencyResult:
        """Use simple heuristic: sufficient if body has some content."""
        if len((issue.body or "").strip()) < 20:
            return SufficiencyResult(
                sufficient=False,
                clarification=("Please add more details: what should be implemented and acceptance criteria."),
            )
        return SufficiencyResult(sufficient=True)

    def generate_code(self, issue: Issue, comments: List[Comment]) -> str | None:
        """Write task YAML, run Cursor CLI headless, read PR report.

        All run info and CLI stdout/stderr are written to
        .coddy/logs/{issue}.log. Returns PR description string for
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

        self._log.info(
            "Issue #%s: running Cursor CLI (headless): %s (timeout=%ss)", issue.number, self.command, self.timeout
        )
        try:
            if self.stream_output_to_log:
                result = self._run_with_streaming_log(cmd, env, log_path, issue.number)
            else:
                result = self._run_with_file_log(cmd, env, log_path, issue.number)
            if result is not None:
                log_suffix = "-" * 60 + f"\nExit code: {result.returncode}\n"
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_suffix)
        except subprocess.TimeoutExpired:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write("-" * 60 + "\n")
                log_file.write(f"Timed out after {self.timeout}s\n")
            self._log.warning("Issue #%s: Cursor CLI timed out after %s seconds", issue.number, self.timeout)
        except FileNotFoundError as e:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write("-" * 60 + "\n")
                log_file.write(f"Error: CLI not found: {e}\n")
            self._log.warning("Issue #%s: Cursor CLI not found: %s", issue.number, e)
            return None

        return read_pr_report(repo_dir, issue.number) or None

    def _run_with_file_log(
        self,
        cmd: List[str],
        env: dict[str, Any],
        log_path: Path,
        issue_number: int,
    ) -> subprocess.CompletedProcess[str] | None:
        """Run CLI with stdout/stderr redirected to log file."""
        coddy_dir = log_path.parent.parent  # .coddy/logs/N.log -> .coddy
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(
                f"[{datetime.now(UTC).isoformat()}] Issue #{issue_number} | "
                f"command={self.command} timeout={self.timeout}s\n"
            )
            log_file.write(f"Task file: {coddy_dir / f'task-{issue_number}.yaml'}\n")
            log_file.write(f"Report file: {coddy_dir / f'pr-{issue_number}.yaml'}\n")
            log_file.write("-" * 60 + "\n")
            log_file.flush()
            return subprocess.run(
                cmd,
                cwd=self.working_directory,
                env=env,
                timeout=self.timeout,
                check=False,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

    def _run_with_streaming_log(
        self,
        cmd: List[str],
        env: dict[str, Any],
        log_path: Path,
        issue_number: int,
    ) -> subprocess.CompletedProcess[str] | None:
        """Run CLI and stream stdout/stderr to log file and to logger (real-
        time debug)."""
        coddy_dir = log_path.parent.parent  # .coddy/logs/N.log -> .coddy
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(
                f"[{datetime.now(UTC).isoformat()}] Issue #{issue_number} | "
                f"command={self.command} timeout={self.timeout}s\n"
            )
            log_file.write(f"Task file: {coddy_dir / f'task-{issue_number}.yaml'}\n")
            log_file.write(f"Report file: {coddy_dir / f'pr-{issue_number}.yaml'}\n")
            log_file.write("-" * 60 + "\n")
            log_file.flush()
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.working_directory,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except FileNotFoundError:
                raise
            lines_done: list[bool] = [False]

            def read_and_log() -> None:
                assert proc.stdout is not None
                for line in proc.stdout:
                    log_file.write(line)
                    log_file.flush()
                    self._log.debug("agent: %s", line.rstrip("\n"))
                lines_done[0] = True

            t = threading.Thread(target=read_and_log, daemon=True)
            t.start()
            try:
                proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise
            t.join(timeout=2.0)
            return subprocess.CompletedProcess(proc.args, proc.returncode or 0, "", "")

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
        log_path = task_log_path(Path(repo_dir), issue_number)
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
            "PR #%s (issue #%s): running Cursor CLI for review item %s/%s (timeout=%ss)",
            pr_number,
            issue_number,
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
            self._log.warning(
                "PR #%s (issue #%s): Cursor CLI timed out after %s seconds", pr_number, issue_number, self.timeout
            )
            return None
        except FileNotFoundError as e:
            self._log.warning("PR #%s (issue #%s): Cursor CLI not found: %s", pr_number, issue_number, e)
            return None

        return read_review_reply(Path(repo_dir), pr_number, current.id) or None


def make_cursor_cli_agent(config: Any) -> CursorCLIAgent:
    """Build CursorCLIAgent from app config (ai_agents.cursor_cli and resolved
    token).

    Agent CWD is always bot.workspace_path.
    """
    cfg = getattr(config, "ai_agents", {}).get("cursor_cli") or {}
    token = getattr(config, "cursor_agent_token_resolved", None) or getattr(cfg, "token", None)
    workspace = getattr(config.bot, "workspace_path", ".") or "."
    return CursorCLIAgent(
        command=getattr(cfg, "command", "agent"),
        timeout=getattr(cfg, "timeout", 600),
        working_directory=workspace,
        token=token,
        output_format=getattr(cfg, "output_format", None),
        stream_partial_output=getattr(cfg, "stream_partial_output", False),
        model=getattr(cfg, "model", None),
        mode=getattr(cfg, "mode", None),
    )
