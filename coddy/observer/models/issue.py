"""Git hosting platform issue model."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class Issue(BaseModel):
    """Git hosting platform issue."""

    number: int
    title: str
    body: str = ""
    author: str
    labels: List[str] = Field(default_factory=list)
    state: str
    created_at: datetime
    updated_at: datetime
