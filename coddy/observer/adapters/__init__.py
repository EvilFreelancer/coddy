"""Git platform adapters (base and implementations)."""

from coddy.observer.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.observer.adapters.github import GitHubAdapter

__all__ = ["GitPlatformAdapter", "GitPlatformError", "GitHubAdapter"]
