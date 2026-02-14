"""Tests for webhook handlers (PR merged, review comment, issues flow)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from coddy.services.store import IssueFile, load_issue
from coddy.observer.webhook.handlers import handle_github_event


@pytest.fixture
def config_pr_merged() -> "object":
    """Config with github platform and default_branch."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.default_branch = "main"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": "."})()}
    return config


def test_handle_pr_merged_pulls_and_exits(config_pr_merged: "object") -> None:
    """On pull_request closed+merged, run_git_pull is called and
    sys.exit(0)."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": True, "number": 1},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.observer.webhook.handlers.run_git_pull", create=True) as mock_pull:
        with patch("coddy.observer.webhook.handlers.sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit(0)
            with pytest.raises(SystemExit, match="0"):
                handle_github_event(config_pr_merged, "pull_request", payload)
    mock_pull.assert_called_once()
    call_kw = mock_pull.call_args[1]
    assert call_kw["log"] is not None
    mock_exit.assert_called_once_with(0)


def test_handle_pr_merged_ignores_when_not_merged(config_pr_merged: "object") -> None:
    """pull_request closed but not merged does nothing."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": False},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.observer.webhook.handlers.run_git_pull", create=True) as mock_pull:
        with patch("coddy.observer.webhook.handlers.sys.exit") as mock_exit:
            handle_github_event(config_pr_merged, "pull_request", payload)
    mock_pull.assert_not_called()
    mock_exit.assert_not_called()


def test_handle_pr_merged_ignores_other_repo(config_pr_merged: "object") -> None:
    """pull_request merged for another repo does nothing."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": True},
        "repository": {"full_name": "other/repo"},
    }
    with patch("coddy.observer.webhook.handlers.run_git_pull", create=True) as mock_pull:
        with patch("coddy.observer.webhook.handlers.sys.exit") as mock_exit:
            handle_github_event(config_pr_merged, "pull_request", payload)
    mock_pull.assert_not_called()
    mock_exit.assert_not_called()


def test_handle_pr_merged_uses_repo_dir_when_passed(config_pr_merged: "object") -> None:
    """When repo_dir is passed, run_git_pull is called with that path."""
    payload = {
        "action": "closed",
        "pull_request": {"merged": True},
        "repository": {"full_name": "owner/repo"},
    }
    custom_dir = Path("/tmp/bot-repo")
    with patch("coddy.observer.webhook.handlers.run_git_pull", create=True) as mock_pull:
        with patch("coddy.observer.webhook.handlers.sys.exit", side_effect=SystemExit(0)):
            with pytest.raises(SystemExit):
                handle_github_event(
                    config_pr_merged,
                    "pull_request",
                    payload,
                    repo_dir=custom_dir,
                )
    mock_pull.assert_called_once()
    assert mock_pull.call_args[1]["repo_dir"] == custom_dir


def test_handle_pr_merged_no_exit_on_pull_failure(config_pr_merged: "object") -> None:
    """When run_git_pull raises, we do not call sys.exit."""
    from coddy.services.git import GitRunnerError

    payload = {
        "action": "closed",
        "pull_request": {"merged": True},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.observer.webhook.handlers.run_git_pull", create=True, side_effect=GitRunnerError("pull failed")):
        with patch("coddy.observer.webhook.handlers.sys.exit") as mock_exit:
            handle_github_event(config_pr_merged, "pull_request", payload)
    mock_exit.assert_not_called()


def test_handle_issues_assigned_creates_issue_file_when_bot_in_assignees(tmp_path: Path) -> None:
    """On issues.assigned with bot in assignees, create_issue is called (issue
    file in .coddy/issues/)."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}

    payload = {
        "action": "assigned",
        "issue": {
            "number": 42,
            "title": "Add feature",
            "body": "Please add X",
            "user": {"login": "user1"},
            "assignees": [{"login": "coddy-bot"}, {"login": "other"}],
        },
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.observer.webhook.handlers.create_issue") as mock_create:
        handle_github_event(config, "issues", payload, repo_dir=tmp_path)
    mock_create.assert_called_once()
    call_args = mock_create.call_args[0]
    assert call_args[0] == tmp_path
    assert call_args[1] == 42
    assert call_args[2] == "owner/repo"
    assert call_args[3] == "Add feature"
    assert call_args[4] == "Please add X"
    assert call_args[5] == "user1"


def test_handle_issues_assigned_ignores_when_bot_not_assignee(tmp_path: Path) -> None:
    """On issues.assigned without bot in assignees, create_issue is not
    called."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}

    payload = {
        "action": "assigned",
        "issue": {"number": 42, "assignees": [{"login": "other-user"}]},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.observer.webhook.handlers.create_issue") as mock_create:
        handle_github_event(config, "issues", payload, repo_dir=tmp_path)
    mock_create.assert_not_called()


def test_handle_issue_comment_calls_on_user_confirmed_when_affirmative(tmp_path: Path) -> None:
    """On issue_comment with issue status waiting_confirmation and affirmative
    body, on_user_confirmed is called."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.github = type("GitHub", (), {"api_url": "https://api.github.com"})()
    config.github_token_resolved = "token"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}

    payload = {
        "action": "created",
        "comment": {"body": "да, устраивает", "user": {"login": "user1"}},
        "issue": {"number": 7},
        "repository": {"full_name": "owner/repo"},
    }
    issue_file = IssueFile(
        author="@u",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        status="waiting_confirmation",
        title="Fix bug",
        description="",
    )
    with patch("coddy.observer.webhook.handlers.load_issue", return_value=issue_file):
        with patch("coddy.observer.webhook.handlers.on_user_confirmed") as mock_confirm:
            handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
    mock_confirm.assert_called_once()
    call_kw = mock_confirm.call_args[1]
    assert call_kw["comment_author"] == "user1"
    assert "устраивает" in call_kw["comment_body"]
    assert call_kw["bot_username"] == "coddy-bot"


def test_handle_issue_comment_ignores_when_not_waiting_confirmation(tmp_path: Path) -> None:
    """On issue_comment when issue is not waiting_confirmation,
    on_user_confirmed is not called."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.github_token_resolved = "token"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}

    payload = {
        "action": "created",
        "comment": {"body": "да", "user": {"login": "user1"}},
        "issue": {"number": 8},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.observer.webhook.handlers.load_issue", return_value=None):
        with patch("coddy.observer.webhook.handlers.on_user_confirmed") as mock_confirm:
            handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
    mock_confirm.assert_not_called()


def test_handle_issue_comment_ignores_bot_comment(tmp_path: Path) -> None:
    """On issue_comment from bot user, on_user_confirmed is not called."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.github_token_resolved = "token"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}

    payload = {
        "action": "created",
        "comment": {"body": "да", "user": {"login": "coddy-bot"}},
        "issue": {"number": 9},
        "repository": {"full_name": "owner/repo"},
    }
    issue_file = IssueFile(
        author="@u",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        status="waiting_confirmation",
        title="T",
    )
    with patch("coddy.observer.webhook.handlers.load_issue", return_value=issue_file):
        with patch("coddy.observer.webhook.handlers.on_user_confirmed") as mock_confirm:
            handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
    mock_confirm.assert_not_called()


# --- Issue flow integration tests (real state/queue on tmp_path) ---


def _issues_assigned_config(tmp_path: Path) -> "object":
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.github_username = "coddy-bot"
    config.ai_agents = {"cursor_cli": type("CLI", (), {"working_directory": str(tmp_path)})()}
    return config


def test_webhook_issues_assigned_creates_issue_file(tmp_path: Path) -> None:
    """On issues.assigned (bot in assignees), issue file is created; without
    token status stays pending_plan."""
    config = _issues_assigned_config(tmp_path)
    payload = {
        "action": "assigned",
        "issue": {
            "number": 42,
            "title": "Add login form",
            "body": "Add a form with email and password.",
            "user": {"login": "author1"},
            "assignees": [{"login": "coddy-bot"}],
        },
        "repository": {"full_name": "owner/repo"},
    }
    handle_github_event(config, "issues", payload, repo_dir=tmp_path)

    issue_path = tmp_path / ".coddy" / "issues" / "42.yaml"
    assert issue_path.exists(), "Issue file should be created"
    content = issue_path.read_text(encoding="utf-8")
    assert "pending_plan" in content
    assert "owner/repo" in content
    assert "Add login form" in content
    assert "assigned_at" in content

    issue = load_issue(tmp_path, 42)
    assert issue is not None
    assert issue.status == "pending_plan"
    assert issue.issue_id == 42
    assert issue.repo == "owner/repo"
    assert issue.title == "Add login form"
    assert len(issue.comments) == 1
    assert "Add login form" in issue.comments[0].content


def test_webhook_issues_assigned_runs_planner_when_token_set(tmp_path: Path) -> None:
    """On issues.assigned with token, planner runs and status becomes
    waiting_confirmation."""
    from coddy.services.store import set_issue_status

    config = _issues_assigned_config(tmp_path)
    config.github_token_resolved = "gh-token"
    config.github = type("GitHub", (), {"api_url": "https://api.github.com"})()

    payload = {
        "action": "assigned",
        "issue": {
            "number": 43,
            "title": "Add feature",
            "body": "Body",
            "user": {"login": "u"},
            "assignees": [{"login": "coddy-bot"}],
        },
        "repository": {"full_name": "owner/repo"},
    }

    mock_issue = MagicMock()
    mock_issue.number = 43
    mock_issue.title = "Add feature"
    mock_issue.body = "Body"
    mock_adapter = MagicMock()
    mock_adapter.get_issue.return_value = mock_issue

    def fake_run_planner(adapter, agent, issue, repo, repo_dir, **kwargs):
        set_issue_status(repo_dir, issue.number, "waiting_confirmation")

    with patch("coddy.observer.webhook.handlers.GitHubAdapter", return_value=mock_adapter):
        with patch("coddy.observer.webhook.handlers.run_planner", side_effect=fake_run_planner):
            with patch("coddy.observer.webhook.handlers.make_cursor_cli_agent", return_value=MagicMock()):
                handle_github_event(config, "issues", payload, repo_dir=tmp_path)

    issue = load_issue(tmp_path, 43)
    assert issue is not None
    assert issue.status == "waiting_confirmation"
    mock_adapter.get_issue.assert_called_once_with("owner/repo", 43)


def test_webhook_issue_comment_affirmative_sets_queued(tmp_path: Path) -> None:
    """On issue_comment with waiting_confirmation and affirmative reply,
    status=queued (worker picks from .coddy/issues/)."""
    from coddy.services.store import create_issue, list_queued, set_issue_status

    create_issue(tmp_path, 7, "owner/repo", "Fix bug", "Description", "user1")
    set_issue_status(tmp_path, 7, "waiting_confirmation")
    assert (tmp_path / ".coddy" / "issues" / "7.yaml").exists()

    config = _issues_assigned_config(tmp_path)
    config.github = type("GitHub", (), {"api_url": "https://api.github.com"})()
    config.github_token_resolved = "gh-token"
    payload = {
        "action": "created",
        "comment": {"body": "yes, go ahead", "user": {"login": "user1"}},
        "issue": {"number": 7},
        "repository": {"full_name": "owner/repo"},
    }

    mock_adapter = MagicMock()
    with patch("coddy.observer.webhook.handlers.GitHubAdapter", return_value=mock_adapter):
        handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)

    issue = load_issue(tmp_path, 7)
    assert issue is not None
    assert issue.status == "queued"

    queued = list_queued(tmp_path)
    assert len(queued) == 1
    assert queued[0][0] == 7
    assert queued[0][1].title == "Fix bug"
    assert queued[0][1].repo == "owner/repo"

    mock_adapter.create_comment.assert_called_once()
