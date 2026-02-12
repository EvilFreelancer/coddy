"""Tests for StubAgent (sufficiency, code gen stub, review stub)."""

from datetime import UTC, datetime
from pathlib import Path

from coddy.agents.stub_agent import StubAgent
from coddy.models import Issue, ReviewComment


def _issue(body: str = "Some body", title: str = "Test") -> Issue:
    return Issue(
        number=1,
        title=title,
        body=body,
        author="user",
        labels=[],
        state="open",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_stub_agent_always_sufficient_when_min_zero() -> None:
    """StubAgent(min_body_length=0) always returns sufficient."""
    agent = StubAgent(min_body_length=0)
    result = agent.evaluate_sufficiency(_issue(body=""), [])
    assert result.sufficient is True
    assert result.clarification == ""


def test_stub_agent_insufficient_when_body_short() -> None:
    """StubAgent(min_body_length=50) returns insufficient for short body."""
    agent = StubAgent(min_body_length=50)
    result = agent.evaluate_sufficiency(_issue(body="short"), [])
    assert result.sufficient is False
    assert "detail" in result.clarification.lower() or "criteria" in result.clarification.lower()


def test_stub_agent_sufficient_when_body_long_enough() -> None:
    """StubAgent(min_body_length=10) returns sufficient for long enough
    body."""
    agent = StubAgent(min_body_length=10)
    result = agent.evaluate_sufficiency(_issue(body="This is a long enough body."), [])
    assert result.sufficient is True


def test_stub_agent_generate_code_no_raise() -> None:
    """generate_code does not raise (stub only logs)."""
    agent = StubAgent()
    agent.generate_code(_issue(), [])


def test_stub_agent_process_review_item_returns_none() -> None:
    """process_review_item returns None (stub does not reply)."""
    agent = StubAgent()
    dt = datetime.now(UTC)
    comments = [
        ReviewComment(1, "Fix this", "user", "a.py", 10, "RIGHT", dt, None, None),
    ]
    result = agent.process_review_item(3, 1, comments, 1, Path("/tmp"))
    assert result is None
