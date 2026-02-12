"""GitHub API adapter."""

from datetime import datetime
from typing import List

import requests

from coddy.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.models import PR, Comment, Issue, ReviewComment


class GitHubAdapter(GitPlatformAdapter):
    """GitHub API implementation of GitPlatformAdapter."""

    def __init__(
        self,
        token: str | None = None,
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
        """Fetch a single issue by number.

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
        return self._parse_issue(data)

    def _parse_issue(self, data: dict) -> Issue:
        """Build Issue from GitHub API issue dict."""
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

    def list_open_issues(self, repo: str) -> List[Issue]:
        """List all open issues in the repository (excludes pull requests).

        GitHub /repos/{owner}/{repo}/issues returns both issues and PRs;
        we filter out items that have pull_request set.
        """
        path = f"/repos/{repo}/issues"
        params = {"state": "open", "per_page": 100}
        resp = self._request("GET", path, params=params)
        data_list = resp.json()
        issues: List[Issue] = []
        for data in data_list:
            if data.get("pull_request") is not None:
                continue
            issues.append(self._parse_issue(data))
        return issues

    def set_issue_labels(self, repo: str, issue_number: int, labels: List[str]) -> None:
        """Set labels on an issue (replaces existing)."""
        path = f"/repos/{repo}/issues/{issue_number}/labels"
        self._request("PUT", path, json={"labels": labels})

    def create_comment(self, repo: str, issue_number: int, body: str) -> Comment:
        """Post a comment on an issue."""
        path = f"/repos/{repo}/issues/{issue_number}/comments"
        resp = self._request("POST", path, json={"body": body})
        data = resp.json()
        created = data.get("created_at")
        updated = data.get("updated_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        user = data.get("user") or {}
        author = user.get("login", "")
        return Comment(
            id=data["id"],
            body=data.get("body", ""),
            author=author,
            created_at=created,
            updated_at=updated,
        )

    def get_issue_comments(self, repo: str, issue_number: int, since: datetime | None = None) -> List[Comment]:
        """Fetch comments on an issue, optionally since a given datetime."""
        path = f"/repos/{repo}/issues/{issue_number}/comments"
        params: dict = {"per_page": 100}
        if since is not None:
            params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = self._request("GET", path, params=params)
        data_list = resp.json()
        comments: List[Comment] = []
        for data in data_list:
            created = data.get("created_at")
            updated = data.get("updated_at")
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if isinstance(updated, str):
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            user = data.get("user") or {}
            author = user.get("login", "")
            comments.append(
                Comment(
                    id=data["id"],
                    body=data.get("body", ""),
                    author=author,
                    created_at=created,
                    updated_at=updated,
                )
            )
        return comments

    def get_default_branch(self, repo: str) -> str:
        """Return default branch name (e.g. main)."""
        resp = self._request("GET", f"/repos/{repo}")
        return resp.json().get("default_branch", "main")

    def create_branch(self, repo: str, branch_name: str) -> None:
        """Create a branch from the default branch HEAD."""
        default_branch = self.get_default_branch(repo)
        ref_path = f"/repos/{repo}/git/ref/heads/{default_branch}"
        ref_resp = self._request("GET", ref_path)
        ref_data = ref_resp.json()
        sha = ref_data.get("object", {}).get("sha")
        if not sha:
            raise GitPlatformError("Could not get default branch SHA")
        self._request("POST", f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch_name}", "sha": sha})

    def get_pr(self, repo: str, pr_number: int) -> PR:
        """Fetch a pull request by number."""
        path = f"/repos/{repo}/pulls/{pr_number}"
        resp = self._request("GET", path)
        data = resp.json()
        return PR(
            number=data["number"],
            title=data.get("title", ""),
            body=data.get("body", ""),
            head_branch=data.get("head", {}).get("ref", ""),
            base_branch=data.get("base", {}).get("ref", ""),
            state=data.get("state", "open"),
            html_url=data.get("html_url"),
        )

    def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> PR:
        """Create a pull request."""
        resp = self._request(
            "POST",
            f"/repos/{repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body or ""},
        )
        data = resp.json()
        return PR(
            number=data["number"],
            title=data.get("title", title),
            body=data.get("body", body or ""),
            head_branch=data.get("head", {}).get("ref", head),
            base_branch=data.get("base", {}).get("ref", base),
            state=data.get("state", "open"),
            html_url=data.get("html_url"),
        )

    def list_pr_review_comments(self, repo: str, pr_number: int, since: datetime | None = None) -> List[ReviewComment]:
        """List review comments on a pull request, optionally since a given
        datetime."""
        path = f"/repos/{repo}/pulls/{pr_number}/comments"
        params: dict = {"per_page": 100, "sort": "created", "direction": "asc"}
        if since is not None:
            params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = self._request("GET", path, params=params)
        data_list = resp.json()
        comments: List[ReviewComment] = []
        for data in data_list:
            created = data.get("created_at")
            updated = data.get("updated_at")
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if isinstance(updated, str):
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            user = data.get("user") or {}
            author = user.get("login", "")
            line = data.get("line")
            comments.append(
                ReviewComment(
                    id=data["id"],
                    body=data.get("body", ""),
                    author=author,
                    path=data.get("path", ""),
                    line=int(line) if line is not None else None,
                    side=data.get("side", "RIGHT"),
                    created_at=created,
                    updated_at=updated,
                    in_reply_to_id=data.get("in_reply_to_id"),
                )
            )
        return comments

    def reply_to_review_comment(self, repo: str, pr_number: int, in_reply_to_comment_id: int, body: str) -> Comment:
        """Post a reply to a review comment."""
        path = f"/repos/{repo}/pulls/{pr_number}/comments"
        resp = self._request(
            "POST",
            path,
            json={"body": body, "in_reply_to": in_reply_to_comment_id},
        )
        data = resp.json()
        created = data.get("created_at")
        updated = data.get("updated_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        user = data.get("user") or {}
        author = user.get("login", "")
        return Comment(
            id=data["id"],
            body=data.get("body", ""),
            author=author,
            created_at=created,
            updated_at=updated,
        )
