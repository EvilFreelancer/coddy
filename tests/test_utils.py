"""Tests for branch name sanitization utility."""

import pytest

from coddy.utils import is_valid_branch_name, sanitize_branch_name


def test_sanitize_branch_name_replaces_spaces_with_dashes() -> None:
    """Spaces are replaced with single dashes."""
    assert sanitize_branch_name("add user login") == "add-user-login"
    assert sanitize_branch_name("  a  b  ") == "a-b"


def test_sanitize_branch_name_removes_invalid_characters() -> None:
    """Invalid characters (e.g. special chars) are removed."""
    assert sanitize_branch_name("add~feature") == "addfeature"
    assert sanitize_branch_name("fix: bug") == "fix-bug"
    assert sanitize_branch_name("test?me") == "testme"
    assert sanitize_branch_name("foo*bar") == "foobar"
    assert sanitize_branch_name("a.b.c") == "a-b-c"


def test_sanitize_branch_name_lowercase() -> None:
    """Output is lowercase."""
    assert sanitize_branch_name("Add Feature") == "add-feature"


def test_sanitize_branch_name_strips_and_collapses_dashes() -> None:
    """Leading/trailing dashes and repeated dashes are normalized."""
    assert sanitize_branch_name("--hello--world--") == "hello-world"
    assert sanitize_branch_name("  spaces  ") == "spaces"


def test_sanitize_branch_name_truncates_to_max_length() -> None:
    """Long result is truncated to max_length, default 100."""
    long_input = "a" * 150
    result = sanitize_branch_name(long_input, max_length=100)
    assert len(result) <= 100
    result_default = sanitize_branch_name(long_input)
    assert len(result_default) <= 100


def test_sanitize_branch_name_truncate_does_not_end_with_dash() -> None:
    """When truncating, result does not end with a trailing dash."""
    long_input = "a-b-" * 30
    result = sanitize_branch_name(long_input, max_length=20)
    assert len(result) <= 20
    assert not result.endswith("-")


def test_sanitize_branch_name_empty_after_sanitize() -> None:
    """If only invalid chars, return empty string."""
    assert sanitize_branch_name("???***") == ""
    assert sanitize_branch_name("   ") == ""


def test_is_valid_branch_name_accepts_valid_names() -> None:
    """Valid branch names (digits, lowercase letters, dashes) are accepted."""
    assert is_valid_branch_name("42-add-feature") is True
    assert is_valid_branch_name("1-fix-bug") is True
    assert is_valid_branch_name("123") is True
    assert is_valid_branch_name("a-b-c") is True


def test_is_valid_branch_name_rejects_invalid() -> None:
    """Invalid branch names are rejected (spaces, special chars, double dot)."""
    assert is_valid_branch_name("42 add feature") is False
    assert is_valid_branch_name("42..add") is False
    assert is_valid_branch_name("42~feature") is False
    assert is_valid_branch_name("42:feature") is False
    assert is_valid_branch_name("42?feature") is False
    assert is_valid_branch_name("") is False
    assert is_valid_branch_name("-leading") is False
    assert is_valid_branch_name("trailing-") is False


def test_sanitize_result_is_valid() -> None:
    """Result of sanitize_branch_name is always valid when non-empty."""
    inputs = ["Add user login", "Fix: bug???", "a" * 80, "  x  y  z  "]
    for text in inputs:
        result = sanitize_branch_name(text, max_length=100)
        if result:
            assert is_valid_branch_name(result), f"sanitize({text!r}) produced invalid name {result!r}"
