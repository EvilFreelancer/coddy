"""
Stub agent: considers data sufficient by default, no-op code generation.

Use for development or until Cursor CLI (or other) is wired.
"""

import logging
from pathlib import Path
from typing import List

from coddy.agents.base import AIAgent, SufficiencyResult
from coddy.models import Comment, Issue, ReviewComment


class StubAgent(AIAgent):
    """Agent that proceeds (or asks once if heuristic says insufficient), no-op
    code gen."""

    def __init__(self, min_body_length: int = 0) -> None:
        """
        Args:
            min_body_length: If > 0 and issue body is shorter, return insufficient
                            and ask for more detail (for testing clarification flow).
        """
        self.min_body_length = min_body_length

    def evaluate_sufficiency(self, issue: Issue, comments: List[Comment]) -> SufficiencyResult:
        """Return sufficient unless body is too short (when min_body_length >
        0)."""
        if self.min_body_length > 0 and len((issue.body or "").strip()) < self.min_body_length:
            return SufficiencyResult(
                sufficient=False,
                clarification=(
                    "Please add more details: what exactly should be implemented, and acceptance criteria if possible."
                ),
            )
        return SufficiencyResult(sufficient=True)

    def generate_code(self, issue: Issue, comments: List[Comment]) -> str | None:
        """Log only; no code changes.

        Returns None (no PR body from stub).
        """
        log = logging.getLogger("coddy.agents.stub")
        log.info("Code generation (stub): issue #%s - %s", issue.number, issue.title)
        return None

    def process_review_item(
        self,
        pr_number: int,
        issue_number: int,
        comments: List[ReviewComment],
        current_index: int,
        repo_dir: Path,
    ) -> str | None:
        """Stub: no changes, no reply."""
        log = logging.getLogger("coddy.agents.stub")
        log.info(
            "Review item (stub): PR #%s item %s/%s",
            pr_number,
            current_index,
            len(comments),
        )
        return None
