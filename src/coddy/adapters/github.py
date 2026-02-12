"""
GitHub API adapter.
"""

from datetime import datetime
from typing import Optional

import requests

from coddy.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.models import Issue


class GitHubAdapter(GitPlatformAdapter):
    """GitHub API implementation of GitPlatformAdapter."""

    def __init__(
        self,
        token: Optional[str] = None,
        api_url: str = "https://api.github.com",
    ) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def _request(self, method: str, path: str, **kwargs: object) -> requests.Response:
        url = f"{self.api_url}{path}"
        resp = self._session.request(method, url, timeout=30, **kwargs)
        if resp.status_code == 404:
            raise GitPlatformError(f"Not found: {path}")
        if resp.status_code >= 400:
            msg = resp.text
            try:
                data = resp.json()
                if "message" in data:
                    msg = data["message"]
            except Exception:
                pass
            raise GitPlatformError(f"GitHub API error {resp.status_code}: {msg}")
        return resp

    def get_issue(self, repo: str, issue_number: int) -> Issue:
        """
        Fetch a single issue by number.

        Args:
            repo: Repository in format owner/repo
            issue_number: Issue number

        Returns:
            Issue instance

        Raises:
            GitPlatformError: If the API call fails or issue not found
        """
        path = f"/repos/{repo}/issues/{issue_number}"
        resp = self._request("GET", path)
        data = resp.json()

        # GitHub returns PRs in the issues endpoint; we still map to Issue
        labels = [lb.get("name", "") for lb in data.get("labels", []) if lb.get("name")]
        created = data.get("created_at")
        updated = data.get("updated_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))

        user = data.get("user") or {}
        author = user.get("login", "")

        return Issue(
            number=data["number"],
            title=data.get("title", ""),
            body=data.get("body") or "",
            author=author,
            labels=labels,
            state=data.get("state", "open"),
            created_at=created,
            updated_at=updated,
        )
