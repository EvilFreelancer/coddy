"""Abstract base class for Git platform adapters."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from coddy.models import PR, Comment, Issue, ReviewComment


class GitPlatformError(Exception):
    """Raised when a Git platform API call fails."""

    pass


class GitPlatformAdapter(ABC):
    """Abstract interface for Git hosting platforms (GitHub, GitLab,
    Bitbucket)."""

    @abstractmethod
    def get_issue(self, repo: str, issue_number: int) -> Issue:
        """Fetch a single issue by number.

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
        """Return list of assignee logins for the issue.

        Default: fetch issue and derive from it if needed.
        """
        raise NotImplementedError

    def list_issues_assigned_to(self, repo: str, assignee_username: str) -> List[Issue]:
        """List open issues assigned to the given user."""
        raise NotImplementedError

    def list_open_issues(self, repo: str) -> List[Issue]:
        """List all open issues in the repository (excludes pull requests).

        Args:
            repo: Repository in format owner/repo

        Returns:
            List of Issue instances, open only, no PRs
        """
        raise NotImplementedError

    def set_issue_labels(self, repo: str, issue_number: int, labels: List[str]) -> None:
        """Set labels on an issue (replaces existing labels).

        Args:
            repo: Repository in format owner/repo
            issue_number: Issue number
            labels: New list of label names
        """
        raise NotImplementedError

    def create_comment(self, repo: str, issue_number: int, body: str) -> Comment:
        """Post a comment on an issue.

        Args:
            repo: Repository in format owner/repo
            issue_number: Issue number
            body: Comment body (markdown supported)

        Returns:
            Created Comment instance
        """
        raise NotImplementedError

    def create_branch(self, repo: str, branch_name: str) -> None:
        """Create a branch from the default branch HEAD (e.g. main).

        Args:
            repo: Repository in format owner/repo
            branch_name: New branch name (e.g. 1-implement-get-issue-assignees)
        """
        raise NotImplementedError

    def get_default_branch(self, repo: str) -> str:
        """Return default branch name (e.g. main)."""
        raise NotImplementedError

    def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> PR:
        """Create a pull request from head branch to base branch.

        Args:
            repo: Repository in format owner/repo
            title: PR title
            body: PR description (markdown)
            head: Head branch name
            base: Base branch name (e.g. main)

        Returns:
            Created PR instance
        """
        raise NotImplementedError

    def get_issue_comments(self, repo: str, issue_number: int, since: datetime | None = None) -> List[Comment]:
        """Fetch comments on an issue, optionally since a given datetime."""
        raise NotImplementedError

    def get_pr(self, repo: str, pr_number: int) -> PR:
        """Fetch a pull request by number.

        Args:
            repo: Repository in format owner/repo
            pr_number: Pull request number

        Returns:
            PR instance

        Raises:
            GitPlatformError: If the API call fails or PR not found
        """
        raise NotImplementedError

    def list_pr_review_comments(self, repo: str, pr_number: int, since: datetime | None = None) -> List[ReviewComment]:
        """List review comments on a pull request (line-level comments).

        Optionally only comments updated after `since`.

        Args:
            repo: Repository in format owner/repo
            pr_number: Pull request number
            since: Optional datetime to fetch only comments updated after

        Returns:
            List of ReviewComment, typically ordered by path and line
        """
        raise NotImplementedError

    def reply_to_review_comment(self, repo: str, pr_number: int, in_reply_to_comment_id: int, body: str) -> Comment:
        """Post a reply to a review comment (creates a thread reply).

        Args:
            repo: Repository in format owner/repo
            pr_number: Pull request number
            in_reply_to_comment_id: ID of the comment to reply to
            body: Reply body (markdown supported)

        Returns:
            Created Comment instance
        """
        raise NotImplementedError
