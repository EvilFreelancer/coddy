"""PR record as stored in .coddy/prs/{pr_number}.yaml."""

from typing import Optional

from pydantic import BaseModel, Field


class PRFile(BaseModel):
    """PR record as stored in .coddy/prs/{pr_number}.yaml."""

    pr_id: int = Field(..., description="Pull request ID")
    repo: str = Field(..., description="Repository full_name, e.g. owner/repo")
    status: str = Field(
        default="open",
        description="PR state: open, merged, closed",
    )
    issue_id: Optional[int] = Field(default=None, description="Linked issue ID if any")
    created_at: str = Field(..., description="ISO timestamp when record was created")
    updated_at: str = Field(..., description="ISO timestamp of last status update")

    model_config = {"extra": "forbid", "populate_by_name": True}

    def to_markdown(self) -> str:
        """Render PR record as markdown."""
        lines = [
            f"# PR #{self.pr_id}",
            "",
            f"**Repo:** `{self.repo}`",
            f"**Status:** {self.status}",
            "",
        ]
        if self.issue_id is not None:
            lines.append(f"**Linked issue:** #{self.issue_id}")
            lines.append("")
        lines.extend(
            [
                f"**Created:** {self.created_at}",
                f"**Updated:** {self.updated_at}",
            ]
        )
        return "\n".join(lines).strip() + "\n"
