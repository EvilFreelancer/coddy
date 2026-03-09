"""Tests for observer startup sync (issues and PRs from API to .coddy/)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coddy.observer.sync import run_sync
from coddy.services.store import create_issue, load_issue, set_issue_status


def test_run_sync_skips_when_no_repository() -> None:
    """run_sync does nothing when config has no repository."""
    config = MagicMock()
    config.bot.repository = ""
    config.bot.git_platform = "github"
    config.github_token_resolved = "token"
    config.github.api_url = "https://api.github.com"
    repo_dir = Path("/tmp/empty")
    run_sync(config, repo_dir)
    # No exception; no adapter calls (we skip before creating adapter)


def test_run_sync_skips_when_no_token() -> None:
    """run_sync does nothing when no GitHub token."""
    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = None
    repo_dir = Path("/tmp/empty")
    run_sync(config, repo_dir)


def test_run_sync_creates_issues_and_prs_in_folders(tmp_path: Path) -> None:
    """run_sync creates issue files in open/closed and PR files in
    open/merged/rejected."""
    from datetime import datetime

    from coddy.observer.models import PR, Issue

    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = "gh-token"
    config.github.api_url = "https://api.github.com"

    open_issue = Issue(
        number=1,
        title="Open issue",
        body="Body",
        author="user",
        labels=[],
        state="open",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 2),
    )
    closed_issue = Issue(
        number=2,
        title="Closed issue",
        body="Body",
        author="user",
        labels=[],
        state="closed",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 3),
    )
    open_pr = PR(
        number=10,
        title="Open PR",
        body="",
        head_branch="feature",
        base_branch="main",
        state="open",
        merged_at=None,
    )
    merged_pr = PR(
        number=11,
        title="Merged PR",
        body="",
        head_branch="fix",
        base_branch="main",
        state="closed",
        merged_at=datetime(2024, 1, 5),
    )

    mock_adapter = MagicMock()
    mock_adapter.list_issues.side_effect = lambda repo, state: ([open_issue] if state == "open" else [closed_issue])
    mock_adapter.list_pulls.return_value = [open_pr, merged_pr]

    with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
        run_sync(config, tmp_path)

    assert (tmp_path / ".coddy" / "issues" / "open" / "1.yaml").exists()
    assert (tmp_path / ".coddy" / "issues" / "closed" / "2.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "open" / "10.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "merged" / "11.yaml").exists()


def test_run_sync_preserves_existing_issue_status(tmp_path: Path) -> None:
    """run_sync updates title/description but keeps existing workflow
    status."""
    create_issue(
        tmp_path,
        3,
        "owner/repo",
        "Old title",
        "Old body",
        "user",
        state="open",
    )
    set_issue_status(tmp_path, 3, "queued")

    from datetime import datetime

    from coddy.observer.models import Issue

    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = "token"
    config.github.api_url = "https://api.github.com"

    api_issue = Issue(
        number=3,
        title="New title",
        body="New body",
        author="user",
        labels=[],
        state="open",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 5),
    )
    mock_adapter = MagicMock()
    mock_adapter.list_issues.side_effect = lambda repo, state: [api_issue] if state == "open" else []
    mock_adapter.list_pulls.return_value = []

    with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
        run_sync(config, tmp_path)

    issue = load_issue(tmp_path, 3)
    assert issue is not None
    assert issue.title == "New title"
    assert issue.description == "New body"
    assert issue.status == "queued"
