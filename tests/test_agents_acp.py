"""Tests for ACP agent integration in worker."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from coddy.config import AppConfig, BotConfig
from coddy.observer.models import Issue, ReviewComment


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


def test_local_acp_client_merges_message_chunks_and_plan_updates() -> None:
    """Session text must include both message stream and plan stream from
    ACP."""
    import logging

    from coddy.worker.agents.acp_agent import _LocalACPClient

    client = _LocalACPClient(
        logging.getLogger("test.acp"),
        ".",
        30,
        True,
        True,
        True,
    )
    client.reset_session("s1")
    client._text_chunks["s1"] = ["Short ack"]
    client._plan_chunks["s1"] = ["## Plan\n\n- Step one\n- Step two"]
    assert client.get_session_text("s1") == "Short ack\n\n## Plan\n\n- Step one\n- Step two"


def test_local_acp_client_returns_plan_when_message_is_prefix_of_plan() -> None:
    """If message text is contained in plan text, avoid duplicating."""
    import logging

    from coddy.worker.agents.acp_agent import _LocalACPClient

    client = _LocalACPClient(
        logging.getLogger("test.acp"),
        ".",
        30,
        True,
        True,
        True,
    )
    client.reset_session("s1")
    client._text_chunks["s1"] = ["Intro"]
    client._plan_chunks["s1"] = ["Intro\n\nFull plan details here."]
    assert client.get_session_text("s1") == "Intro\n\nFull plan details here."


def test_local_acp_client_concatenates_streaming_message_chunks_without_breaks() -> None:
    """Streamed assistant deltas must be joined in order with no separator."""
    import logging

    from coddy.worker.agents.acp_agent import _LocalACPClient

    client = _LocalACPClient(
        logging.getLogger("test.acp"),
        ".",
        30,
        True,
        True,
        True,
    )
    client.reset_session("s1")
    client._text_chunks["s1"] = ["confi", "rmation", " ", "and ", "`coddy/observer/webhook/handlers.py`"]
    assert client.get_session_text("s1") == "confirmation and `coddy/observer/webhook/handlers.py`"


def test_acp_agent_generate_plan_returns_agent_text(tmp_path: Path) -> None:
    """ACP agent should return text gathered from ACP updates."""
    from coddy.worker.agents.acp_agent import ACPAgent

    agent = ACPAgent(command="agent", args=["acp"], timeout=30, working_directory=str(tmp_path))

    with patch.object(agent, "_run_prompt", return_value="## Plan\n\n- Step 1\n- Step 2"):
        plan = agent.generate_plan(_issue(number=1), [])

    assert plan == "## Plan\n\n- Step 1\n- Step 2"


def test_acp_agent_generate_code_reads_pr_report(tmp_path: Path) -> None:
    """ACP generate_code should return PR body from report file."""
    from coddy.worker.agents.acp_agent import ACPAgent

    agent = ACPAgent(command="agent", args=["acp"], timeout=30, working_directory=str(tmp_path))
    issue = _issue(number=7)
    report_path = tmp_path / ".coddy" / "pr-7.yaml"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("body: PR description from ACP\n", encoding="utf-8")

    with patch.object(agent, "_run_prompt", return_value="Done"):
        result = agent.generate_code(issue, [])

    assert result == "PR description from ACP"


def test_acp_agent_process_review_item_reads_reply(tmp_path: Path) -> None:
    """ACP review processing should return YAML reply body."""
    from coddy.worker.agents.acp_agent import ACPAgent

    agent = ACPAgent(command="agent", args=["acp"], timeout=30, working_directory=str(tmp_path))
    review_comment = ReviewComment(
        id=10,
        body="Please fix it",
        author="reviewer",
        path="file.py",
        line=12,
        side="RIGHT",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    reply_path = tmp_path / ".coddy" / "review-reply-5-10.yaml"
    reply_path.parent.mkdir(parents=True, exist_ok=True)
    reply_path.write_text("body: Applied fix\n", encoding="utf-8")

    with patch.object(agent, "_run_prompt", return_value="Done"):
        reply = agent.process_review_item(
            pr_number=5,
            issue_number=2,
            comments=[review_comment],
            current_index=1,
            repo_dir=tmp_path,
        )

    assert reply == "Applied fix"


def test_make_acp_agent_passes_cursor_token_to_child_env(tmp_path: Path) -> None:
    """Resolved CURSOR_AGENT_TOKEN should be passed to ACP process env."""
    import coddy.config as config_module
    from coddy.worker.agents.acp_agent import make_acp_agent

    config = AppConfig()
    config.bot = BotConfig(workspace_path=str(tmp_path), repository="owner/repo")
    old_env = getattr(config_module, "_current_env", {})
    try:
        secret_file = tmp_path / "cursor_token"
        secret_file.write_text("token-value\n", encoding="utf-8")
        config_module._current_env = {
            **old_env,
            "CURSOR_AGENT_TOKEN_FILE": str(secret_file),
        }
        agent = make_acp_agent(config)
    finally:
        config_module._current_env = old_env

    assert agent.env["CURSOR_AGENT_TOKEN"] == "token-value"
    assert agent.env["CURSOR_API_KEY"] == "token-value"
