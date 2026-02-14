"""Pydantic models for issue YAML files in .coddy/issues/.

One file per issue: .coddy/issues/{issue_number}.yaml
Stores meta, title, description, and messages (user comments + bot replies).
Status drives the flow: pending_plan -> waiting_confirmation -> queued (worker picks).
"""

from pydantic import BaseModel, Field


class IssueMessage(BaseModel):
    """Single message in the issue thread (user comment or bot reply)."""

    name: str = Field(..., description="Author login, e.g. @username or @botname")
    content: str = Field(..., description="Message body")
    timestamp: int = Field(..., description="Unix timestamp")


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
    messages: list[IssueMessage] = Field(default_factory=list, description="Thread: user comments and bot replies")

    # Optional meta for scheduler and worker
    repo: str | None = Field(default=None, description="Repository full_name, e.g. owner/repo")
    issue_number: int | None = Field(default=None, description="Issue number (also in filename)")
    assigned_at: str | None = Field(default=None, description="When bot was assigned (ISO), for idle_minutes")

    model_config = {"extra": "forbid"}
