"""Full issue record as stored in .coddy/issues/{issue_number}.yaml."""

from typing import List, Optional

from pydantic import BaseModel, Field

from coddy.observer.store.schemas.issue_comment import IssueComment


class IssueFile(BaseModel):
    """Full issue record as stored in .coddy/issues/{issue_number}.yaml."""

    author: str = Field(..., description="Issue author login")
    created_at: str = Field(..., description="ISO or unix timestamp when issue was created")
    updated_at: str = Field(..., description="ISO or unix timestamp of last update")
    status: str = Field(
        default="pending_plan",
        description="Current state: pending_plan, waiting_confirmation, queued, in_progress, done, failed, closed",
    )
    title: str = Field(default="", description="Issue title")
    description: str = Field(default="", description="Issue body (multiline)")
    comments: List[IssueComment] = Field(
        default_factory=list,
        description="Thread: user comments and bot replies",
    )

    repo: Optional[str] = Field(default=None, description="Repository full_name, e.g. owner/repo")
    issue_number: Optional[int] = Field(default=None, description="Issue number (also in filename)")
    assigned_at: Optional[str] = Field(
        default=None,
        description="When bot was assigned (ISO), for idle_minutes",
    )

    model_config = {"extra": "forbid"}
