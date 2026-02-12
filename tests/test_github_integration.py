"""Integration tests for GitHub adapter using real API.

Requires GITHUB_TOKEN in environment. Uses repository from config (default EvilFreelancer/coddy).
Run: pytest tests/test_github_integration.py -v
"""

import os
from pathlib import Path

import pytest

from coddy.adapters.github import GitHubAdapter
from coddy.config import load_config
from coddy.models import Issue


def _get_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    path = os.environ.get("GITHUB_TOKEN_FILE")
    if path and Path(path).is_file():
        return Path(path).read_text().strip()
    return None


@pytest.mark.skipif(not _get_token(), reason="GITHUB_TOKEN or GITHUB_TOKEN_FILE not set")
def test_github_adapter_get_issue_from_own_repo() -> None:
    """
    Integration test: bot loads config and fetches an issue from its own repo via GitHub API.
    """
    config_path = Path("config.yaml")
    if not config_path.is_file():
        config_path = Path("config.example.yaml")
    config = load_config(config_path)

    token = config.github_token_resolved
    assert token, "GitHub token must be resolved from config/env"

    repo = config.bot.repository
    assert repo and "/" in repo, "bot.repository must be set (e.g. EvilFreelancer/coddy)"

    adapter = GitHubAdapter(token=token, api_url=config.github.api_url)

    # Fetch issue #1 from own repo (repo must have at least one issue)
    issue = adapter.get_issue(repo, 1)

    assert isinstance(issue, Issue)
    assert issue.number == 1
    assert isinstance(issue.title, str)
    assert isinstance(issue.body, str)
    assert issue.state in ("open", "closed")
    assert issue.author
