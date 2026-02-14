"""Comment on an issue or PR."""

from datetime import datetime

from pydantic import BaseModel


class Comment(BaseModel):
    """Comment on an issue or PR."""

    id: int
    body: str
    author: str
    created_at: datetime
    updated_at: datetime | None = None
