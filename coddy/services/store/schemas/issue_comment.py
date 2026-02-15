"""Single comment in the issue thread (user comment or bot reply)."""

from pydantic import BaseModel, Field


class IssueComment(BaseModel):
    """Single comment in the issue thread (user comment or bot reply)."""

    comment_id: int | None = Field(default=None, description="Platform comment id (e.g. GitHub), for lookup and updates")
    name: str = Field(..., description="Author login, e.g. @username or @botname")
    content: str = Field(..., description="Comment body")
    created_at: int = Field(..., description="Unix timestamp when comment was created")
    updated_at: int = Field(..., description="Unix timestamp when comment was last updated")
    deleted_at: int | None = Field(
        default=None,
        description="Unix timestamp when comment was deleted (soft delete). Omitted when not deleted.",
    )
