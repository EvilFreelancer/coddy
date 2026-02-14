"""Webhook event schemas for GitHub payloads.

Processed events:

Issues (bot only reacts to issues assigned to it):
- assigned: user(s) assigned to issue
- comment created/edited: comments in issue; edit of description, title, or comments
- closed

Pull requests:
- comments (issue_comment on PR)
- review (pull_request_review submitted)
- approvals (review state approved)
- closed
- merged
"""

from coddy.observer.webhook.events.issues import (
    IssueAssigned,
    IssueClosed,
    IssueCommentCreated,
    IssueCommentEdited,
    IssueEdited,
)
from coddy.observer.webhook.events.pull_request import (
    PRClosed,
    PRCommentCreated,
    PRMerged,
    PRReviewCommentCreated,
    PRReviewSubmitted,
)

__all__ = [
    "IssueAssigned",
    "IssueClosed",
    "IssueCommentCreated",
    "IssueCommentEdited",
    "IssueEdited",
    "PRClosed",
    "PRCommentCreated",
    "PRMerged",
    "PRReviewCommentCreated",
    "PRReviewSubmitted",
]
