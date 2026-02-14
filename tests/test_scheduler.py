"""Tests for scheduler: pending_plan older than idle_minutes triggers planner."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from coddy.observer.scheduler import run_scheduler_loop


def test_scheduler_runs_planner_when_pending_plan_older_than_idle_minutes(tmp_path: Path) -> None:
    """When a pending_plan issue has assigned_at older than idle_minutes, planner runs once per tick."""
    import yaml

    from coddy.observer.issues import create_issue, load_issue

    create_issue(
        tmp_path,
        issue_number=5,
        repo="owner/repo",
        title="Add feature",
        description="",
        author="@user",
    )
    issue_path = tmp_path / ".coddy" / "issues" / "5.yaml"
    data = yaml.safe_load(issue_path.read_text(encoding="utf-8"))
    data["assigned_at"] = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
    issue_path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    # Ensure issue is loadable and has pending_plan
    loaded = load_issue(tmp_path, 5)
    assert loaded is not None and loaded.status == "pending_plan", "setup: issue file must be pending_plan"

    config = MagicMock()
    config.bot.idle_minutes = 10
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.ai_agent = "cursor_cli"
    config.github_token_resolved = "token"
    config.github.api_url = "https://api.github.com"
    config.ai_agents = {}
    config.scheduler = MagicMock()
    config.scheduler.interval_seconds = 60

    mock_issue = MagicMock()
    mock_issue.number = 5
    mock_issue.title = "Add feature"
    mock_adapter = MagicMock()
    mock_adapter.get_issue.return_value = mock_issue

    with patch("coddy.observer.scheduler.GitHubAdapter", return_value=mock_adapter):
        with patch("coddy.observer.scheduler.run_planner") as mock_run_planner:
            with patch("coddy.observer.scheduler.time.sleep", side_effect=StopIteration("one tick")):
                with pytest.raises(StopIteration, match="one tick"):
                    run_scheduler_loop(config, tmp_path, interval_seconds=60)

    mock_run_planner.assert_called_once()
    call_args = mock_run_planner.call_args[0]
    assert call_args[2] == mock_issue  # issue
    assert call_args[3] == "owner/repo"  # repo


def test_scheduler_skips_pending_plan_when_not_idle_yet(tmp_path: Path) -> None:
    """When assigned_at is within idle_minutes, planner is not called."""
    from coddy.observer.issues import create_issue

    create_issue(tmp_path, 3, "owner/repo", "Fix bug", "", "@u")
    # assigned_at is set to now by create_issue; for "2 min ago" we'd need to patch or rewrite
    # So we rely on: create_issue just ran, so assigned_at is now, delta_minutes < 10

    config = MagicMock()
    config.bot.idle_minutes = 10
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.github_token_resolved = "token"
    config.github.api_url = "https://api.github.com"
    config.ai_agents = {}

    with patch("coddy.observer.scheduler.GitHubAdapter") as mock_adapter_cls:
        with patch("coddy.observer.scheduler.run_planner") as mock_run_planner:
            with patch("coddy.observer.scheduler.time.sleep", side_effect=StopIteration("one tick")):
                with pytest.raises(StopIteration, match="one tick"):
                    run_scheduler_loop(config, tmp_path, interval_seconds=60)

    mock_run_planner.assert_not_called()
    # get_issue should not be called because we skip before that
    mock_adapter_cls.return_value.get_issue.assert_not_called()
