"""Abstract base for AI agents (sufficiency check, code generation, review
feedback)."""

from pathlib import Path
from typing import List

from coddy.models import Comment, Issue, ReviewComment


class SufficiencyResult:
    """Result of evaluating whether issue data is sufficient to implement."""

    def __init__(self, sufficient: bool, clarification: str | None = None) -> None:
        self.sufficient = sufficient
        self.clarification = clarification or ""


class AIAgent:
    """
    Pluggable agent: evaluate issue sufficiency and generate code.

    Implementations can use Cursor CLI or other backends.
    """

    def evaluate_sufficiency(self, issue: Issue, comments: List[Comment]) -> SufficiencyResult:
        """Decide if the issue description and comments are sufficient to
        implement.

        Returns SufficiencyResult(sufficient=True) to proceed, or
        SufficiencyResult(sufficient=False, clarification="...") to ask the user.
        """
        raise NotImplementedError

    def generate_code(self, issue: Issue, comments: List[Comment]) -> str | None:
        """Generate code for the issue (e.g. run Cursor CLI, apply changes).

        Called only when data is sufficient. May commit and push.
        Returns PR description body for create_pr, or None to use issue
        title/body.
        """
        raise NotImplementedError

    def process_review_item(
        self,
        pr_number: int,
        issue_number: int,
        comments: List[ReviewComment],
        current_index: int,
        repo_dir: Path,
    ) -> str | None:
        """Address one PR review comment (current item in the todo list).

        May apply code changes and/or produce a reply. Caller will
        commit/push and post the reply to the comment thread. Returns
        the reply text to post for this comment, or None if no reply.
        """
        raise NotImplementedError
