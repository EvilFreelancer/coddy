"""Single comment in the issue thread (user comment or bot reply)."""

from pydantic import BaseModel, Field


class IssueComment(BaseModel):
    """Single comment in the issue thread (user comment or bot reply)."""

    name: str = Field(..., description="Author login, e.g. @username or @botname")
    content: str = Field(..., description="Comment body")
    created_at: int = Field(..., description="Unix timestamp when comment was created")
    updated_at: int = Field(..., description="Unix timestamp when comment was last updated")
