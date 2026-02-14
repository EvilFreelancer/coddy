"""GitHub API adapter."""

from datetime import datetime
from typing import Any, Dict, List

import requests

from coddy.observer.adapters.base import GitPlatformAdapter, GitPlatformError
from coddy.observer.models import PR, Comment, Issue, ReviewComment


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _issue_from_api(data: Dict[str, Any]) -> Issue:
    user = data.get("user") or {}
    labels = [lb["name"] for lb in (data.get("labels") or []) if isinstance(lb, dict) and "name" in lb]
    return Issue(
        number=data["number"],
        title=data.get("title") or "",
        body=data.get("body") or "",
        author=user.get("login", ""),
        labels=labels,
        state=data.get("state", "open"),
        created_at=_parse_iso(data["created_at"]),
        updated_at=_parse_iso(data["updated_at"]),
    )


def _comment_from_api(data: Dict[str, Any]) -> Comment:
    user = data.get("user") or {}
    created = _parse_iso(data["created_at"])
    updated = _parse_iso(data.get("updated_at") or data["created_at"])
    return Comment(
        id=data["id"],
        body=data.get("body") or "",
        author=user.get("login", ""),
        created_at=created,
        updated_at=updated,
    )


def _pr_from_api(data: Dict[str, Any]) -> PR:
    head = data.get("head") or {}
    base = data.get("base") or {}
    return PR(
        number=data["number"],
        title=data.get("title") or "",
        body=data.get("body") or "",
        head_branch=head.get("ref", ""),
        base_branch=base.get("ref", ""),
        state=data.get("state", "open"),
        html_url=data.get("html_url"),
    )


def _review_comment_from_api(data: Dict[str, Any]) -> ReviewComment:
    user = data.get("user") or {}
    created = _parse_iso(data["created_at"])
    updated = _parse_iso(data.get("updated_at") or data["created_at"])
    return ReviewComment(
        id=data["id"],
        body=data.get("body") or "",
        author=user.get("login", ""),
        path=data.get("path", ""),
        line=data.get("line"),
        side=data.get("side", "RIGHT"),
        created_at=created,
        updated_at=updated,
        in_reply_to_id=data.get("in_reply_to_id"),
    )


class GitHubAdapter(GitPlatformAdapter):
    """GitHub API implementation."""

    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self._api_url = api_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"token {token}"
        self._session.headers["Accept"] = "application/vnd.github.v3+json"

    def _request(
        self,
        method: str,
        path: str,
        params: Dict[str, Any] | None = None,
        json: Dict[str, Any] | None = None,
    ) -> requests.Response:
        url = f"{self._api_url}{path}" if path.startswith("/") else f"{self._api_url}/{path}"
        resp = self._session.request(method, url, params=params, json=json, timeout=30)
        if resp.status_code >= 400:
            msg = resp.text or resp.reason or str(resp.status_code)
            try:
                msg = resp.json().get("message", msg)
            except Exception:
                pass
            raise GitPlatformError(f"{resp.status_code}: {msg}")
        return resp

    def get_issue(self, repo: str, issue_number: int) -> Issue:
        path = f"/repos/{repo}/issues/{issue_number}"
        url = f"{self._api_url}{path}"
        resp = self._session.request("GET", url, timeout=30)
        if resp.status_code == 404:
            raise GitPlatformError(f"Not found: issue #{issue_number}")
        if resp.status_code >= 400:
            raise GitPlatformError(f"{resp.status_code}: {resp.text or resp.reason}")
        data = resp.json()
        return _issue_from_api(data)

    def get_issue_comments(
        self,
        repo: str,
        issue_number: int,
        since: datetime | None = None,
    ) -> List[Comment]:
        path = f"/repos/{repo}/issues/{issue_number}/comments"
        params: Dict[str, Any] = {}
        if since is not None:
            params["since"] = since.isoformat()
        url = f"{self._api_url}{path}"
        resp = self._session.request("GET", url, params=params or None, timeout=30)
        if resp.status_code >= 400:
            raise GitPlatformError(f"{resp.status_code}: {resp.text or resp.reason}")
        data = resp.json() or []
        return [_comment_from_api(d) for d in data]

    def create_comment(self, repo: str, issue_number: int, body: str) -> Comment:
        path = f"/repos/{repo}/issues/{issue_number}/comments"
        url = f"{self._api_url}{path}"
        resp = self._session.request("POST", url, json={"body": body}, timeout=30)
        if resp.status_code >= 400:
            raise GitPlatformError(f"{resp.status_code}: {resp.text or resp.reason}")
        return _comment_from_api(resp.json())

    def set_issue_labels(self, repo: str, issue_number: int, labels: List[str]) -> None:
        path = f"/repos/{repo}/issues/{issue_number}/labels"
        self._request("PUT", path, json={"labels": labels})

    def get_default_branch(self, repo: str) -> str:
        data = self._request("GET", f"/repos/{repo}").json()
        return data.get("default_branch", "main")

    def create_branch(
        self,
        repo: str,
        branch_name: str,
        base_branch: str | None = None,
    ) -> None:
        if base_branch is None:
            base_branch = self.get_default_branch(repo)
        ref_path = f"/repos/{repo}/git/ref/heads/{base_branch}"
        ref_resp = self._request("GET", ref_path)
        sha = ref_resp.json()["object"]["sha"]
        self._request(
            "POST",
            f"/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        )

    def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PR:
        resp = self._request(
            "POST",
            f"/repos/{repo}/pulls",
            json={"title": title, "body": body, "head": head, "base": base},
        )
        return _pr_from_api(resp.json())

    def get_pr(self, repo: str, pr_number: int) -> PR:
        resp = self._request("GET", f"/repos/{repo}/pulls/{pr_number}")
        return _pr_from_api(resp.json())

    def list_open_issues(self, repo: str) -> List[Issue]:
        resp = self._request("GET", f"/repos/{repo}/issues", params={"state": "open"})
        data = resp.json() or []
        return [_issue_from_api(d) for d in data if "pull_request" not in d]

    def list_pr_review_comments(self, repo: str, pr_number: int) -> List[ReviewComment]:
        resp = self._request("GET", f"/repos/{repo}/pulls/{pr_number}/comments")
        data = resp.json() or []
        return [_review_comment_from_api(d) for d in data]

    def reply_to_review_comment(
        self,
        repo: str,
        pr_number: int,
        comment_id: int,
        body: str,
    ) -> Comment:
        resp = self._request(
            "POST",
            f"/repos/{repo}/pulls/{pr_number}/comments",
            json={"body": body, "in_reply_to": comment_id},
        )
        return _comment_from_api(resp.json())
