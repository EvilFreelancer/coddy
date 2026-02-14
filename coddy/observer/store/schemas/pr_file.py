"""PR record as stored in .coddy/prs/{pr_number}.yaml."""

from typing import Optional

from pydantic import BaseModel, Field


class PRFile(BaseModel):
    """PR record as stored in .coddy/prs/{pr_number}.yaml."""

    pr_number: int = Field(..., description="Pull request number")
    repo: str = Field(..., description="Repository full_name, e.g. owner/repo")
    status: str = Field(
        default="open",
        description="PR state: open, merged, closed",
    )
    issue_number: Optional[int] = Field(default=None, description="Linked issue number if any")
    created_at: str = Field(..., description="ISO timestamp when record was created")
    updated_at: str = Field(..., description="ISO timestamp of last status update")

    model_config = {"extra": "forbid"}
