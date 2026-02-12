"""Tests for CursorCLIAgent (headless mode, task/report/log files)."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from coddy.agents.cursor_cli_agent import CursorCLIAgent
from coddy.models import Issue


def _issue(number: int = 42, body: str = "Enough body for sufficiency check.") -> Issue:
    return Issue(
        number=number,
        title="Test issue",
        body=body,
        author="user",
        labels=[],
        state="open",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_cursor_cli_agent_writes_log_file(tmp_path: Path, mocker: MagicMock) -> None:
    """generate_code writes .coddy/task-{issue}.log with header and CLI
    output."""
    mock_run = mocker.patch("coddy.agents.cursor_cli_agent.subprocess.run")
    mock_run.return_value = MagicMock(returncode=0)
    mocker.patch(
        "coddy.agents.cursor_cli_agent.read_pr_report",
        return_value="PR description",
    )
    agent = CursorCLIAgent(
        command="agent",
        timeout=60,
        working_directory=str(tmp_path),
    )
    issue = _issue(number=7)
    result = agent.generate_code(issue, [])
    assert result == "PR description"
    log_path = tmp_path / ".coddy" / "task-7.log"
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "Issue #7" in content
    assert "command=agent" in content
    assert "timeout=60" in content
    assert "Task file:" in content
    assert "Report file:" in content
    assert "Exit code: 0" in content


def test_cursor_cli_agent_log_file_on_timeout(tmp_path: Path, mocker: MagicMock) -> None:
    """On timeout, log file is appended with timeout message."""
    mocker.patch("coddy.agents.cursor_cli_agent.subprocess.run").side_effect = __import__("subprocess").TimeoutExpired(
        "agent", 60
    )
    agent = CursorCLIAgent(
        command="agent",
        timeout=60,
        working_directory=str(tmp_path),
    )
    issue = _issue(number=8)
    result = agent.generate_code(issue, [])
    assert result is None
    log_path = tmp_path / ".coddy" / "task-8.log"
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "Timed out after 60s" in content


def test_cursor_cli_agent_log_file_on_cli_not_found(tmp_path: Path, mocker: MagicMock) -> None:
    """On FileNotFoundError, log file is appended with error."""
    mocker.patch("coddy.agents.cursor_cli_agent.subprocess.run").side_effect = FileNotFoundError("agent not found")
    agent = CursorCLIAgent(
        command="agent",
        timeout=60,
        working_directory=str(tmp_path),
    )
    issue = _issue(number=9)
    result = agent.generate_code(issue, [])
    assert result is None
    log_path = tmp_path / ".coddy" / "task-9.log"
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "CLI not found" in content or "not found" in content


def test_cursor_cli_agent_passes_cli_params_to_subprocess(tmp_path: Path, mocker: MagicMock) -> None:
    """When output_format, model, mode, stream_partial_output are set, they
    appear in cmd."""
    mock_run = mocker.patch("coddy.agents.cursor_cli_agent.subprocess.run")
    mock_run.return_value = MagicMock(returncode=0)
    mocker.patch("coddy.agents.cursor_cli_agent.read_pr_report", return_value="")
    agent = CursorCLIAgent(
        command="agent",
        timeout=60,
        working_directory=str(tmp_path),
        output_format="stream-json",
        stream_partial_output=True,
        model="Claude 4 Sonnet",
        mode="plan",
    )
    agent.generate_code(_issue(number=10), [])
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert cmd[0] == "agent"
    assert "-p" in cmd and "--force" in cmd
    assert "--output-format" in cmd
    idx = cmd.index("--output-format")
    assert cmd[idx + 1] == "stream-json"
    assert "--stream-partial-output" in cmd
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "Claude 4 Sonnet"
    assert "--mode" in cmd
    assert cmd[cmd.index("--mode") + 1] == "plan"
