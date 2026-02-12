"""
Unit tests for GitHub adapter (mocked API).
"""

from unittest.mock import Mock, patch

import pytest

from coddy.adapters.base import GitPlatformError
from coddy.adapters.github import GitHubAdapter
from coddy.models import Issue


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
