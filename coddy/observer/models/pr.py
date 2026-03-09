"""Pull request (or merge request) model."""

from datetime import datetime

from pydantic import BaseModel, Field


class PR(BaseModel):
    """Pull request (or merge request)."""

    number: int
    title: str
    body: str = ""
    head_branch: str
    base_branch: str
    state: str
    html_url: str | None = None
    merged_at: datetime | None = Field(default=None, description="When PR was merged; None if not merged")
    draft: bool = Field(default=False, description="Whether the PR is in draft mode")
