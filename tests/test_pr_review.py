"""Tests for PR review feature: schemas, store functions, webhook handlers,
idle timeout, worker processing, and review loop."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from coddy.observer.clarification_poll import run_review_idle_poll
from coddy.observer.webhook.handlers import handle_github_event
from coddy.services.store import (
    add_review,
    add_review_comment,
    list_prs_by_workflow_status,
    load_pr,
    save_pr,
    set_pr_status,
    set_pr_workflow_status,
)
from coddy.services.store.schemas import PRFile, PRReview, PRReviewComment

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestPRReviewSchemas:
    """Tests for PRReview and PRReviewComment pydantic models."""

    def test_pr_review_comment_all_fields(self) -> None:
        c = PRReviewComment(
            comment_id=100,
            name="reviewer",
            content="Fix this line",
            path="src/main.py",
            line=42,
            created_at=1000,
            updated_at=1000,
            in_reply_to_id=None,
        )
        assert c.comment_id == 100
        assert c.name == "reviewer"
        assert c.content == "Fix this line"
        assert c.path == "src/main.py"
        assert c.line == 42
        assert c.in_reply_to_id is None

    def test_pr_review_comment_minimal(self) -> None:
        c = PRReviewComment(name="u", content="ok", created_at=0, updated_at=0)
        assert c.comment_id is None
        assert c.path == ""
        assert c.line is None
        assert c.in_reply_to_id is None

    def test_pr_review_all_fields(self) -> None:
        comment = PRReviewComment(name="u", content="c", created_at=1, updated_at=1)
        r = PRReview(
            review_id=10,
            author="reviewer",
            state="changes_requested",
            body="Please fix",
            comments=[comment],
            created_at=1000,
        )
        assert r.review_id == 10
        assert r.author == "reviewer"
        assert r.state == "changes_requested"
        assert r.body == "Please fix"
        assert len(r.comments) == 1
        assert r.created_at == 1000

    def test_pr_review_minimal(self) -> None:
        r = PRReview(author="u", created_at=0)
        assert r.review_id is None
        assert r.state == "commented"
        assert r.body == ""
        assert r.comments == []

    def test_pr_file_has_reviews_and_workflow_status(self) -> None:
        pr = PRFile(
            pr_id=1,
            repo="o/r",
            status="open",
            workflow_status="idle",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert pr.workflow_status == "idle"
        assert pr.reviews == []
        assert pr.last_review_ts is None

    def test_pr_file_with_reviews(self) -> None:
        review = PRReview(
            review_id=1,
            author="u",
            state="commented",
            body="text",
            comments=[
                PRReviewComment(
                    comment_id=10,
                    name="u",
                    content="fix",
                    path="a.py",
                    line=5,
                    created_at=100,
                    updated_at=100,
                )
            ],
            created_at=100,
        )
        pr = PRFile(
            pr_id=2,
            repo="o/r",
            reviews=[review],
            last_review_ts=100,
            workflow_status="review_received",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert len(pr.reviews) == 1
        assert pr.reviews[0].comments[0].path == "a.py"
        assert pr.last_review_ts == 100
        assert pr.workflow_status == "review_received"


# ---------------------------------------------------------------------------
# Store function tests
# ---------------------------------------------------------------------------


class TestPRStoreReviewFunctions:
    """Tests for add_review, add_review_comment, set_pr_workflow_status,
    list_prs_by_workflow_status."""

    def test_add_review_creates_review_in_pr(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 10, "open", repo="o/r")
        add_review(tmp_path, 10, review_id=1, author="user1", state="commented", body="Looks ok", created_at=500)
        pr = load_pr(tmp_path, 10)
        assert pr is not None
        assert len(pr.reviews) == 1
        assert pr.reviews[0].review_id == 1
        assert pr.reviews[0].author == "user1"
        assert pr.reviews[0].state == "commented"
        assert pr.reviews[0].body == "Looks ok"
        assert pr.workflow_status == "review_received"
        assert pr.last_review_ts == 500

    def test_add_review_updates_existing_review(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 11, "open", repo="o/r")
        add_review(tmp_path, 11, review_id=1, author="u", state="commented", body="old", created_at=100)
        add_review(tmp_path, 11, review_id=1, author="u", state="changes_requested", body="new", created_at=200)
        pr = load_pr(tmp_path, 11)
        assert pr is not None
        assert len(pr.reviews) == 1
        assert pr.reviews[0].state == "changes_requested"
        assert pr.reviews[0].body == "new"

    def test_add_review_when_pr_not_found_does_nothing(self, tmp_path: Path) -> None:
        add_review(tmp_path, 999, review_id=1, author="u", state="commented", body="", created_at=0)
        assert load_pr(tmp_path, 999) is None

    def test_add_review_comment_creates_comment_in_review(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 20, "open", repo="o/r")
        add_review(tmp_path, 20, review_id=1, author="u", state="commented", body="", created_at=100)
        add_review_comment(
            tmp_path,
            20,
            review_id=1,
            comment_id=50,
            author="u",
            content="Fix this",
            path="src/app.py",
            line=10,
            created_at=200,
        )
        pr = load_pr(tmp_path, 20)
        assert pr is not None
        assert len(pr.reviews) == 1
        assert len(pr.reviews[0].comments) == 1
        c = pr.reviews[0].comments[0]
        assert c.comment_id == 50
        assert c.content == "Fix this"
        assert c.path == "src/app.py"
        assert c.line == 10
        assert pr.workflow_status == "review_received"
        assert pr.last_review_ts == 200

    def test_add_review_comment_creates_ad_hoc_review_when_no_match(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 21, "open", repo="o/r")
        add_review_comment(
            tmp_path,
            21,
            review_id=None,
            comment_id=60,
            author="u",
            content="Issue here",
            path="b.py",
            line=5,
            created_at=300,
        )
        pr = load_pr(tmp_path, 21)
        assert pr is not None
        assert len(pr.reviews) == 1
        assert pr.reviews[0].review_id is None
        assert len(pr.reviews[0].comments) == 1

    def test_add_review_comment_updates_existing_comment(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 22, "open", repo="o/r")
        add_review(tmp_path, 22, review_id=5, author="u", state="commented", body="", created_at=50)
        add_review_comment(
            tmp_path,
            22,
            review_id=5,
            comment_id=70,
            author="u",
            content="Original",
            path="c.py",
            line=1,
            created_at=100,
        )
        add_review_comment(
            tmp_path,
            22,
            review_id=5,
            comment_id=70,
            author="u",
            content="Edited",
            path="c.py",
            line=2,
            created_at=200,
        )
        pr = load_pr(tmp_path, 22)
        assert pr is not None
        total_comments = sum(len(r.comments) for r in pr.reviews)
        assert total_comments == 1
        assert pr.reviews[0].comments[0].content == "Edited"

    def test_add_review_comment_with_in_reply_to(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 23, "open", repo="o/r")
        add_review_comment(
            tmp_path,
            23,
            review_id=None,
            comment_id=80,
            author="u",
            content="Reply",
            path="d.py",
            line=3,
            created_at=400,
            in_reply_to_id=50,
        )
        pr = load_pr(tmp_path, 23)
        assert pr is not None
        assert pr.reviews[0].comments[0].in_reply_to_id == 50

    def test_add_review_comment_when_pr_not_found_does_nothing(self, tmp_path: Path) -> None:
        add_review_comment(
            tmp_path,
            999,
            review_id=None,
            comment_id=1,
            author="u",
            content="x",
            path="a.py",
            line=1,
            created_at=0,
        )
        assert load_pr(tmp_path, 999) is None

    def test_set_pr_workflow_status(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 30, "open", repo="o/r")
        set_pr_workflow_status(tmp_path, 30, "pending_plan")
        pr = load_pr(tmp_path, 30)
        assert pr is not None
        assert pr.workflow_status == "pending_plan"

    def test_set_pr_workflow_status_when_pr_not_found(self, tmp_path: Path) -> None:
        set_pr_workflow_status(tmp_path, 999, "idle")
        assert load_pr(tmp_path, 999) is None

    def test_list_prs_by_workflow_status(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 40, "open", repo="o/r")
        set_pr_status(tmp_path, 41, "open", repo="o/r")
        set_pr_workflow_status(tmp_path, 40, "review_received")
        result = list_prs_by_workflow_status(tmp_path, "review_received")
        assert len(result) == 1
        assert result[0][0] == 40

    def test_list_prs_by_workflow_status_empty(self, tmp_path: Path) -> None:
        assert list_prs_by_workflow_status(tmp_path, "review_received") == []

    def test_pr_review_roundtrip_yaml(self, tmp_path: Path) -> None:
        """Save a PR with reviews and load it back - verify all data persists."""
        review = PRReview(
            review_id=5,
            author="reviewer",
            state="changes_requested",
            body="Please address",
            comments=[
                PRReviewComment(
                    comment_id=100,
                    name="reviewer",
                    content="Fix indentation",
                    path="main.py",
                    line=15,
                    created_at=1000,
                    updated_at=1000,
                    in_reply_to_id=None,
                ),
                PRReviewComment(
                    comment_id=101,
                    name="reviewer",
                    content="Missing docstring",
                    path="utils.py",
                    line=3,
                    created_at=1001,
                    updated_at=1001,
                ),
            ],
            created_at=1000,
        )
        pr = PRFile(
            pr_id=50,
            repo="o/r",
            status="open",
            workflow_status="review_received",
            reviews=[review],
            last_review_ts=1001,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        save_pr(tmp_path, pr)
        loaded = load_pr(tmp_path, 50)
        assert loaded is not None
        assert loaded.workflow_status == "review_received"
        assert loaded.last_review_ts == 1001
        assert len(loaded.reviews) == 1
        assert loaded.reviews[0].review_id == 5
        assert loaded.reviews[0].state == "changes_requested"
        assert len(loaded.reviews[0].comments) == 2
        assert loaded.reviews[0].comments[0].path == "main.py"
        assert loaded.reviews[0].comments[1].path == "utils.py"


# ---------------------------------------------------------------------------
# Webhook handler tests
# ---------------------------------------------------------------------------


def _make_review_config(tmp_path: Path) -> object:
    config = type("Config", (), {})()
    config.bot = type("Bot", (), {})()
    config.bot.git_platform = "github"
    config.bot.repository = "owner/repo"
    config.bot.username = "coddybot"
    config.bot.workspace_path = str(tmp_path)
    config.github = type("GitHub", (), {"api_url": "https://api.github.com"})()
    config.github_token_resolved = "token"
    return config


class TestWebhookPullRequestReview:
    """Tests for pull_request_review event handler."""

    def test_review_submitted_stores_in_pr(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 5, "open", repo="owner/repo")
        payload = {
            "action": "submitted",
            "review": {
                "id": 100,
                "user": {"login": "reviewer1"},
                "state": "changes_requested",
                "body": "Fix these issues",
                "submitted_at": "2024-06-01T12:00:00Z",
            },
            "pull_request": {"number": 5},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 5)
        assert pr is not None
        assert len(pr.reviews) == 1
        assert pr.reviews[0].review_id == 100
        assert pr.reviews[0].author == "reviewer1"
        assert pr.reviews[0].state == "changes_requested"
        assert pr.reviews[0].body == "Fix these issues"
        assert pr.workflow_status == "pending_plan"

    def test_review_submitted_ignores_bot_review(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 6, "open", repo="owner/repo")
        payload = {
            "action": "submitted",
            "review": {
                "id": 101,
                "user": {"login": "coddybot"},
                "state": "commented",
                "body": "Self review",
                "submitted_at": "2024-06-01T12:00:00Z",
            },
            "pull_request": {"number": 6},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 6)
        assert pr is not None
        assert len(pr.reviews) == 0

    def test_review_submitted_ignores_other_repo(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        payload = {
            "action": "submitted",
            "review": {"id": 1, "user": {"login": "u"}, "state": "commented", "body": ""},
            "pull_request": {"number": 1},
            "repository": {"full_name": "other/repo"},
        }
        handle_github_event(config, "pull_request_review", payload, repo_dir=tmp_path)
        assert load_pr(tmp_path, 1) is None

    def test_review_submitted_ignores_non_submitted_action(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 7, "open", repo="owner/repo")
        payload = {
            "action": "dismissed",
            "review": {"id": 1, "user": {"login": "u"}, "state": "commented", "body": ""},
            "pull_request": {"number": 7},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 7)
        assert pr is not None
        assert len(pr.reviews) == 0

    def test_review_submitted_creates_pr_if_missing(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        payload = {
            "action": "submitted",
            "review": {
                "id": 200,
                "user": {"login": "reviewer"},
                "state": "commented",
                "body": "Note",
                "submitted_at": "2024-06-01T12:00:00Z",
            },
            "pull_request": {"number": 99},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 99)
        assert pr is not None
        assert len(pr.reviews) == 1


class TestWebhookPullRequestReviewComment:
    """Tests for pull_request_review_comment event handler."""

    def test_review_comment_created_stores_in_pr(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 10, "open", repo="owner/repo")
        payload = {
            "action": "created",
            "comment": {
                "id": 500,
                "user": {"login": "reviewer1"},
                "body": "Rename this variable",
                "path": "coddy/main.py",
                "line": 42,
                "pull_request_review_id": None,
                "in_reply_to_id": None,
                "created_at": "2024-06-01T12:00:00Z",
                "updated_at": "2024-06-01T12:00:00Z",
            },
            "pull_request": {"number": 10},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 10)
        assert pr is not None
        assert pr.workflow_status == "pending_plan"
        all_comments = [c for r in pr.reviews for c in r.comments]
        assert len(all_comments) == 1
        assert all_comments[0].comment_id == 500
        assert all_comments[0].content == "Rename this variable"
        assert all_comments[0].path == "coddy/main.py"
        assert all_comments[0].line == 42

    def test_review_comment_edited_updates_content(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 11, "open", repo="owner/repo")
        add_review(tmp_path, 11, review_id=50, author="u", state="commented", body="", created_at=100)
        base = {
            "pull_request": {"number": 11},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(
            config,
            "pull_request_review_comment",
            {
                **base,
                "action": "created",
                "comment": {
                    "id": 600,
                    "user": {"login": "u"},
                    "body": "Original",
                    "path": "a.py",
                    "line": 1,
                    "pull_request_review_id": 50,
                    "created_at": "2024-06-01T12:00:00Z",
                },
            },
            repo_dir=tmp_path,
        )
        handle_github_event(
            config,
            "pull_request_review_comment",
            {
                **base,
                "action": "edited",
                "comment": {
                    "id": 600,
                    "user": {"login": "u"},
                    "body": "Edited",
                    "path": "a.py",
                    "line": 2,
                    "pull_request_review_id": 50,
                    "created_at": "2024-06-01T12:00:00Z",
                },
            },
            repo_dir=tmp_path,
        )
        pr = load_pr(tmp_path, 11)
        assert pr is not None
        all_comments = [c for r in pr.reviews for c in r.comments]
        assert len(all_comments) == 1
        assert all_comments[0].content == "Edited"

    def test_review_comment_ignores_bot(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 12, "open", repo="owner/repo")
        payload = {
            "action": "created",
            "comment": {
                "id": 700,
                "user": {"login": "coddybot"},
                "body": "Auto reply",
                "path": "a.py",
                "line": 1,
                "pull_request_review_id": None,
                "created_at": "2024-06-01T12:00:00Z",
            },
            "pull_request": {"number": 12},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 12)
        assert pr is not None
        assert len(pr.reviews) == 0

    def test_review_comment_creates_pr_if_missing(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        payload = {
            "action": "created",
            "comment": {
                "id": 800,
                "user": {"login": "reviewer"},
                "body": "Missing",
                "path": "x.py",
                "line": 5,
                "pull_request_review_id": None,
                "created_at": "2024-06-01T12:00:00Z",
            },
            "pull_request": {"number": 98},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 98)
        assert pr is not None

    def test_review_comment_with_reply_to(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 13, "open", repo="owner/repo")
        payload = {
            "action": "created",
            "comment": {
                "id": 900,
                "user": {"login": "reviewer"},
                "body": "Clarification",
                "path": "b.py",
                "line": 3,
                "pull_request_review_id": 50,
                "in_reply_to_id": 800,
                "created_at": "2024-06-01T12:00:00Z",
            },
            "pull_request": {"number": 13},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "pull_request_review_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 13)
        assert pr is not None
        all_comments = [c for r in pr.reviews for c in r.comments]
        assert len(all_comments) == 1
        assert all_comments[0].in_reply_to_id == 800


class TestWebhookPRIssueComment:
    """Tests for issue_comment on PR: user confirms review plan."""

    def test_pr_comment_affirmative_sets_in_progress(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 15, "open", repo="owner/repo")
        set_pr_workflow_status(tmp_path, 15, "waiting_confirmation")
        payload = {
            "action": "created",
            "comment": {"body": "yes", "user": {"login": "user1"}},
            "issue": {"number": 15, "pull_request": {"url": "..."}},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 15)
        assert pr is not None
        assert pr.workflow_status == "in_progress"

    def test_pr_comment_non_affirmative_does_not_change_status(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 16, "open", repo="owner/repo")
        set_pr_workflow_status(tmp_path, 16, "waiting_confirmation")
        payload = {
            "action": "created",
            "comment": {"body": "I have a question", "user": {"login": "user1"}},
            "issue": {"number": 16, "pull_request": {"url": "..."}},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 16)
        assert pr is not None
        assert pr.workflow_status == "waiting_confirmation"

    def test_pr_comment_ignores_when_not_waiting_confirmation(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 17, "open", repo="owner/repo")
        set_pr_workflow_status(tmp_path, 17, "idle")
        payload = {
            "action": "created",
            "comment": {"body": "yes", "user": {"login": "user1"}},
            "issue": {"number": 17, "pull_request": {"url": "..."}},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 17)
        assert pr is not None
        assert pr.workflow_status == "idle"

    def test_pr_comment_ignores_bot(self, tmp_path: Path) -> None:
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 18, "open", repo="owner/repo")
        set_pr_workflow_status(tmp_path, 18, "waiting_confirmation")
        payload = {
            "action": "created",
            "comment": {"body": "yes", "user": {"login": "coddybot"}},
            "issue": {"number": 18, "pull_request": {"url": "..."}},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 18)
        assert pr is not None
        assert pr.workflow_status == "waiting_confirmation"

    def test_pr_comment_ignores_non_pr_issue(self, tmp_path: Path) -> None:
        """issue_comment on a regular issue (not a PR) does not affect PR
        workflow."""
        config = _make_review_config(tmp_path)
        set_pr_status(tmp_path, 19, "open", repo="owner/repo")
        set_pr_workflow_status(tmp_path, 19, "waiting_confirmation")
        payload = {
            "action": "created",
            "comment": {"body": "yes", "user": {"login": "user1"}},
            "issue": {"number": 19},
            "repository": {"full_name": "owner/repo"},
        }
        handle_github_event(config, "issue_comment", payload, repo_dir=tmp_path)
        pr = load_pr(tmp_path, 19)
        assert pr is not None
        assert pr.workflow_status == "waiting_confirmation"


# ---------------------------------------------------------------------------
# Idle timeout tests
# ---------------------------------------------------------------------------


class TestReviewIdleTimeout:
    """Tests for run_review_idle_poll (observer poll for review_received)."""

    def test_idle_timeout_transitions_to_pending_plan(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 50, "open", repo="o/r")
        add_review(tmp_path, 50, review_id=1, author="u", state="commented", body="", created_at=100)
        config = MagicMock()
        run_review_idle_poll(config, tmp_path, idle_timeout=0)
        pr = load_pr(tmp_path, 50)
        assert pr is not None
        assert pr.workflow_status == "pending_plan"

    def test_idle_timeout_does_not_transition_when_not_expired(self, tmp_path: Path) -> None:
        import time

        set_pr_status(tmp_path, 51, "open", repo="o/r")
        now = int(time.time())
        add_review(tmp_path, 51, review_id=1, author="u", state="commented", body="", created_at=now)
        config = MagicMock()
        run_review_idle_poll(config, tmp_path, idle_timeout=9999)
        pr = load_pr(tmp_path, 51)
        assert pr is not None
        assert pr.workflow_status == "review_received"

    def test_idle_timeout_skips_non_review_received(self, tmp_path: Path) -> None:
        set_pr_status(tmp_path, 52, "open", repo="o/r")
        set_pr_workflow_status(tmp_path, 52, "idle")
        config = MagicMock()
        run_review_idle_poll(config, tmp_path, idle_timeout=0)
        pr = load_pr(tmp_path, 52)
        assert pr is not None
        assert pr.workflow_status == "idle"

    def test_idle_timeout_no_prs(self, tmp_path: Path) -> None:
        config = MagicMock()
        run_review_idle_poll(config, tmp_path, idle_timeout=0)


# ---------------------------------------------------------------------------
# Worker review processing tests
# ---------------------------------------------------------------------------


class TestWorkerReviewProcessing:
    """Tests for _process_pr_reviews, _collect_review_comments,
    _build_review_plan in worker/run.py."""

    def test_collect_review_comments_extracts_top_level_only(self) -> None:
        from coddy.worker.run import _collect_review_comments

        pr = PRFile(
            pr_id=1,
            repo="o/r",
            reviews=[
                PRReview(
                    review_id=1,
                    author="u",
                    state="commented",
                    comments=[
                        PRReviewComment(
                            comment_id=10,
                            name="u",
                            content="Fix",
                            path="a.py",
                            line=1,
                            created_at=1,
                            updated_at=1,
                        ),
                        PRReviewComment(
                            comment_id=11,
                            name="bot",
                            content="Done",
                            path="a.py",
                            line=1,
                            created_at=2,
                            updated_at=2,
                            in_reply_to_id=10,
                        ),
                    ],
                    created_at=1,
                ),
            ],
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        items = _collect_review_comments(pr)
        assert len(items) == 1
        assert items[0]["comment_id"] == 10
        assert items[0]["path"] == "a.py"

    def test_collect_review_comments_empty_reviews(self) -> None:
        from coddy.worker.run import _collect_review_comments

        pr = PRFile(
            pr_id=1,
            repo="o/r",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert _collect_review_comments(pr) == []

    def test_build_review_plan_formats_markdown(self) -> None:
        from coddy.worker.run import _build_review_plan

        comments = [
            {
                "comment_id": 1,
                "author": "user1",
                "body": "Fix indentation",
                "path": "src/main.py",
                "line": 10,
                "review_id": 1,
            },
            {
                "comment_id": 2,
                "author": "user2",
                "body": "Missing docstring",
                "path": "utils.py",
                "line": None,
                "review_id": 2,
            },
        ]
        plan = _build_review_plan(comments)
        assert "`src/main.py`" in plan
        assert "line 10" in plan
        assert "@user1" in plan
        assert "Fix indentation" in plan
        assert "`utils.py`" in plan
        assert "file-level" in plan
        assert "@user2" in plan

    def test_process_pr_reviews_pending_plan(self, tmp_path: Path) -> None:
        """Worker generates plan for PR with pending_plan and posts as PR
        comment."""
        from coddy.config import AppConfig, BotConfig, LoggingConfig
        from coddy.worker.run import _process_pr_reviews

        set_pr_status(tmp_path, 60, "open", repo="owner/repo")
        add_review(tmp_path, 60, review_id=1, author="u", state="commented", body="", created_at=100)
        add_review_comment(
            tmp_path,
            60,
            review_id=1,
            comment_id=100,
            author="u",
            content="Fix this",
            path="a.py",
            line=5,
            created_at=200,
        )
        set_pr_workflow_status(tmp_path, 60, "pending_plan")

        config = AppConfig()
        config.bot = BotConfig(
            workspace_path=str(tmp_path),
            repository="owner/repo",
            username="coddybot",
        )
        config.logging = LoggingConfig()

        mock_adapter = MagicMock()
        mock_agent = MagicMock()
        import logging

        log = logging.getLogger("test")
        did_work = _process_pr_reviews(config, tmp_path, mock_adapter, mock_agent, log)
        assert did_work is True
        mock_adapter.create_pr_comment.assert_called_once()
        call_args = mock_adapter.create_pr_comment.call_args[0]
        assert call_args[0] == "owner/repo"
        assert call_args[1] == 60
        assert "Review response plan" in call_args[2]
        assert "Fix this" in call_args[2]

        pr = load_pr(tmp_path, 60)
        assert pr is not None
        assert pr.workflow_status == "waiting_confirmation"

    def test_process_pr_reviews_sets_idle_when_no_comments(self, tmp_path: Path) -> None:
        """When PR has pending_plan but no review comments, set idle."""
        from coddy.config import AppConfig, BotConfig, LoggingConfig
        from coddy.worker.run import _process_pr_reviews

        set_pr_status(tmp_path, 61, "open", repo="owner/repo")
        set_pr_workflow_status(tmp_path, 61, "pending_plan")

        config = AppConfig()
        config.bot = BotConfig(
            workspace_path=str(tmp_path),
            repository="owner/repo",
            username="coddybot",
        )
        config.logging = LoggingConfig()

        import logging

        log = logging.getLogger("test")
        _process_pr_reviews(config, tmp_path, MagicMock(), MagicMock(), log)

        pr = load_pr(tmp_path, 61)
        assert pr is not None
        assert pr.workflow_status == "idle"


# ---------------------------------------------------------------------------
# Review loop tests
# ---------------------------------------------------------------------------


class TestReviewLoop:
    """Tests for run_review_loop_for_pr."""

    def test_review_loop_no_comments_returns_success(self, tmp_path: Path) -> None:
        from coddy.worker.review_loop import run_review_loop_for_pr

        pr_file = PRFile(
            pr_id=70,
            repo="o/r",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        result = run_review_loop_for_pr(
            adapter=MagicMock(),
            agent=MagicMock(),
            pr_file=pr_file,
            repo="o/r",
            repo_dir=tmp_path,
        )
        assert result == "success"

    def test_review_loop_processes_comments_and_posts_replies(self, tmp_path: Path) -> None:
        from coddy.worker.review_loop import run_review_loop_for_pr

        pr_file = PRFile(
            pr_id=71,
            repo="o/r",
            issue_id=10,
            reviews=[
                PRReview(
                    review_id=1,
                    author="u",
                    state="commented",
                    comments=[
                        PRReviewComment(
                            comment_id=200,
                            name="u",
                            content="Fix logic",
                            path="app.py",
                            line=10,
                            created_at=100,
                            updated_at=100,
                        ),
                    ],
                    created_at=100,
                ),
            ],
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_adapter = MagicMock()
        mock_pr = MagicMock()
        mock_pr.head_branch = "71-feature"
        mock_adapter.get_pr.return_value = mock_pr

        mock_agent = MagicMock()
        mock_agent.process_review_item.return_value = "Fixed the logic issue."

        with patch("coddy.worker.review_loop.fetch_and_checkout_branch"):
            with patch("coddy.worker.review_loop.set_commit_author"):
                with patch("coddy.worker.review_loop.commit_all_and_push"):
                    with patch("coddy.worker.review_loop.checkout_branch"):
                        result = run_review_loop_for_pr(
                            adapter=mock_adapter,
                            agent=mock_agent,
                            pr_file=pr_file,
                            repo="o/r",
                            repo_dir=tmp_path,
                            bot_name="Bot",
                            bot_email="bot@test.com",
                            default_branch="main",
                        )

        assert result == "success"
        mock_adapter.reply_to_review_comment.assert_called_once_with("o/r", 71, 200, "Fixed the logic issue.")

    def test_review_loop_skips_reply_comments(self, tmp_path: Path) -> None:
        """Comments with in_reply_to_id are skipped (they are replies, not top-
        level)."""
        from coddy.worker.review_loop import run_review_loop_for_pr

        pr_file = PRFile(
            pr_id=72,
            repo="o/r",
            reviews=[
                PRReview(
                    review_id=1,
                    author="u",
                    state="commented",
                    comments=[
                        PRReviewComment(
                            comment_id=300,
                            name="bot",
                            content="Reply",
                            path="a.py",
                            line=1,
                            created_at=1,
                            updated_at=1,
                            in_reply_to_id=200,
                        ),
                    ],
                    created_at=1,
                ),
            ],
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        result = run_review_loop_for_pr(
            adapter=MagicMock(),
            agent=MagicMock(),
            pr_file=pr_file,
            repo="o/r",
            repo_dir=tmp_path,
        )
        assert result == "success"

    def test_review_loop_returns_failed_on_pr_fetch_error(self, tmp_path: Path) -> None:
        from coddy.worker.review_loop import run_review_loop_for_pr

        pr_file = PRFile(
            pr_id=73,
            repo="o/r",
            reviews=[
                PRReview(
                    review_id=1,
                    author="u",
                    state="commented",
                    comments=[
                        PRReviewComment(
                            comment_id=400,
                            name="u",
                            content="Fix",
                            path="a.py",
                            line=1,
                            created_at=1,
                            updated_at=1,
                        ),
                    ],
                    created_at=1,
                ),
            ],
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_adapter = MagicMock()
        mock_adapter.get_pr.side_effect = Exception("API error")

        result = run_review_loop_for_pr(
            adapter=mock_adapter,
            agent=MagicMock(),
            pr_file=pr_file,
            repo="o/r",
            repo_dir=tmp_path,
        )
        assert result == "failed"

    def test_review_loop_reads_reply_from_file_when_agent_returns_none(self, tmp_path: Path) -> None:
        from coddy.worker.review_loop import run_review_loop_for_pr
        from coddy.worker.task_yaml import review_reply_file_path

        pr_file = PRFile(
            pr_id=74,
            repo="o/r",
            issue_id=10,
            reviews=[
                PRReview(
                    review_id=1,
                    author="u",
                    state="commented",
                    comments=[
                        PRReviewComment(
                            comment_id=500,
                            name="u",
                            content="Fix",
                            path="a.py",
                            line=1,
                            created_at=1,
                            updated_at=1,
                        ),
                    ],
                    created_at=1,
                ),
            ],
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        reply_path = review_reply_file_path(tmp_path, 74, 500)
        reply_path.parent.mkdir(parents=True, exist_ok=True)
        reply_path.write_text("body: File-based reply\n", encoding="utf-8")

        mock_adapter = MagicMock()
        mock_pr = MagicMock()
        mock_pr.head_branch = "74-fix"
        mock_adapter.get_pr.return_value = mock_pr

        mock_agent = MagicMock()
        mock_agent.process_review_item.return_value = None

        with patch("coddy.worker.review_loop.fetch_and_checkout_branch"):
            with patch("coddy.worker.review_loop.set_commit_author"):
                with patch("coddy.worker.review_loop.commit_all_and_push"):
                    with patch("coddy.worker.review_loop.checkout_branch"):
                        result = run_review_loop_for_pr(
                            adapter=mock_adapter,
                            agent=mock_agent,
                            pr_file=pr_file,
                            repo="o/r",
                            repo_dir=tmp_path,
                            bot_name="Bot",
                            bot_email="bot@test.com",
                            default_branch="main",
                        )

        assert result == "success"
        mock_adapter.reply_to_review_comment.assert_called_once_with("o/r", 74, 500, "File-based reply")
