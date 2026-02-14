"""Pull request (or merge request) model."""

from pydantic import BaseModel


class PR(BaseModel):
    """Pull request (or merge request)."""

    number: int
    title: str
    body: str = ""
    head_branch: str
    base_branch: str
    state: str
    html_url: str | None = None
