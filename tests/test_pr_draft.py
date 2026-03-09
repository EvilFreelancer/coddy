"""Tests for draft PR status support (open->draft, draft->open, draft->merged,
etc.)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from coddy.observer.webhook.handlers import handle_github_event
from coddy.services.store import load_pr, save_pr, set_pr_status
from coddy.services.store.pr_store import PR_STATUSES
from coddy.services.store.schemas import PRFile

# --- PR store: draft in PR_STATUSES ---


def test_draft_in_pr_statuses() -> None:
    """'draft' must be a valid PR status."""
    assert "draft" in PR_STATUSES


# --- PR store: set_pr_status with draft ---


def test_set_pr_status_creates_draft_file(tmp_path: Path) -> None:
    """set_pr_status with status='draft' creates file in draft/ folder."""
    set_pr_status(tmp_path, 100, "draft", repo="owner/repo")
    pr_file = tmp_path / ".coddy" / "pull_requests" / "draft" / "100.yaml"
    assert pr_file.exists()
    data = yaml.safe_load(pr_file.read_text(encoding="utf-8"))
    assert data["status"] == "draft"


def test_set_pr_status_open_to_draft(tmp_path: Path) -> None:
    """Transition open -> draft: file moves from open/ to draft/."""
    set_pr_status(tmp_path, 101, "open", repo="owner/repo")
    assert (tmp_path / ".coddy" / "pull_requests" / "open" / "101.yaml").exists()

    set_pr_status(tmp_path, 101, "draft", repo="owner/repo")
    assert not (tmp_path / ".coddy" / "pull_requests" / "open" / "101.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "draft" / "101.yaml").exists()

    pr = load_pr(tmp_path, 101)
    assert pr is not None
    assert pr.status == "draft"


def test_set_pr_status_draft_to_open(tmp_path: Path) -> None:
    """Transition draft -> open: file moves from draft/ to open/."""
    set_pr_status(tmp_path, 102, "draft", repo="owner/repo")
    assert (tmp_path / ".coddy" / "pull_requests" / "draft" / "102.yaml").exists()

    set_pr_status(tmp_path, 102, "open", repo="owner/repo")
    assert not (tmp_path / ".coddy" / "pull_requests" / "draft" / "102.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "open" / "102.yaml").exists()

    pr = load_pr(tmp_path, 102)
    assert pr is not None
    assert pr.status == "open"


def test_set_pr_status_draft_to_merged(tmp_path: Path) -> None:
    """Transition draft -> merged: file moves from draft/ to merged/."""
    set_pr_status(tmp_path, 103, "draft", repo="owner/repo")
    set_pr_status(tmp_path, 103, "merged", repo="owner/repo")

    assert not (tmp_path / ".coddy" / "pull_requests" / "draft" / "103.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "merged" / "103.yaml").exists()

    pr = load_pr(tmp_path, 103)
    assert pr is not None
    assert pr.status == "merged"


def test_set_pr_status_draft_to_rejected(tmp_path: Path) -> None:
    """Transition draft -> rejected: file moves from draft/ to rejected/."""
    set_pr_status(tmp_path, 104, "draft", repo="owner/repo")
    set_pr_status(tmp_path, 104, "rejected", repo="owner/repo")

    assert not (tmp_path / ".coddy" / "pull_requests" / "draft" / "104.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "rejected" / "104.yaml").exists()


# --- PR store: load_pr searches draft folder ---


def test_load_pr_finds_draft(tmp_path: Path) -> None:
    """load_pr must find PR file in the draft/ folder."""
    set_pr_status(tmp_path, 105, "draft", repo="owner/repo")
    pr = load_pr(tmp_path, 105)
    assert pr is not None
    assert pr.status == "draft"
    assert pr.pr_id == 105


# --- PR store: save_pr with draft status ---


def test_save_pr_draft_writes_to_draft_folder(tmp_path: Path) -> None:
    """save_pr with status='draft' writes to draft/ folder."""
    pr = PRFile(
        pr_id=106,
        repo="owner/repo",
        status="draft",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    path = save_pr(tmp_path, pr)
    assert "draft" in str(path)
    assert path.exists()


# --- PRFile schema: draft status in description ---


def test_pr_file_accepts_draft_status() -> None:
    """PRFile model must accept 'draft' as status without validation error."""
    pr = PRFile(
        pr_id=107,
        repo="owner/repo",
        status="draft",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    assert pr.status == "draft"


# --- Webhook: converted_to_draft ---


def _make_pr_config(tmp_path: Path) -> object:
    """Create config for PR webhook tests."""
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.default_branch = "main"
    config.bot.username = "coddybot"
    return config


def test_webhook_pr_converted_to_draft(tmp_path: Path) -> None:
    """On pull_request action=converted_to_draft, PR status -> draft."""
    config = _make_pr_config(tmp_path)
    set_pr_status(tmp_path, 200, "open", repo="owner/repo")

    payload = {
        "action": "converted_to_draft",
        "pull_request": {"number": 200, "draft": True},
        "repository": {"full_name": "owner/repo"},
    }
    handle_github_event(config, "pull_request", payload, repo_dir=tmp_path)

    pr = load_pr(tmp_path, 200)
    assert pr is not None
    assert pr.status == "draft"
    assert not (tmp_path / ".coddy" / "pull_requests" / "open" / "200.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "draft" / "200.yaml").exists()


def test_webhook_pr_ready_for_review(tmp_path: Path) -> None:
    """On pull_request action=ready_for_review, PR status -> open."""
    config = _make_pr_config(tmp_path)
    set_pr_status(tmp_path, 201, "draft", repo="owner/repo")

    payload = {
        "action": "ready_for_review",
        "pull_request": {"number": 201, "draft": False},
        "repository": {"full_name": "owner/repo"},
    }
    handle_github_event(config, "pull_request", payload, repo_dir=tmp_path)

    pr = load_pr(tmp_path, 201)
    assert pr is not None
    assert pr.status == "open"
    assert not (tmp_path / ".coddy" / "pull_requests" / "draft" / "201.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "open" / "201.yaml").exists()


def test_webhook_pr_converted_to_draft_other_repo_ignored(tmp_path: Path) -> None:
    """converted_to_draft for another repo is ignored."""
    config = _make_pr_config(tmp_path)
    set_pr_status(tmp_path, 202, "open", repo="owner/repo")

    payload = {
        "action": "converted_to_draft",
        "pull_request": {"number": 202, "draft": True},
        "repository": {"full_name": "other/repo"},
    }
    handle_github_event(config, "pull_request", payload, repo_dir=tmp_path)

    pr = load_pr(tmp_path, 202)
    assert pr is not None
    assert pr.status == "open"


# --- Webhook: closed draft PR -> merged/rejected ---


def test_webhook_draft_pr_closed_merged(tmp_path: Path) -> None:
    """Draft PR closed+merged moves to merged/ folder."""
    config = _make_pr_config(tmp_path)
    set_pr_status(tmp_path, 203, "draft", repo="owner/repo")

    payload = {
        "action": "closed",
        "pull_request": {"number": 203, "merged": True, "draft": True},
        "repository": {"full_name": "owner/repo"},
    }
    with patch("coddy.observer.webhook.handlers.run_git_pull"):
        with patch("coddy.observer.webhook.handlers.sys.exit", side_effect=SystemExit(0)):
            with pytest.raises(SystemExit):
                handle_github_event(config, "pull_request", payload, repo_dir=tmp_path)

    pr = load_pr(tmp_path, 203)
    assert pr is not None
    assert pr.status == "merged"


def test_webhook_draft_pr_closed_rejected(tmp_path: Path) -> None:
    """Draft PR closed without merge moves to rejected/ folder."""
    config = _make_pr_config(tmp_path)
    set_pr_status(tmp_path, 204, "draft", repo="owner/repo")

    payload = {
        "action": "closed",
        "pull_request": {"number": 204, "merged": False, "draft": True},
        "repository": {"full_name": "owner/repo"},
    }
    handle_github_event(config, "pull_request", payload, repo_dir=tmp_path)

    pr = load_pr(tmp_path, 204)
    assert pr is not None
    assert pr.status == "rejected"


# --- Sync: draft PRs detected ---


def test_sync_detects_draft_pr(tmp_path: Path) -> None:
    """run_sync maps open+draft PR to 'draft' status."""
    from coddy.observer.models import PR
    from coddy.observer.sync import run_sync

    config = MagicMock()
    config.bot.repository = "owner/repo"
    config.bot.git_platform = "github"
    config.github_token_resolved = "token"
    config.github.api_url = "https://api.github.com"

    draft_pr = PR(
        number=300,
        title="Draft PR",
        body="WIP",
        head_branch="feature",
        base_branch="main",
        state="open",
        draft=True,
        merged_at=None,
    )
    non_draft_pr = PR(
        number=301,
        title="Ready PR",
        body="Done",
        head_branch="fix",
        base_branch="main",
        state="open",
        draft=False,
        merged_at=None,
    )

    mock_adapter = MagicMock()
    mock_adapter.list_issues.return_value = []
    mock_adapter.list_pulls.return_value = [draft_pr, non_draft_pr]

    with patch("coddy.observer.adapters.github.GitHubAdapter", return_value=mock_adapter):
        run_sync(config, tmp_path)

    assert (tmp_path / ".coddy" / "pull_requests" / "draft" / "300.yaml").exists()
    assert (tmp_path / ".coddy" / "pull_requests" / "open" / "301.yaml").exists()

    pr_draft = load_pr(tmp_path, 300)
    assert pr_draft is not None
    assert pr_draft.status == "draft"

    pr_open = load_pr(tmp_path, 301)
    assert pr_open is not None
    assert pr_open.status == "open"


# --- PR model: draft field ---


def test_pr_model_has_draft_field() -> None:
    """PR observer model must have a 'draft' boolean field."""
    from coddy.observer.models import PR

    pr = PR(
        number=400,
        title="Test",
        body="",
        head_branch="feature",
        base_branch="main",
        state="open",
        draft=True,
    )
    assert pr.draft is True

    pr2 = PR(
        number=401,
        title="Test 2",
        body="",
        head_branch="feature",
        base_branch="main",
        state="open",
    )
    assert pr2.draft is False
