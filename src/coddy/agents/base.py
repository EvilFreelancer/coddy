"""
Abstract base for AI agents (sufficiency check, code generation).
"""

from typing import List, Optional

from coddy.models import Comment, Issue


class SufficiencyResult:
    """Result of evaluating whether issue data is sufficient to implement."""

    def __init__(self, sufficient: bool, clarification: Optional[str] = None) -> None:
        self.sufficient = sufficient
        self.clarification = clarification or ""


class AIAgent:
    """
    Pluggable agent: evaluate issue sufficiency and generate code.

    Implementations can use Cursor CLI or other backends.
    """

    def evaluate_sufficiency(self, issue: Issue, comments: List[Comment]) -> SufficiencyResult:
        """
        Decide if the issue description and comments are sufficient to implement.

        Returns SufficiencyResult(sufficient=True) to proceed, or
        SufficiencyResult(sufficient=False, clarification="...") to ask the user.
        """
        raise NotImplementedError

    def generate_code(self, issue: Issue, comments: List[Comment]) -> Optional[str]:
        """
        Generate code for the issue (e.g. run Cursor CLI, apply changes).

        Called only when data is sufficient. May commit and push.
        Returns PR description body for create_pr, or None to use issue title/body.
        """
        raise NotImplementedError
