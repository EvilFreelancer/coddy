"""PR review and review comment schemas for .coddy/pull_requests/."""

from typing import List

from pydantic import BaseModel, Field


class PRReviewComment(BaseModel):
    """Single comment within a PR review (line-level or file-level)."""

    comment_id: int | None = Field(default=None, description="Platform comment id")
    name: str = Field(..., description="Author login, e.g. @username")
    content: str = Field(..., description="Comment body")
    path: str = Field(default="", description="File path relative to repo root")
    line: int | None = Field(default=None, description="Line number in the file")
    created_at: int = Field(..., description="Unix timestamp when comment was created")
    updated_at: int = Field(..., description="Unix timestamp when comment was last updated")
    in_reply_to_id: int | None = Field(default=None, description="Parent comment id (for threaded replies)")


class PRReview(BaseModel):
    """A single review submitted on a PR."""

    review_id: int | None = Field(default=None, description="Platform review id")
    author: str = Field(..., description="Reviewer login")
    state: str = Field(default="commented", description="Review state: approved, changes_requested, commented")
    body: str = Field(default="", description="Top-level review body")
    comments: List[PRReviewComment] = Field(default_factory=list, description="Line-level review comments")
    created_at: int = Field(..., description="Unix timestamp when review was submitted")
