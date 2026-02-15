"""Full issue record as stored in .coddy/issues/{issue_number}.yaml."""

from datetime import datetime, timezone
from typing import Annotated, List

from pydantic import BaseModel, BeforeValidator, Field

from coddy.services.store.schemas.issue_comment import IssueComment


def _ensure_unix_ts(value: int | str | None) -> int | None:
    """Coerce ISO date string or int to Unix timestamp (int). Accepts None for optional fields."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


class IssueFile(BaseModel):
    """Full issue record as stored in .coddy/issues/{issue_number}.yaml."""

    repo: str | None = Field(default=None, description="Repository full_name, e.g. owner/repo")
    issue_id: int | None = Field(default=None, description="Issue ID")

    author: str = Field(..., description="Issue author login")
    assigned_at: Annotated[int | None, BeforeValidator(_ensure_unix_ts)] = Field(
        default=None,
        description="When issue was assigned (Unix timestamp). Omitted when not assigned.",
    )
    assigned_to: str | None = Field(
        default=None,
        description="Login of the assignee. Omitted when not assigned.",
    )

    created_at: Annotated[int, BeforeValidator(_ensure_unix_ts)] = Field(
        ...,
        description="Unix timestamp when issue was created",
    )
    updated_at: Annotated[int, BeforeValidator(_ensure_unix_ts)] = Field(
        ...,
        description="Unix timestamp of last update",
    )

    status: str = Field(
        default="pending_plan",
        description="Current state: pending_plan, waiting_confirmation, queued, in_progress, done, failed, closed",
    )
    title: str = Field(default="", description="Issue title")
    description: str = Field(default="", description="Issue description")
    comments: List[IssueComment] = Field(
        default_factory=list,
        description="Thread: user comments and bot replies",
    )

    model_config = {"extra": "forbid", "populate_by_name": True}

    def to_markdown(self) -> str:
        """Render issue as markdown (title, description, comments thread)."""
        lines = []
        if self.issue_id is not None:
            lines.append(f"# Issue {self.issue_id}")
            lines.append("")
        lines.append("## Title")
        lines.append(self.title or "(no title)")
        lines.append("")
        lines.append("## Description")
        lines.append(self.description or "(no description)")
        lines.append("")
        if self.comments:
            lines.append("## Comments")
            lines.append("")
            for msg in self.comments:
                lines.append(f"### {msg.name}")
                lines.append("")
                lines.append(msg.content)
                lines.append("")
        return "\n".join(lines).strip() + "\n"
