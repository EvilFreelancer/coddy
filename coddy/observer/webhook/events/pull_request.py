"""Event schemas for GitHub pull_request, pull_request_review,
pull_request_review_comment, issue_comment (on PR).

Bot processes:
- comments (issue_comment when issue is a PR; pull_request_review_comment for line comments)
- review (pull_request_review submitted - includes approvals when state=approved)
- closed
- merged
"""

from typing import Literal

from pydantic import BaseModel

from coddy.observer.models import ReviewComment


class PRClosed(BaseModel):
    """PR closed without merge (pull_request webhook, action=closed,
    merged=false)."""

    repo: str
    pr_number: int


class PRMerged(BaseModel):
    """PR merged (pull_request webhook, action=closed, merged=true)."""

    repo: str
    pr_number: int


class PRCommentCreated(BaseModel):
    """New comment on PR (issue_comment on PR, action=created)."""

    repo: str
    pr_number: int
    comment_id: int
    body: str = ""
    author: str = ""


class PRReviewSubmitted(BaseModel):
    """Review submitted (pull_request_review webhook, action=submitted).

    Covers approval and changes_requested.
    """

    repo: str
    pr_number: int
    review_id: int
    body: str = ""
    author: str = ""
    state: Literal["approved", "changes_requested", "commented"] = "commented"


class PRReviewCommentCreated(BaseModel):
    """Line or file review comment created (pull_request_review_comment
    webhook, action=created)."""

    repo: str
    pr_number: int
    comment: ReviewComment
