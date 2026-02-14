"""Root storage logic for issues and PRs (.coddy/issues/, .coddy/prs/)."""

from coddy.services.store.issue_store import (
    add_message,
    create_issue,
    list_issues_by_status,
    list_pending_plan,
    list_queued,
    load_issue,
    save_issue,
    set_issue_status,
)
from coddy.services.store.pr_store import load_pr, save_pr, set_pr_status
from coddy.services.store.schemas import IssueComment, IssueFile, PRFile

__all__ = [
    "IssueComment",
    "IssueFile",
    "PRFile",
    "add_message",
    "create_issue",
    "list_issues_by_status",
    "list_pending_plan",
    "list_queued",
    "load_issue",
    "load_pr",
    "save_issue",
    "save_pr",
    "set_issue_status",
    "set_pr_status",
]
