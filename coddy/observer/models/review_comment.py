"""Line-level or file-level comment on a pull request review."""

from datetime import datetime

from pydantic import BaseModel


class ReviewComment(BaseModel):
    """Line-level (or file-level) comment on a pull request review."""

    id: int
    body: str
    author: str
    path: str
    line: int | None
    side: str
    created_at: datetime
    updated_at: datetime | None = None
    in_reply_to_id: int | None = None
