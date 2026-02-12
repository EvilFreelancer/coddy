"""Git platform adapters."""

from coddy.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.adapters.github import GitHubAdapter

__all__ = ["GitPlatformAdapter", "GitPlatformError", "GitHubAdapter"]
