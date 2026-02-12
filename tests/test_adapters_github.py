"""Unit tests for GitHub adapter (mocked API)."""

from unittest.mock import Mock, patch

import pytest

from coddy.adapters.base import GitPlatformError
from coddy.adapters.github import GitHubAdapter
from coddy.models import PR, Comment, Issue, ReviewComment


@pytest.fixture
def adapter() -> GitHubAdapter:
    return GitHubAdapter(token="test-token", api_url="https://api.github.com")


def test_get_issue_success(adapter: GitHubAdapter) -> None:
    """get_issue returns Issue when API returns 200."""
    response_data = {
        "number": 1,
        "title": "Test issue",
        "body": "Body text",
        "state": "open",
        "labels": [{"name": "bug"}, {"name": "enhancement"}],
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-16T12:00:00Z",
        "user": {"login": "octocat"},
    }
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response_data

    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        issue = adapter.get_issue("owner/repo", 1)

    assert isinstance(issue, Issue)
    assert issue.number == 1
    assert issue.title == "Test issue"
    assert issue.body == "Body text"
    assert issue.author == "octocat"
    assert issue.labels == ["bug", "enhancement"]
    assert issue.state == "open"
    req.assert_called_once()
    call_args = req.call_args
    assert call_args[0][0] == "GET"
    assert "/repos/owner/repo/issues/1" in call_args[0][1]


def test_get_issue_404_raises(adapter: GitHubAdapter) -> None:
    """get_issue raises GitPlatformError when issue not found."""
    mock_resp = Mock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"

    with patch.object(adapter._session, "request", return_value=mock_resp):
        with pytest.raises(GitPlatformError) as exc_info:
            adapter.get_issue("owner/repo", 999)
    assert "404" in str(exc_info.value) or "Not found" in str(exc_info.value)


def test_get_issue_api_error_raises(adapter: GitHubAdapter) -> None:
    """get_issue raises GitPlatformError on API error."""
    mock_resp = Mock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_resp.json.return_value = {"message": "API rate limit exceeded"}

    with patch.object(adapter._session, "request", return_value=mock_resp):
        with pytest.raises(GitPlatformError) as exc_info:
            adapter.get_issue("owner/repo", 1)
    assert "403" in str(exc_info.value) or "rate limit" in str(exc_info.value).lower()


def test_list_open_issues_returns_issues_only(adapter: GitHubAdapter) -> None:
    """list_open_issues returns only issues, excludes PRs."""
    response_data = [
        {
            "number": 1,
            "title": "An issue",
            "body": "Body",
            "state": "open",
            "labels": [],
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-16T12:00:00Z",
            "user": {"login": "octocat"},
        },
        {
            "number": 2,
            "title": "A PR",
            "state": "open",
            "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/2"},
            "labels": [],
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-16T12:00:00Z",
            "user": {"login": "octocat"},
        },
    ]
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response_data

    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        issues = adapter.list_open_issues("owner/repo")

    assert len(issues) == 1
    assert issues[0].number == 1
    assert issues[0].title == "An issue"
    call_args = req.call_args
    assert call_args[0][0] == "GET"
    assert "/repos/owner/repo/issues" in call_args[0][1]
    assert call_args[1].get("params", {}).get("state") == "open"


def test_list_open_issues_empty(adapter: GitHubAdapter) -> None:
    """list_open_issues returns empty list when no issues."""
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch.object(adapter._session, "request", return_value=mock_resp):
        issues = adapter.list_open_issues("owner/repo")
    assert issues == []


def test_set_issue_labels_success(adapter: GitHubAdapter) -> None:
    """set_issue_labels sends PUT with labels."""
    mock_resp = Mock()
    mock_resp.status_code = 200

    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        adapter.set_issue_labels("owner/repo", 1, ["in progress"])

    call_args = req.call_args
    assert call_args[0][0] == "PUT"
    assert "/repos/owner/repo/issues/1/labels" in call_args[0][1]
    assert call_args[1].get("json") == {"labels": ["in progress"]}


def test_create_comment_success(adapter: GitHubAdapter) -> None:
    """create_comment returns Comment when API returns 201."""
    response_data = {
        "id": 42,
        "body": "Hello",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
        "user": {"login": "bot"},
    }
    mock_resp = Mock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = response_data

    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        comment = adapter.create_comment("owner/repo", 1, "Hello")

    assert isinstance(comment, Comment)
    assert comment.id == 42
    assert comment.body == "Hello"
    assert comment.author == "bot"
    assert req.call_args[1].get("json") == {"body": "Hello"}


def test_get_issue_comments_success(adapter: GitHubAdapter) -> None:
    """get_issue_comments returns list of Comment."""
    response_data = [
        {
            "id": 1,
            "body": "First",
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
            "user": {"login": "user1"},
        },
    ]
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response_data

    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        comments = adapter.get_issue_comments("owner/repo", 1)

    assert len(comments) == 1
    assert comments[0].id == 1
    assert comments[0].body == "First"
    assert comments[0].author == "user1"
    assert "/repos/owner/repo/issues/1/comments" in req.call_args[0][1]


def test_create_branch_success(adapter: GitHubAdapter) -> None:
    """create_branch GETs repo and default ref then POSTs new ref."""
    repo_data = {"default_branch": "main"}
    ref_data = {"object": {"sha": "abc123"}}

    def side_effect(method, url, **kwargs):
        resp = Mock()
        resp.status_code = 200
        if method == "GET" and "git/ref/heads" in url:
            resp.json.return_value = ref_data
        elif method == "POST" and "git/refs" in url:
            resp.json.return_value = {}
        else:
            resp.json.return_value = repo_data
        return resp

    with patch.object(adapter, "_request", side_effect=side_effect) as req:
        adapter.create_branch("owner/repo", "1-feature")

    assert req.call_count == 3
    assert req.call_args_list[0][0][1] == "/repos/owner/repo"
    assert "ref/heads/main" in req.call_args_list[1][0][1]
    assert req.call_args_list[2][0][0] == "POST"
    assert req.call_args_list[2][1].get("json") == {"ref": "refs/heads/1-feature", "sha": "abc123"}


def test_create_branch_with_base_branch_skips_repo_api(adapter: GitHubAdapter) -> None:
    """create_branch with base_branch uses it and does not call get repo
    API."""
    ref_data = {"object": {"sha": "def456"}}

    def side_effect(method, url, **kwargs):
        resp = Mock()
        resp.status_code = 200
        if method == "GET" and "git/ref/heads/main" in url:
            resp.json.return_value = ref_data
        elif method == "POST" and "git/refs" in url:
            resp.json.return_value = {}
        else:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return resp

    with patch.object(adapter, "_request", side_effect=side_effect) as req:
        adapter.create_branch("owner/repo", "2-feature", base_branch="main")

    assert req.call_count == 2
    assert "ref/heads/main" in req.call_args_list[0][0][1]
    assert req.call_args_list[1][1].get("json") == {"ref": "refs/heads/2-feature", "sha": "def456"}


def test_get_default_branch(adapter: GitHubAdapter) -> None:
    """get_default_branch returns default_branch from repo API."""
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"default_branch": "main"}
    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        branch = adapter.get_default_branch("owner/repo")
    assert branch == "main"
    assert "/repos/owner/repo" in req.call_args[0][1]


def test_create_pr_success(adapter: GitHubAdapter) -> None:
    """create_pr returns PR when API returns 201."""
    response_data = {
        "number": 2,
        "title": "Implement feature",
        "body": "Done.",
        "state": "open",
        "head": {"ref": "1-feature"},
        "base": {"ref": "main"},
        "html_url": "https://github.com/owner/repo/pull/2",
    }
    mock_resp = Mock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = response_data
    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        pr = adapter.create_pr("owner/repo", "Implement feature", "Done.", "1-feature", "main")
    assert isinstance(pr, PR)
    assert pr.number == 2
    assert pr.title == "Implement feature"
    assert pr.head_branch == "1-feature"
    assert pr.base_branch == "main"
    assert req.call_args[1].get("json") == {
        "title": "Implement feature",
        "head": "1-feature",
        "base": "main",
        "body": "Done.",
    }


def test_get_pr_success(adapter: GitHubAdapter) -> None:
    """get_pr returns PR when API returns 200."""
    response_data = {
        "number": 3,
        "title": "Fix bug",
        "body": "Description",
        "state": "open",
        "head": {"ref": "2-fix-bug"},
        "base": {"ref": "main"},
        "html_url": "https://github.com/owner/repo/pull/3",
    }
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response_data
    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        pr = adapter.get_pr("owner/repo", 3)
    assert isinstance(pr, PR)
    assert pr.number == 3
    assert pr.title == "Fix bug"
    assert pr.head_branch == "2-fix-bug"
    assert pr.base_branch == "main"
    assert "/repos/owner/repo/pulls/3" in req.call_args[0][1]


def test_list_pr_review_comments_success(adapter: GitHubAdapter) -> None:
    """list_pr_review_comments returns list of ReviewComment."""
    response_data = [
        {
            "id": 100,
            "body": "Use a constant here",
            "path": "src/foo.py",
            "line": 42,
            "side": "RIGHT",
            "user": {"login": "reviewer"},
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
        },
    ]
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response_data
    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        comments = adapter.list_pr_review_comments("owner/repo", 3)
    assert len(comments) == 1
    assert isinstance(comments[0], ReviewComment)
    assert comments[0].id == 100
    assert comments[0].body == "Use a constant here"
    assert comments[0].path == "src/foo.py"
    assert comments[0].line == 42
    assert comments[0].author == "reviewer"
    assert "/repos/owner/repo/pulls/3/comments" in req.call_args[0][1]


def test_reply_to_review_comment_success(adapter: GitHubAdapter) -> None:
    """reply_to_review_comment sends POST with body and in_reply_to."""
    response_data = {
        "id": 101,
        "body": "Done.",
        "created_at": "2024-01-15T11:00:00Z",
        "updated_at": "2024-01-15T11:00:00Z",
        "user": {"login": "bot"},
    }
    mock_resp = Mock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = response_data
    with patch.object(adapter._session, "request", return_value=mock_resp) as req:
        comment = adapter.reply_to_review_comment("owner/repo", 3, 100, "Done.")
    assert isinstance(comment, Comment)
    assert comment.id == 101
    assert comment.body == "Done."
    assert comment.author == "bot"
    assert req.call_args[1].get("json") == {"body": "Done.", "in_reply_to": 100}
