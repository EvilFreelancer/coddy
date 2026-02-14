"""Event schemas for GitHub 'issues' and 'issue_comment' webhooks.

Bot processes only issues assigned to it. Supported:
- assigned: create/update issue in .coddy/issues/
- comment created/edited: e.g. confirmation reply, new input
- issue edited: title, body, or comments changed
- closed: set issue status to closed
"""

from typing import List

from pydantic import BaseModel, Field


class IssueAssigned(BaseModel):
    """Issue assigned event (issues webhook, action=assigned)."""

    repo: str = Field(description="Repository full_name (owner/repo)")
    issue_number: int
    title: str = ""
    body: str = ""
    author: str = Field(description="Issue author login")
    assignee_logins: List[str] = Field(default_factory=list, description="Current assignee logins (includes bot)")


class IssueClosed(BaseModel):
    """Issue closed event (issues webhook, action=closed)."""

    repo: str
    issue_number: int


class IssueEdited(BaseModel):
    """Issue title/body edited (issues webhook, action=edited)."""

    repo: str
    issue_number: int
    title: str = ""
    body: str = ""


class IssueCommentCreated(BaseModel):
    """New comment on issue (issue_comment webhook, action=created)."""

    repo: str
    issue_number: int
    comment_id: int
    body: str = ""
    author: str = ""


class IssueCommentEdited(BaseModel):
    """Comment on issue edited (issue_comment webhook, action=edited)."""

    repo: str
    issue_number: int
    comment_id: int
    body: str = ""
    author: str = ""
