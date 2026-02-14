"""Abstract base for Git platform adapters."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from coddy.observer.models import PR, Comment, Issue, ReviewComment


class GitPlatformError(Exception):
    """Raised when a Git platform API call fails."""

    pass


class GitPlatformAdapter(ABC):
    """Abstract interface for Git hosting platforms (GitHub, GitLab, Bitbucket)."""

    @abstractmethod
    def get_issue(self, repo: str, issue_number: int) -> Issue:
        """Fetch issue by number."""
        ...

    @abstractmethod
    def get_issue_comments(
        self,
        repo: str,
        issue_number: int,
        since: datetime | None = None,
    ) -> List[Comment]:
        """Fetch comments on an issue."""
        ...

    @abstractmethod
    def create_comment(self, repo: str, issue_number: int, body: str) -> Comment:
        """Post a comment on an issue."""
        ...

    @abstractmethod
    def set_issue_labels(self, repo: str, issue_number: int, labels: List[str]) -> None:
        """Set labels on an issue."""
        ...

    @abstractmethod
    def create_branch(
        self,
        repo: str,
        branch_name: str,
        base_branch: str | None = None,
    ) -> None:
        """Create a branch (from default or base_branch)."""
        ...

    @abstractmethod
    def get_default_branch(self, repo: str) -> str:
        """Return default branch name (e.g. main)."""
        ...

    @abstractmethod
    def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PR:
        """Create a pull request."""
        ...

    def get_pr(self, repo: str, pr_number: int) -> PR:
        """Fetch PR by number. Override if needed."""
        raise NotImplementedError("get_pr")

    def list_open_issues(self, repo: str) -> List[Issue]:
        """List open issues (exclude PRs). Override if needed."""
        return []

    def list_pr_review_comments(self, repo: str, pr_number: int) -> List[ReviewComment]:
        """List review comments on a PR. Override if needed."""
        return []

    def reply_to_review_comment(
        self,
        repo: str,
        pr_number: int,
        comment_id: int,
        body: str,
    ) -> Comment:
        """Reply to a review comment. Override if needed."""
        raise NotImplementedError("reply_to_review_comment")
