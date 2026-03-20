"""Tests for additional logging: verify #<issue/pr> in log messages."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from coddy.observer.models import Issue
from coddy.observer.webhook.server import WebhookHandler
from coddy.services.git.push_pull import _extract_issue_tag


def _issue(number: int = 1) -> Issue:
    return Issue(
        number=number,
        title="Add login",
        body="Body",
        author="user",
        labels=[],
        state="open",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestHandlersLogging:
    """Webhook handlers include #<issue/pr> in log messages."""

    def test_pr_merged_log_includes_pr_number(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """PR merged log message contains #<pr_number>."""
        from coddy.observer.webhook.handlers import handle_github_event

        config = type("C", (), {})()
        config.bot = type("B", (), {})()
        config.bot.git_platform = "github"
        config.bot.repository = "owner/repo"
        config.bot.default_branch = "main"
        config.bot.workspace_path = str(tmp_path)

        payload = {
            "action": "closed",
            "pull_request": {"merged": True, "number": 55},
            "repository": {"full_name": "owner/repo"},
        }
        with (
            patch("coddy.observer.webhook.handlers.run_git_pull"),
            patch("coddy.observer.webhook.handlers.sys.exit", side_effect=SystemExit(0)),
            caplog.at_level(logging.DEBUG),
        ):
            with pytest.raises(SystemExit):
                handle_github_event(config, "pull_request", payload, repo_dir=tmp_path)

        merged_logs = [r.message for r in caplog.records if "PR #55" in r.message]
        assert merged_logs, "Expected log message with PR #55"

    def test_pr_closed_wrong_repo_log_includes_pr_number(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """PR closed for wrong repo log message contains #<pr_number>."""
        from coddy.observer.webhook.handlers import handle_github_event

        config = type("C", (), {})()
        config.bot = type("B", (), {})()
        config.bot.git_platform = "github"
        config.bot.repository = "owner/repo"
        config.bot.default_branch = "main"

        payload = {
            "action": "closed",
            "pull_request": {"merged": True, "number": 77},
            "repository": {"full_name": "other/repo"},
        }
        with caplog.at_level(logging.DEBUG):
            handle_github_event(config, "pull_request", payload, repo_dir=tmp_path)

        pr_logs = [r.message for r in caplog.records if "#77" in r.message]
        assert pr_logs, "Expected log message with PR #77"

    def test_issue_assigned_log_includes_issue_number(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Issue assigned log message contains #<issue_number>."""
        from coddy.observer.webhook.handlers import handle_github_event

        config = type("C", (), {})()
        config.bot = type("B", (), {})()
        config.bot.git_platform = "github"
        config.bot.repository = "owner/repo"
        config.bot.username = "coddybot"

        payload = {
            "action": "assigned",
            "issue": {
                "number": 42,
                "title": "Add feature",
                "body": "Body",
                "user": {"login": "user1"},
                "assignees": [{"login": "coddybot"}],
            },
            "repository": {"full_name": "owner/repo"},
        }
        with caplog.at_level(logging.DEBUG):
            handle_github_event(config, "issues", payload, repo_dir=tmp_path)

        issue_logs = [r.message for r in caplog.records if "#42" in r.message]
        assert issue_logs, "Expected log message with #42"


class TestRalphLoopLogging:
    """Ralph loop includes #<issue> in log messages."""

    def test_ralph_loop_clarification_log_includes_issue_number(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When data insufficient, clarification log includes #<issue>."""
        from coddy.services.store import create_issue
        from coddy.worker.ralph_loop import run_ralph_loop_for_issue

        create_issue(tmp_path, 10, "owner/repo", "T", "D", "u")
        adapter = MagicMock()
        adapter.get_issue_comments.return_value = []
        agent = MagicMock()
        agent.evaluate_sufficiency.return_value = type(
            "R", (), {"sufficient": False, "clarification": "Need more info."}
        )()
        with caplog.at_level(logging.DEBUG):
            result = run_ralph_loop_for_issue(
                adapter, agent, _issue(10), "owner/repo", tmp_path, default_branch="main", max_iterations=1
            )
        assert result == "clarification"
        issue_logs = [r.message for r in caplog.records if "#10" in r.message]
        assert issue_logs, "Expected log message with #10"

    def test_ralph_loop_branch_error_log_includes_issue_number(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Branch creation failure log includes #<issue>."""
        from coddy.observer.adapters.base import GitPlatformError
        from coddy.worker.ralph_loop import run_ralph_loop_for_issue

        adapter = MagicMock()
        adapter.get_issue_comments.return_value = []
        adapter.create_branch.side_effect = GitPlatformError("403 Forbidden")
        agent = MagicMock()
        agent.evaluate_sufficiency.return_value = type("R", (), {"sufficient": True, "clarification": ""})()
        with caplog.at_level(logging.DEBUG):
            result = run_ralph_loop_for_issue(
                adapter, agent, _issue(5), "owner/repo", tmp_path, default_branch="main", max_iterations=1
            )
        assert result == "failed"
        branch_error_logs = [r.message for r in caplog.records if "#5" in r.message and "branch" in r.message.lower()]
        assert branch_error_logs, "Expected branch error log with #5"

    def test_ralph_loop_success_log_includes_issue_number(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Successful PR creation log includes #<issue>."""
        from coddy.worker.ralph_loop import run_ralph_loop_for_issue

        issue = _issue(3)
        adapter = MagicMock()
        adapter.get_issue_comments.return_value = []
        adapter.get_default_branch.return_value = "main"
        adapter.get_issue.return_value = issue
        adapter.create_branch.side_effect = None
        adapter.create_pr.side_effect = None
        adapter.set_issue_labels.side_effect = None
        agent = MagicMock()
        agent.evaluate_sufficiency.return_value = type("R", (), {"sufficient": True, "clarification": ""})()
        agent.generate_code.return_value = "PR body"

        with (
            patch("coddy.worker.ralph_loop.fetch_and_checkout_branch"),
            patch("coddy.worker.ralph_loop.checkout_branch"),
            patch("coddy.worker.ralph_loop.commit_all_and_push"),
            caplog.at_level(logging.DEBUG),
        ):
            result = run_ralph_loop_for_issue(
                adapter, agent, issue, "owner/repo", tmp_path, default_branch="main", max_iterations=2
            )
        assert result == "success"
        pr_logs = [r.message for r in caplog.records if "#3" in r.message and "PR" in r.message]
        assert pr_logs, "Expected PR creation log with #3"


class TestClarificationPollLogging:
    """Clarification poll includes #<issue> in log messages."""

    def test_clarification_poll_log_includes_issue_number(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Posted clarification log includes #<issue_number>."""
        from coddy.observer.clarification_poll import run_clarification_poll
        from coddy.services.store import create_issue, set_agent_clarification

        create_issue(tmp_path, 8, "owner/repo", "T", "D", "@u")
        set_agent_clarification(tmp_path, 8, "Please clarify.", bot_name="@bot")
        config = MagicMock()
        config.bot.repository = "owner/repo"
        config.bot.git_platform = "github"
        config.github_token_resolved = "token"
        config.github = MagicMock()
        config.github.api_url = "https://api.github.com"

        mock_adapter = MagicMock()
        with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
            with caplog.at_level(logging.DEBUG):
                run_clarification_poll(config, tmp_path)

        issue_logs = [r.message for r in caplog.records if "#8" in r.message]
        assert issue_logs, "Expected log message with #8"


class TestWorkerRunLogging:
    """Worker run includes #<issue> in log messages."""

    def test_worker_dry_run_log_includes_issue_number(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Dry run processing log includes #<issue_number>."""
        from coddy.config import AppConfig, BotConfig
        from coddy.services.store import create_issue, set_issue_status
        from coddy.worker.run import run_worker_poll

        create_issue(tmp_path, 6, "owner/repo", "Dry", "D", "u", assigned_at=1704067200, assigned_to="coddybot")
        set_issue_status(tmp_path, 6, "queued")
        config = AppConfig()
        config.bot = BotConfig(
            workspace_path=str(tmp_path),
            repository="owner/repo",
            assignment_only=True,
            username="coddybot",
        )

        log = logging.getLogger("coddy.worker.test_dry_run")
        with caplog.at_level(logging.DEBUG):
            run_worker_poll(config, tmp_path, adapter=None, agent=None, log=log)

        issue_logs = [r.message for r in caplog.records if "#6" in r.message]
        assert issue_logs, "Expected log message with #6"


class TestPushPullLogging:
    """push_pull includes issue tag from commit_message in logs."""

    def test_extract_issue_tag(self) -> None:
        """_extract_issue_tag extracts #N from commit message."""
        assert _extract_issue_tag("#42 Add login form") == "#42"
        assert _extract_issue_tag("No issue ref") == ""
        assert _extract_issue_tag("#1 Fix") == "#1"

    def test_commit_all_and_push_log_includes_issue_tag(self, caplog: pytest.LogCaptureFixture) -> None:
        """commit_all_and_push logs #<issue> from commit_message."""
        from coddy.services.git.push_pull import commit_all_and_push

        logger = logging.getLogger("test.push_pull")
        with (
            patch("coddy.services.git.push_pull.add_all_and_commit", return_value=True),
            patch("coddy.services.git.push_pull.push_branch"),
            caplog.at_level(logging.DEBUG),
        ):
            commit_all_and_push(
                "42-add-login",
                "#42 Add login",
                "Bot",
                "bot@example.com",
                repo_dir=Path("/tmp"),
                log=logger,
            )

        issue_logs = [r.message for r in caplog.records if "#42" in r.message]
        assert issue_logs, "Expected log message with #42"


class TestWebhookServerLogging:
    """Webhook server extracts #<issue/pr> from payload."""

    def test_extract_number_from_issue_payload(self) -> None:
        """_extract_number_from_payload returns #N for issue payloads."""
        result = WebhookHandler._extract_number_from_payload({"issue": {"number": 42}})
        assert result == "#42"

    def test_extract_number_from_pr_payload(self) -> None:
        """_extract_number_from_payload returns #N for PR payloads."""
        result = WebhookHandler._extract_number_from_payload({"pull_request": {"number": 10}})
        assert result == "#10"

    def test_extract_number_from_empty_payload(self) -> None:
        """_extract_number_from_payload returns empty string when no number."""
        result = WebhookHandler._extract_number_from_payload({})
        assert result == ""

    def test_extract_number_prefers_issue(self) -> None:
        """When both issue and PR present, issue number is preferred."""
        result = WebhookHandler._extract_number_from_payload({"issue": {"number": 5}, "pull_request": {"number": 9}})
        assert result == "#5"
