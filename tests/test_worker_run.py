"""Tests for worker run (queue polling, assignment-only filtering)."""

from pathlib import Path

from coddy.config import AppConfig, BotConfig, LoggingConfig
from coddy.services.store import create_issue, load_issue, set_issue_status
from coddy.worker.run import run_worker


def _make_config(tmp_path: Path, assignment_only: bool = True, username: str | None = "coddybot") -> AppConfig:
    """Build AppConfig with workspace at tmp_path and given bot options."""
    config = AppConfig()
    config.bot = BotConfig(
        workspace=str(tmp_path),
        repository="owner/repo",
        assignment_only=assignment_only,
        username=username,
    )
    config.logging = LoggingConfig()
    config.ai_agents = {}
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
