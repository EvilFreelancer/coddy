"""Issue storage and state (.coddy/issues/, .coddy/state/)."""

from coddy.observer.issues.issue_file import IssueFile, IssueMessage
from coddy.observer.issues.issue_state import (
    clear_state,
    get_state,
    list_pending_plan_states,
    set_pending_plan,
    set_waiting_confirmation,
)
from coddy.observer.issues.issue_store import (
    add_message,
    create_issue,
    list_issues_by_status,
    list_pending_plan,
    list_queued,
    load_issue,
    save_issue,
    set_status,
)

__all__ = [
    "IssueFile",
    "IssueMessage",
    "add_message",
    "create_issue",
    "load_issue",
    "list_issues_by_status",
    "list_pending_plan",
    "list_queued",
    "save_issue",
    "set_status",
    "clear_state",
    "get_state",
    "list_pending_plan_states",
    "set_pending_plan",
    "set_waiting_confirmation",
]
