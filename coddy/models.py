"""Data models for issues, pull requests, comments, and code changes."""

from datetime import datetime
from typing import List


class Issue:
    """Git hosting platform issue."""

    def __init__(
        self,
        number: int,
        title: str,
        body: str,
        author: str,
        labels: List[str],
        state: str,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        self.number = number
        self.title = title
        self.body = body or ""
        self.author = author
        self.labels = labels or []
        self.state = state
        self.created_at = created_at
        self.updated_at = updated_at


class Comment:
    """Comment on an issue or PR."""

    def __init__(
        self,
        id: int,
        body: str,
        author: str,
        created_at: datetime,
        updated_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.body = body
        self.author = author
        self.created_at = created_at
        self.updated_at = updated_at or created_at


class PR:
    """Pull request (or merge request)."""

    def __init__(
        self,
        number: int,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        state: str,
        html_url: str | None = None,
    ) -> None:
        self.number = number
        self.title = title
        self.body = body or ""
        self.head_branch = head_branch
        self.base_branch = base_branch
        self.state = state
        self.html_url = html_url


class ReviewComment:
    """Line-level (or file-level) comment on a pull request review.

    Identifies where the comment was made (path, line) and the user's
    message.
    """

    def __init__(
        self,
        id: int,
        body: str,
        author: str,
        path: str,
        line: int | None,
        side: str,
        created_at: datetime,
        updated_at: datetime | None = None,
        in_reply_to_id: int | None = None,
    ) -> None:
        self.id = id
        self.body = body
        self.author = author
        self.path = path
        self.line = line
        self.side = side
        self.created_at = created_at
        self.updated_at = updated_at or created_at
        self.in_reply_to_id = in_reply_to_id
