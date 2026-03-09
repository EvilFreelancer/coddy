"""PR record as stored in .coddy/pull_requests/{status}/{pr_number}.yaml.

Pending request: .coddy/pull_requests/pending/{issue_id}.yaml (worker writes,
observer creates PR and moves to open/{pr_id}.yaml).
"""

from typing import List

from pydantic import BaseModel, Field

from coddy.services.store.schemas.pr_review import PRReview


class PendingPRRequest(BaseModel):
    """PR creation request written by worker; observer creates the PR via API.

    Stored in .coddy/pull_requests/pending/{issue_id}.yaml.
    """

    issue_id: int = Field(..., description="Linked issue number")
    repo: str = Field(..., description="Repository full_name, e.g. owner/repo")
    title: str = Field(..., description="PR title")
    body: str = Field(..., description="PR body (markdown)")
    head: str = Field(..., description="Head branch name")
    base: str = Field(..., description="Base branch name")
    created_at: str = Field(..., description="ISO timestamp when request was written")

    model_config = {"extra": "forbid", "populate_by_name": True}


PR_WORKFLOW_STATUSES = (
    "idle",
    "review_received",
    "pending_plan",
    "waiting_confirmation",
    "in_progress",
)


class PRFile(BaseModel):
    """PR record as stored in
    .coddy/pull_requests/{status}/{pr_number}.yaml."""

    pr_id: int = Field(..., description="Pull request ID")
    repo: str = Field(..., description="Repository full_name, e.g. owner/repo")
    status: str = Field(
        default="open",
        description="PR state: open, draft, merged, or rejected (closed without merge). Determines folder.",
    )
    workflow_status: str = Field(
        default="idle",
        description="Review workflow: idle, review_received, pending_plan, waiting_confirmation, in_progress",
    )
    issue_id: int | None = Field(default=None, description="Linked issue ID if any")
    reviews: List[PRReview] = Field(default_factory=list, description="Submitted reviews with line-level comments")
    last_review_ts: int | None = Field(
        default=None,
        description="Unix timestamp of last review/comment received (for idle timeout)",
    )
    created_at: str = Field(..., description="ISO timestamp when record was created")
    updated_at: str = Field(..., description="ISO timestamp of last status update")

    model_config = {"extra": "ignore", "populate_by_name": True}

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
