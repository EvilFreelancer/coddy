"""ACP-based AI agent implementation for worker loops."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

from acp import spawn_agent_process, text_block
from acp.interfaces import Agent, Client
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AllowedOutcome,
    AvailableCommandsUpdate,
    ClientCapabilities,
    ConfigOptionUpdate,
    CreateTerminalResponse,
    CurrentModeUpdate,
    DeniedOutcome,
    FileSystemCapability,
    KillTerminalCommandResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    SessionInfoUpdate,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
    UserMessageChunk,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
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


class _LocalACPClient(Client):
    """ACP client implementation that exposes local fs and terminal tools."""

    def __init__(
        self,
        log: logging.Logger,
        working_directory: str,
        timeout: int,
        allow_fs_read: bool,
        allow_fs_write: bool,
        allow_terminal: bool,
    ) -> None:
        self._log = log
        self._working_directory = Path(working_directory).resolve()
        self._timeout = timeout
        self._allow_fs_read = allow_fs_read
        self._allow_fs_write = allow_fs_write
        self._allow_terminal = allow_terminal
        self._conn: Agent | None = None
        self._text_chunks: Dict[str, List[str]] = {}
        self._plan_chunks: Dict[str, List[str]] = {}
        self._terminal_processes: Dict[str, asyncio.subprocess.Process] = {}
        self._terminal_buffers: Dict[str, str] = {}
        self._terminal_counter = 0

    def on_connect(self, conn: Agent) -> None:
        self._conn = conn

    def reset_session(self, session_id: str) -> None:
        self._text_chunks[session_id] = []
        self._plan_chunks[session_id] = []

    def get_session_text(self, session_id: str) -> str:
        chunks = self._text_chunks.get(session_id, [])
        text = "\n".join([c for c in chunks if c.strip()]).strip()
        if text:
            return text
        plans = self._plan_chunks.get(session_id, [])
        return "\n".join([c for c in plans if c.strip()]).strip()

    async def request_permission(
        self, options: List[PermissionOption], session_id: str, tool_call: ToolCallUpdate, **kwargs: Any
    ) -> RequestPermissionResponse:
        if options:
            return RequestPermissionResponse(outcome=AllowedOutcome(outcome="selected", option_id=options[0].option_id))
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(
        self,
        session_id: str,
        update: UserMessageChunk
        | AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress
        | AgentPlanUpdate
        | AvailableCommandsUpdate
        | CurrentModeUpdate
        | ConfigOptionUpdate
        | SessionInfoUpdate
        | UsageUpdate,
        **kwargs: Any,
    ) -> None:
        if isinstance(update, AgentMessageChunk):
            content = getattr(update, "content", None)
            text = getattr(content, "text", None) if content is not None else None
            if isinstance(text, str) and text.strip():
                self._text_chunks.setdefault(session_id, []).append(text)
        elif isinstance(update, AgentPlanUpdate):
            lines = [entry.content for entry in update.entries if getattr(entry, "content", "")]
            if lines:
                self._plan_chunks.setdefault(session_id, []).append("\n".join(lines))

    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        if not self._allow_fs_write:
            return None
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return WriteTextFileResponse()

    async def read_text_file(
        self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any
    ) -> ReadTextFileResponse:
        if not self._allow_fs_read:
            return ReadTextFileResponse(content="")
        p = Path(path)
        if not p.is_file():
            return ReadTextFileResponse(content="")
        data = p.read_text(encoding="utf-8")
        if line is None and limit is None:
            return ReadTextFileResponse(content=data)
        lines = data.splitlines(keepends=True)
        start = max((line or 1) - 1, 0)
        end = start + limit if limit is not None else None
        return ReadTextFileResponse(content="".join(lines[start:end]))

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: List[str] | None = None,
        cwd: str | None = None,
        env: List[Any] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        if not self._allow_terminal:
            self._terminal_counter += 1
            terminal_id = f"term-{self._terminal_counter}"
            self._terminal_buffers[terminal_id] = ""
            return CreateTerminalResponse(terminal_id=terminal_id)

        process = await asyncio.create_subprocess_exec(
            command,
            *(args or []),
            cwd=cwd or str(self._working_directory),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._terminal_counter += 1
        terminal_id = f"term-{self._terminal_counter}"
        self._terminal_processes[terminal_id] = process
        self._terminal_buffers[terminal_id] = ""
        return CreateTerminalResponse(terminal_id=terminal_id)

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        process = self._terminal_processes.get(terminal_id)
        if process and process.stdout:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=0.01)
                if chunk:
                    self._terminal_buffers[terminal_id] += chunk.decode("utf-8", errors="replace")
            except TimeoutError:
                pass
        from acp.schema import TerminalExitStatus, TerminalOutputResponse

        exit_status = None
        if process and process.returncode is not None:
            exit_status = TerminalExitStatus(exit_code=process.returncode, signal=None)
        return TerminalOutputResponse(
            output=self._terminal_buffers.get(terminal_id, ""),
            truncated=False,
            exit_status=exit_status,
        )

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        process = self._terminal_processes.get(terminal_id)
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        self._terminal_processes.pop(terminal_id, None)
        self._terminal_buffers.pop(terminal_id, None)
        return ReleaseTerminalResponse()

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        process = self._terminal_processes.get(terminal_id)
        if process is None:
            return WaitForTerminalExitResponse(exit_code=1, signal=None)
        await process.wait()
        return WaitForTerminalExitResponse(exit_code=process.returncode, signal=None)

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalCommandResponse | None:
        process = self._terminal_processes.get(terminal_id)
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        return KillTerminalCommandResponse()

    async def ext_method(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self._conn is None:
            return {}
        return await self._conn.ext_method(method, params)

    async def ext_notification(self, method: str, params: Dict[str, Any]) -> None:
        if self._conn is None:
            return
        await self._conn.ext_notification(method, params)


class ACPAgent(AIAgent):
    """Run ACP-compatible code agents via stdio transport."""

    def __init__(
        self,
        command: str = "agent",
        args: List[str] | None = None,
        timeout: int = 600,
        working_directory: str = ".",
        mode: str | None = None,
        model: str | None = None,
        allow_fs_read: bool = True,
        allow_fs_write: bool = True,
        allow_terminal: bool = True,
        env: Dict[str, str] | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self.command = command
        self.args = args or ["acp"]
        self.timeout = timeout
        self.working_directory = working_directory
        self.mode = mode
        self.model = model
        self.allow_fs_read = allow_fs_read
        self.allow_fs_write = allow_fs_write
        self.allow_terminal = allow_terminal
        self.env = env or {}
        self._log = log or logging.getLogger("coddy.worker.agents.acp")
        self._client = _LocalACPClient(
            log=self._log,
            working_directory=self.working_directory,
            timeout=self.timeout,
            allow_fs_read=self.allow_fs_read,
            allow_fs_write=self.allow_fs_write,
            allow_terminal=self.allow_terminal,
        )

    def evaluate_sufficiency(self, issue: Issue, comments: List[Comment]) -> SufficiencyResult:
        if len((issue.body or "").strip()) < 20:
            return SufficiencyResult(
                sufficient=False,
                clarification="Please add more details: what should be implemented and acceptance criteria.",
            )
        return SufficiencyResult(sufficient=True)

    def generate_plan(self, issue: Issue, comments: List[Comment]) -> str | None:
        recent = comments[-10:] if comments else []
        thread_lines = [f"- {c.author}: {c.body}" for c in recent]
        thread_block = "\n".join(thread_lines) if thread_lines else "(none)"
        feedback_block = ""
        if recent:
            feedback_block = (
                "The thread below may include user feedback on a previous plan. If so, revise the plan to "
                "incorporate their feedback; do not repeat the previous plan verbatim.\n\n"
                f"Recent thread (last up to 10 comments):\n{thread_block}\n\n"
            )
        prompt = (
            "You are a planner. The user created an issue. Output ONLY a short implementation plan "
            "(bullet points, no code). Use the same language as the issue. "
            f"Issue title: {issue.title!r}\n\nBody:\n{issue.body or '(none)'}\n\n"
            f"{feedback_block}"
            "Output only the plan, nothing else."
        )
        try:
            out = self._run_prompt(prompt)
            return out or None
        except Exception as e:
            self._log.exception("Issue #%s: ACP plan generation failed: %s", issue.number, e)
            return None

    def generate_code(self, issue: Issue, comments: List[Comment]) -> str | None:
        repo_dir = Path(self.working_directory).resolve()
        task_path = write_task_file(issue, comments, repo_dir)
        report_path = report_file_path(repo_dir, issue.number)
        log_path = task_log_path(repo_dir, issue.number)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_log_header(log_path, issue.number, task_path, report_path)
        prompt = (
            f"Read and execute the task described in {task_path} (YAML). "
            "If data is insufficient, add the key 'agent_clarification' to that YAML with your question and stop. "
            f"Otherwise implement and write the PR description to {report_path} (YAML with key 'body')."
        )
        try:
            out = self._run_prompt(prompt)
            self._append_log(log_path, out or "")
            self._append_log(log_path, "\n" + "-" * 60 + "\nExit code: 0\n")
        except TimeoutError:
            self._append_log(log_path, "\n" + "-" * 60 + f"\nTimed out after {self.timeout}s\n")
            self._log.warning("Issue #%s: ACP prompt timed out after %s seconds", issue.number, self.timeout)
            return None
        except Exception as e:
            self._append_log(log_path, "\n" + "-" * 60 + f"\nError: {e}\n")
            self._log.warning("Issue #%s: ACP prompt failed: %s", issue.number, e)
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
        task_path = write_review_task_file(pr_number, issue_number, comments, current_index, Path(repo_dir))
        current = comments[current_index - 1]
        reply_path = review_reply_file_path(Path(repo_dir), pr_number, current.id)
        log_path = task_log_path(Path(repo_dir), issue_number)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        prompt = (
            f"Read and execute the review task in {task_path} (YAML). "
            f"Address the current item only: apply code changes and/or write your reply to {reply_path} "
            "(YAML with key 'body'). Then stop."
        )
        try:
            out = self._run_prompt(prompt)
            self._append_log(
                log_path, f"[{datetime.now(UTC).isoformat()}] PR #{pr_number} review item {current_index}\n"
            )
            self._append_log(log_path, out or "")
        except Exception as e:
            self._append_log(log_path, f"\nError: {e}\n")
            self._log.warning("PR #%s (issue #%s): ACP review run failed: %s", pr_number, issue_number, e)
            return None
        return read_review_reply(Path(repo_dir), pr_number, current.id) or None

    def _run_prompt(self, prompt: str) -> str:
        return asyncio.run(self._run_prompt_async(prompt))

    async def _run_prompt_async(self, prompt: str) -> str:
        env = os.environ.copy()
        env.update(self.env)
        async with spawn_agent_process(
            self._client,
            self.command,
            *self.args,
            env=env,
            cwd=self.working_directory,
        ) as (conn, _proc):
            caps = ClientCapabilities(
                fs=FileSystemCapability(
                    read_text_file=self.allow_fs_read,
                    write_text_file=self.allow_fs_write,
                ),
                terminal=self.allow_terminal,
            )
            await conn.initialize(protocol_version=1, client_capabilities=caps)
            session = await conn.new_session(cwd=str(Path(self.working_directory).resolve()), mcp_servers=[])
            self._client.reset_session(session.session_id)
            if self.mode:
                try:
                    await conn.set_session_mode(mode_id=self.mode, session_id=session.session_id)
                except Exception:
                    self._log.debug("ACP agent does not support session mode=%s", self.mode)
            if self.model:
                try:
                    await conn.set_session_model(model_id=self.model, session_id=session.session_id)
                except Exception:
                    self._log.debug("ACP agent does not support model=%s", self.model)

            await asyncio.wait_for(
                conn.prompt(session_id=session.session_id, prompt=[text_block(prompt)]),
                timeout=self.timeout,
            )
            return self._client.get_session_text(session.session_id)

    def _write_log_header(self, log_path: Path, issue_number: int, task_path: Path, report_path: Path) -> None:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                f"[{datetime.now(UTC).isoformat()}] Issue #{issue_number} | "
                f"command={self.command} args={self.args} timeout={self.timeout}s\n"
            )
            f.write(f"Task file: {task_path}\n")
            f.write(f"Report file: {report_path}\n")
            f.write("-" * 60 + "\n")

    def _append_log(self, log_path: Path, text: str) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(text)


def make_acp_agent(config: Any) -> ACPAgent:
    """Build ACPAgent from app config (acp section)."""
    cfg = getattr(config, "acp", None) or {}
    command = list(getattr(cfg, "command", ["agent", "acp"]) or ["agent", "acp"])
    command_bin = command[0]
    command_args = command[1:]
    workspace = getattr(config.bot, "workspace_path", ".") or "."
    env_cfg = getattr(cfg, "env", None) or {}
    return ACPAgent(
        command=command_bin,
        args=command_args,
        timeout=getattr(cfg, "timeout", 600),
        working_directory=workspace,
        env=dict(env_cfg),
    )
