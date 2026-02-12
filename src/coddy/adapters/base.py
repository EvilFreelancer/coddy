"""
Abstract base class for Git platform adapters.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from coddy.models import Comment, Issue


class GitPlatformError(Exception):
    """Raised when a Git platform API call fails."""

    pass


class GitPlatformAdapter(ABC):
    """Abstract interface for Git hosting platforms (GitHub, GitLab, Bitbucket)."""

    @abstractmethod
    def get_issue(self, repo: str, issue_number: int) -> Issue:
        """
        Fetch a single issue by number.

        Args:
            repo: Repository in format owner/repo
            issue_number: Issue number

        Returns:
            Issue instance

        Raises:
            GitPlatformError: If the API call fails or issue not found
        """
        pass

    def get_issue_assignees(self, repo: str, issue_number: int) -> List[str]:
        """Return list of assignee logins for the issue. Default: fetch issue and derive from it if needed."""
        raise NotImplementedError

    def list_issues_assigned_to(self, repo: str, assignee_username: str) -> List[Issue]:
        """List open issues assigned to the given user."""
        raise NotImplementedError

    def get_issue_comments(self, repo: str, issue_number: int, since: Optional[datetime] = None) -> List[Comment]:
        """Fetch comments on an issue, optionally since a given datetime."""
        raise NotImplementedError
