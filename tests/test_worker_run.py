"""Tests for worker run (queue polling, assignment-only filtering)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coddy.config import AppConfig, BotConfig, LoggingConfig, load_config
from coddy.observer.webhook.handlers import handle_github_event
from coddy.services.store import create_issue, load_issue, set_issue_status
from coddy.worker.run import run_worker


def _make_config(tmp_path: Path, assignment_only: bool = True, username: str | None = "coddybot") -> AppConfig:
    """Build AppConfig with workspace_path at tmp_path and given bot
    options."""
    config = AppConfig()
    config.bot = BotConfig(
        workspace_path=str(tmp_path),
        repository="owner/repo",
        assignment_only=assignment_only,
        username=username,
    )
    config.logging = LoggingConfig()
    return config


def test_worker_processes_only_issues_assigned_to_bot_when_assignment_only(tmp_path: Path) -> None:
    """When assignment_only=True and username=coddybot, worker processes only
    issues with assigned_to=coddybot."""
    create_issue(
        tmp_path,
        issue_id=1,
        repo="owner/repo",
        title="Assigned to bot",
        description="D",
        author="u",
        assigned_at=1704067200,
        assigned_to="coddybot",
    )
    set_issue_status(tmp_path, 1, "queued")

    create_issue(
        tmp_path,
        issue_id=2,
        repo="owner/repo",
        title="Assigned to other",
        description="D",
        author="u",
        assigned_at=1704067200,
        assigned_to="other-user",
    )
    set_issue_status(tmp_path, 2, "queued")

    config = _make_config(tmp_path, assignment_only=True, username="coddybot")
    run_worker(config, once=True)

    # Issue 1 (coddybot) should be processed: report written, status done
    issue1 = load_issue(tmp_path, 1)
    assert issue1 is not None
    assert issue1.status == "done"
    report1 = tmp_path / ".coddy" / "pr-1.yaml"
    assert report1.exists()

    # Issue 2 (other-user) should remain queued, no report
    issue2 = load_issue(tmp_path, 2)
    assert issue2 is not None
    assert issue2.status == "queued"
    report2 = tmp_path / ".coddy" / "pr-2.yaml"
    assert not report2.exists()


def test_worker_processes_any_queued_issue_when_assignment_only_false(tmp_path: Path) -> None:
    """When assignment_only=False, worker processes first queued issue
    regardless of assigned_to."""
    create_issue(
        tmp_path,
        issue_id=3,
        repo="owner/repo",
        title="No assignee",
        description="D",
        author="u",
    )
    set_issue_status(tmp_path, 3, "queued")

    config = _make_config(tmp_path, assignment_only=False, username="coddybot")
    run_worker(config, once=True)

    issue3 = load_issue(tmp_path, 3)
    assert issue3 is not None
    assert issue3.status == "done"
    assert (tmp_path / ".coddy" / "pr-3.yaml").exists()


def test_worker_skips_all_when_assignment_only_and_no_username(tmp_path: Path) -> None:
    """When assignment_only=True and username is None, worker processes no
    issues (logs warning and exits with --once)."""
    create_issue(
        tmp_path,
        issue_id=4,
        repo="owner/repo",
        title="Queued",
        description="D",
        author="u",
        assigned_at=1704067200,
        assigned_to="coddybot",
    )
    set_issue_status(tmp_path, 4, "queued")

    config = _make_config(tmp_path, assignment_only=True, username=None)
    run_worker(config, once=True)

    # Issue should still be queued (worker skipped it)
    issue4 = load_issue(tmp_path, 4)
    assert issue4 is not None
    assert issue4.status == "queued"
    assert not (tmp_path / ".coddy" / "pr-4.yaml").exists()


def test_worker_skips_issue_with_no_assignee_when_assignment_only(tmp_path: Path) -> None:
    """When assignment_only=True, issues without assigned_to are skipped."""
    create_issue(
        tmp_path,
        issue_id=5,
        repo="owner/repo",
        title="No assignee",
        description="D",
        author="u",
    )
    set_issue_status(tmp_path, 5, "queued")

    config = _make_config(tmp_path, assignment_only=True, username="coddybot")
    run_worker(config, once=True)

    issue5 = load_issue(tmp_path, 5)
    assert issue5 is not None
    assert issue5.status == "queued"
    assert not (tmp_path / ".coddy" / "pr-5.yaml").exists()


def test_worker_config_has_poll_interval_seconds(tmp_path: Path) -> None:
    """AppConfig has worker with poll_interval_seconds; load_config reads
    worker section from YAML."""
    config = AppConfig()
    assert hasattr(config, "worker")
    assert getattr(config.worker, "poll_interval_seconds", None) >= 1

    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "bot:\n  repository: owner/repo\nworker:\n  poll_interval_seconds: 5\n",
        encoding="utf-8",
    )
    loaded = load_config(yaml_path)
    assert loaded.worker.poll_interval_seconds == 5


def test_worker_polls_bot_workspace_not_cursor_working_directory(tmp_path: Path) -> None:
    """Worker reads .coddy/issues/ only from bot.workspace_path (same as
    observer)."""
    import coddy.config as config_module
    from coddy.config import ACPAgentConfig

    store_dir = tmp_path / "store"
    store_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    create_issue(
        store_dir,
        issue_id=20,
        repo="owner/repo",
        title="Need plan",
        description="Body",
        author="u",
        assigned_at=1704067200,
        assigned_to="coddybot",
    )
    set_issue_status(store_dir, 20, "pending_plan")
    assert load_issue(store_dir, 20).status == "pending_plan"

    config = AppConfig()
    config.bot = BotConfig(
        workspace_path=str(store_dir),
        repository="owner/repo",
        assignment_only=True,
        username="coddybot",
    )
    config.bot.git_platform = "github"
    config.logging = LoggingConfig()
    config.github = MagicMock()
    config.github.api_url = "https://api.github.com"
    config.acp = ACPAgentConfig()

    mock_agent = MagicMock()
    mock_agent.generate_plan.return_value = "1. Step one\n2. Step two"

    old_env = getattr(config_module, "_current_env", {})
    try:
        config_module._current_env = {**old_env, "GITHUB_TOKEN": "token"}
        with patch("coddy.worker.agents.acp_agent.make_acp_agent", return_value=mock_agent):
            with patch("coddy.observer.adapters.github.GitHubAdapter"):
                run_worker(config, once=True)
    finally:
        config_module._current_env = old_env

    issue = load_issue(store_dir, 20)
    assert issue is not None
    assert issue.status == "plan_ready"
    assert len(issue.comments) == 1
    assert "Step one" in (issue.comments[0].content or "")


def test_worker_builds_plan_without_github_token_when_acp_enabled(tmp_path: Path) -> None:
    """Worker should process pending_plan with ACP agent even without GitHub
    token."""
    from coddy.config import ACPAgentConfig

    create_issue(
        tmp_path,
        issue_id=21,
        repo="owner/repo",
        title="Need plan without token",
        description="Body",
        author="u",
        assigned_at=1704067200,
        assigned_to="coddybot",
    )
    set_issue_status(tmp_path, 21, "pending_plan")
    assert load_issue(tmp_path, 21).status == "pending_plan"

    config = AppConfig()
    config.bot = BotConfig(
        workspace_path=str(tmp_path),
        repository="owner/repo",
        assignment_only=True,
        username="coddybot",
    )
    config.bot.git_platform = "github"
    config.acp = ACPAgentConfig()
    config.logging = LoggingConfig()
    config.github = MagicMock()
    config.github.api_url = "https://api.github.com"

    mock_agent = MagicMock()
    mock_agent.generate_plan.return_value = "1. Plan step"

    with patch("coddy.worker.agents.acp_agent.make_acp_agent", return_value=mock_agent):
        run_worker(config, once=True)

    issue = load_issue(tmp_path, 21)
    assert issue is not None
    assert issue.status == "plan_ready"
    assert len(issue.comments) == 1
    assert "Plan step" in (issue.comments[0].content or "")


def test_worker_processes_issue_when_bot_not_first_assignee_in_webhook_payload(tmp_path: Path) -> None:
    """Issue assigned to bot should be processed even if bot is not first in
    assignees."""
    config = _make_config(tmp_path, assignment_only=True, username="coddybot")

    payload = {
        "action": "assigned",
        "issue": {
            "number": 45,
            "title": "Need plan",
            "body": "Body",
            "user": {"login": "u"},
            "assignees": [{"login": "other-user"}, {"login": "coddybot"}],
        },
        "repository": {"full_name": "owner/repo"},
    }
    handle_github_event(config, "issues", payload, repo_dir=tmp_path)
    assert load_issue(tmp_path, 45).status == "pending_plan"

    mock_agent = MagicMock()
    mock_agent.generate_plan.return_value = "1. Plan from worker"
    with patch("coddy.worker.agents.acp_agent.make_acp_agent", return_value=mock_agent):
        config.bot.git_platform = "github"
        run_worker(config, once=True)

    issue = load_issue(tmp_path, 45)
    assert issue is not None
    assert issue.status == "plan_ready"
    assert "Plan from worker" in (issue.comments[0].content or "")


def test_worker_uses_acp_when_config_contains_legacy_ai_agent_key(tmp_path: Path) -> None:
    """Worker should initialize ACP even when config YAML still has legacy
    ai_agent key."""
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        (
            "bot:\n"
            "  workspace_path: " + str(tmp_path) + "\n"
            "  repository: owner/repo\n"
            "  assignment_only: true\n"
            "  username: coddybot\n"
            "  ai_agent: cursor_cli\n"
            "  git_platform: github\n"
        ),
        encoding="utf-8",
    )
    config = load_config(yaml_path)
    config.bot.workspace_path = str(tmp_path)

    create_issue(
        tmp_path,
        issue_id=46,
        repo="owner/repo",
        title="Need plan",
        description="Body",
        author="u",
        assigned_at=1704067200,
        assigned_to="coddybot",
    )
    set_issue_status(tmp_path, 46, "pending_plan")

    mock_agent = MagicMock()
    mock_agent.generate_plan.return_value = "1. ACP plan"
    with patch("coddy.worker.agents.acp_agent.make_acp_agent", return_value=mock_agent):
        run_worker(config, once=True)

    issue = load_issue(tmp_path, 46)
    assert issue is not None
    assert issue.status == "plan_ready"
