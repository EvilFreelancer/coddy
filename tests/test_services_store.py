"""Unified tests for store (issue_store, pr_store, schemas)."""

from pathlib import Path
from unittest.mock import patch

from coddy.services.store import (
    IssueComment,
    IssueFile,
    PRFile,
    add_comment,
    create_issue,
    list_issues_by_status,
    list_pending_plan,
    list_queued,
    load_issue,
    load_pr,
    save_issue,
    save_pr,
    set_issue_status,
    set_pr_status,
)


class TestIssueStore:
    """Tests for issue_store (load, save, create, add_comment,
    set_issue_status, list_*)."""

    def test_create_issue_writes_yaml(self, tmp_path: Path) -> None:
        """create_issue writes .coddy/issues/{n}.yaml with status
        pending_plan."""
        create_issue(
            tmp_path,
            issue_id=7,
            repo="owner/repo",
            title="Add login",
            description="Add a login form.",
            author="@user",
        )
        path = tmp_path / ".coddy" / "issues" / "7.yaml"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "pending_plan" in content
        assert "Add login" in content
        assert "Add a login form" in content
        assert "owner/repo" in content
        assert "assigned_at" in content

    def test_load_issue_returns_issue_file(self, tmp_path: Path) -> None:
        """load_issue parses YAML into IssueFile."""
        create_issue(
            tmp_path,
            issue_id=8,
            repo="o/r",
            title="T",
            description="D",
            author="@u",
        )
        issue = load_issue(tmp_path, 8)
        assert issue is not None
        assert issue.status == "pending_plan"
        assert issue.title == "T"
        assert issue.description == "D"
        assert issue.repo == "o/r"
        assert len(issue.comments) == 0

    def test_load_issue_missing_returns_none(self, tmp_path: Path) -> None:
        """load_issue returns None when file does not exist."""
        assert load_issue(tmp_path, 999) is None

    def test_load_issue_invalid_yaml_returns_none(self, tmp_path: Path) -> None:
        """load_issue returns None when YAML is invalid and logs warning."""
        path = tmp_path / ".coddy" / "issues"
        path.mkdir(parents=True)
        (path / "11.yaml").write_text("not: valid: yaml: [[[", encoding="utf-8")
        assert load_issue(tmp_path, 11) is None

    def test_load_issue_empty_file_returns_none(self, tmp_path: Path) -> None:
        """load_issue returns None when file is empty or null YAML."""
        path = tmp_path / ".coddy" / "issues"
        path.mkdir(parents=True)
        (path / "12.yaml").write_text("", encoding="utf-8")
        assert load_issue(tmp_path, 12) is None
        (path / "13.yaml").write_text("null", encoding="utf-8")
        assert load_issue(tmp_path, 13) is None

    def test_load_issue_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        """load_issue returns None when YAML does not match IssueFile schema
        (missing required)."""
        path = tmp_path / ".coddy" / "issues"
        path.mkdir(parents=True)
        (path / "14.yaml").write_text(
            "created_at: '2024'\nupdated_at: '2024'\nstatus: pending_plan",
            encoding="utf-8",
        )
        assert load_issue(tmp_path, 14) is None

    def test_add_comment_appends_and_updates(self, tmp_path: Path) -> None:
        """add_comment appends to comments and updates updated_at."""
        create_issue(tmp_path, 9, "o/r", "T", "D", "@u")
        add_comment(tmp_path, 9, "@bot", "Here is the plan.", created_at=2000, updated_at=2000)
        issue = load_issue(tmp_path, 9)
        assert issue is not None
        assert len(issue.comments) == 1
        assert issue.comments[0].name == "@bot"
        assert issue.comments[0].content == "Here is the plan."
        assert issue.comments[0].created_at == 2000
        assert issue.comments[0].updated_at == 2000

    def test_add_comment_when_issue_not_found_does_nothing(self, tmp_path: Path) -> None:
        """add_comment does not crash when issue file is missing."""
        add_comment(tmp_path, 999, "@bot", "Hello")
        assert load_issue(tmp_path, 999) is None

    def test_set_issue_status_updates_file(self, tmp_path: Path) -> None:
        """set_issue_status changes status in file."""
        create_issue(tmp_path, 10, "o/r", "T", "D", "@u")
        set_issue_status(tmp_path, 10, "waiting_confirmation")
        issue = load_issue(tmp_path, 10)
        assert issue is not None
        assert issue.status == "waiting_confirmation"
        set_issue_status(tmp_path, 10, "queued")
        issue2 = load_issue(tmp_path, 10)
        assert issue2 is not None
        assert issue2.status == "queued"

    def test_set_issue_status_when_issue_not_found_does_nothing(self, tmp_path: Path) -> None:
        """set_issue_status does not crash when issue file is missing."""
        set_issue_status(tmp_path, 999, "queued")

    def test_list_issues_by_status(self, tmp_path: Path) -> None:
        """list_issues_by_status returns only issues with that status."""
        create_issue(tmp_path, 1, "o/r", "A", "", "@u")
        create_issue(tmp_path, 2, "o/r", "B", "", "@u")
        set_issue_status(tmp_path, 2, "queued")
        pending = list_issues_by_status(tmp_path, "pending_plan")
        queued = list_issues_by_status(tmp_path, "queued")
        assert len(pending) == 1
        assert pending[0][0] == 1
        assert len(queued) == 1
        assert queued[0][0] == 2

    def test_list_issues_by_status_when_no_dir_returns_empty(self, tmp_path: Path) -> None:
        """list_issues_by_status returns [] when .coddy/issues does not
        exist."""
        assert list_issues_by_status(tmp_path, "pending_plan") == []
        assert list_issues_by_status(tmp_path, "queued") == []

    def test_list_issues_by_status_skips_non_digit_stem(self, tmp_path: Path) -> None:
        """list_issues_by_status skips files whose stem is not all digits."""
        path = tmp_path / ".coddy" / "issues"
        path.mkdir(parents=True)
        (path / "1a.yaml").write_text(
            "author: x\ncreated_at: '2024'\nupdated_at: '2024'\nstatus: pending_plan",
            encoding="utf-8",
        )
        create_issue(tmp_path, 2, "o/r", "T", "D", "@u")
        result = list_issues_by_status(tmp_path, "pending_plan")
        assert len(result) == 1
        assert result[0][0] == 2

    def test_list_issues_by_status_skips_file_when_int_stem_raises(self, tmp_path: Path) -> None:
        """list_issues_by_status skips file when int(f.stem) raises (e.g.
        unicode digit)."""
        path = tmp_path / ".coddy" / "issues"
        path.mkdir(parents=True)
        (path / "\u0661.yaml").write_text(
            "author: x\ncreated_at: '2024'\nupdated_at: '2024'\nstatus: pending_plan",
            encoding="utf-8",
        )
        create_issue(tmp_path, 2, "o/r", "T", "D", "@u")
        result = list_issues_by_status(tmp_path, "pending_plan")
        assert len(result) == 1
        assert result[0][0] == 2

    def test_list_issues_by_status_skips_file_when_load_raises(self, tmp_path: Path) -> None:
        """list_issues_by_status skips file and continues when load_issue
        raises."""
        create_issue(tmp_path, 1, "o/r", "A", "", "@u")
        with patch(
            "coddy.services.store.issue_store.load_issue",
            side_effect=RuntimeError("read error"),
        ):
            from coddy.services.store.issue_store import list_issues_by_status as list_status

            result = list_status(tmp_path, "pending_plan")
        assert len(result) == 0

    def test_list_pending_plan_and_list_queued(self, tmp_path: Path) -> None:
        """list_pending_plan and list_queued filter by status."""
        create_issue(tmp_path, 3, "o/r", "X", "", "@u")
        create_issue(tmp_path, 4, "o/r", "Y", "", "@u")
        set_issue_status(tmp_path, 4, "queued")
        assert len(list_pending_plan(tmp_path)) == 1
        assert list_pending_plan(tmp_path)[0][0] == 3
        assert len(list_queued(tmp_path)) == 1
        assert list_queued(tmp_path)[0][0] == 4

    def test_save_issue_persists_manual_issue(self, tmp_path: Path) -> None:
        """save_issue writes an IssueFile built by hand."""
        issue = IssueFile(
            author="@x",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            status="queued",
            title="Manual",
            description="Desc",
            comments=[IssueComment(name="@x", content="Manual\n\nDesc", created_at=0, updated_at=0)],
            repo="a/b",
            issue_id=99,
        )
        save_issue(tmp_path, 99, issue)
        loaded = load_issue(tmp_path, 99)
        assert loaded is not None
        assert loaded.title == "Manual"
        assert loaded.status == "queued"

    def test_save_issue_with_none_issue_id_uses_param(self, tmp_path: Path) -> None:
        """save_issue adds issue_id to payload when issue.issue_id is None."""
        issue = IssueFile(
            author="@x",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="No id",
            description="",
            issue_id=None,
        )
        save_issue(tmp_path, 42, issue)
        loaded = load_issue(tmp_path, 42)
        assert loaded is not None
        assert loaded.issue_id == 42

    def test_create_issue_with_optional_timestamps(self, tmp_path: Path) -> None:
        """create_issue accepts optional created_at and updated_at (Unix timestamps)."""
        ts_2020_01_01 = 1577836800  # 2020-01-01T00:00:00Z
        ts_2020_01_02 = 1577923200  # 2020-01-02T00:00:00Z
        issue = create_issue(
            tmp_path,
            issue_id=20,
            repo="r",
            title="T",
            description="D",
            author="@u",
            created_at=ts_2020_01_01,
            updated_at=ts_2020_01_02,
        )
        assert issue.created_at == ts_2020_01_01
        assert issue.updated_at == ts_2020_01_02


class TestPRStore:
    """Tests for pr_store (load_pr, save_pr, set_pr_status)."""

    def test_load_pr_missing_returns_none(self, tmp_path: Path) -> None:
        """load_pr returns None when file does not exist."""
        assert load_pr(tmp_path, 999) is None

    def test_load_pr_empty_returns_none(self, tmp_path: Path) -> None:
        """load_pr returns None when file is empty or null."""
        path = tmp_path / ".coddy" / "prs"
        path.mkdir(parents=True)
        (path / "1.yaml").write_text("", encoding="utf-8")
        assert load_pr(tmp_path, 1) is None
        (path / "2.yaml").write_text("null", encoding="utf-8")
        assert load_pr(tmp_path, 2) is None

    def test_load_pr_invalid_yaml_returns_none(self, tmp_path: Path) -> None:
        """load_pr returns None when YAML is invalid."""
        path = tmp_path / ".coddy" / "prs"
        path.mkdir(parents=True)
        (path / "3.yaml").write_text("not: valid: yaml", encoding="utf-8")
        assert load_pr(tmp_path, 3) is None

    def test_save_pr_creates_file(self, tmp_path: Path) -> None:
        """save_pr writes .coddy/prs/{pr_id}.yaml."""
        pr = PRFile(
            pr_id=5,
            repo="owner/repo",
            status="open",
            issue_id=3,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        )
        out = save_pr(tmp_path, pr)
        assert out == tmp_path / ".coddy" / "prs" / "5.yaml"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "open" in content
        assert "owner/repo" in content

    def test_set_pr_status_creates_new_pr(self, tmp_path: Path) -> None:
        """set_pr_status creates PR file when it does not exist."""
        set_pr_status(tmp_path, 10, "open", repo="o/r", issue_number=7)
        pr = load_pr(tmp_path, 10)
        assert pr is not None
        assert pr.pr_id == 10
        assert pr.status == "open"
        assert pr.repo == "o/r"
        assert pr.issue_id == 7

    def test_set_pr_status_updates_existing(self, tmp_path: Path) -> None:
        """set_pr_status updates status on existing PR."""
        set_pr_status(tmp_path, 11, "open", repo="o/r", issue_number=1)
        set_pr_status(tmp_path, 11, "merged")
        pr = load_pr(tmp_path, 11)
        assert pr is not None
        assert pr.status == "merged"

    def test_set_pr_status_updates_repo_and_issue_id(self, tmp_path: Path) -> None:
        """set_pr_status updates repo and issue_id when passed on existing
        PR."""
        set_pr_status(tmp_path, 12, "open", repo="o/r", issue_number=2)
        set_pr_status(tmp_path, 12, "closed", repo="other/repo", issue_number=99)
        pr = load_pr(tmp_path, 12)
        assert pr is not None
        assert pr.repo == "other/repo"
        assert pr.issue_id == 99
        assert pr.status == "closed"


class TestIssueFileSchema:
    """Tests for IssueFile and IssueComment schemas and
    IssueFile.to_markdown()."""

    def test_issue_comment_model(self) -> None:
        """IssueComment accepts name, content, created_at, updated_at."""
        msg = IssueComment(name="@user", content="Hello", created_at=1234567890, updated_at=1234567890)
        assert msg.name == "@user"
        assert msg.content == "Hello"
        assert msg.created_at == 1234567890
        assert msg.updated_at == 1234567890

    def test_issue_file_minimal(self) -> None:
        """IssueFile with required fields only."""
        issue = IssueFile(
            author="@author",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert issue.status == "pending_plan"
        assert issue.title == ""
        assert issue.description == ""
        assert issue.comments == []
        assert issue.repo is None
        assert issue.issue_id is None
        assert issue.assigned_at is None

    def test_issue_file_full(self) -> None:
        """IssueFile with comments and meta."""
        msg = IssueComment(name="@user", content="Title\n\nBody", created_at=1000, updated_at=1000)
        issue = IssueFile(
            author="@user",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
            status="waiting_confirmation",
            title="Add feature",
            description="Please add X.",
            comments=[msg],
            repo="owner/repo",
            issue_id=42,
            assigned_at="2024-01-01T12:00:00Z",
        )
        assert issue.status == "waiting_confirmation"
        assert issue.title == "Add feature"
        assert len(issue.comments) == 1
        assert issue.comments[0].content == "Title\n\nBody"
        assert issue.repo == "owner/repo"
        assert issue.issue_id == 42

    def test_issue_file_roundtrip_dict(self) -> None:
        """IssueFile can be built from model_dump()."""
        issue = IssueFile(
            author="@a",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="T",
            description="D",
            comments=[IssueComment(name="@a", content="T\n\nD", created_at=0, updated_at=0)],
        )
        data = issue.model_dump(mode="json")
        restored = IssueFile.model_validate(data)
        assert restored.title == issue.title
        assert restored.comments[0].content == issue.comments[0].content

    def test_issue_to_markdown_title_and_description(self) -> None:
        """IssueFile.to_markdown() outputs title and description sections."""
        issue = IssueFile(
            author="@user",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="Add feature",
            description="Please add a button.",
            issue_id=42,
        )
        md = issue.to_markdown()
        assert "# Issue 42" in md
        assert "## Title" in md
        assert "Add feature" in md
        assert "## Description" in md
        assert "Please add a button." in md

    def test_issue_to_markdown_with_comments(self) -> None:
        """to_markdown includes comments section with name, content,
        timestamps."""
        issue = IssueFile(
            author="@user",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="T",
            description="D",
            comments=[
                IssueComment(name="@user", content="T\n\nD", created_at=1000, updated_at=1000),
                IssueComment(name="@bot", content="Here is the plan.", created_at=2000, updated_at=2000),
            ],
            issue_id=7,
        )
        md = issue.to_markdown()
        assert "## Comments" in md
        assert "### @user" in md
        assert "T\n\nD" in md
        assert "### @bot" in md
        assert "Here is the plan." in md
        assert "created_at: 1000" in md
        assert "created_at: 2000" in md

    def test_issue_to_markdown_without_issue_id(self) -> None:
        """to_markdown() works without issue_id (no # Issue N line)."""
        issue = IssueFile(
            author="@u",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="T",
        )
        md = issue.to_markdown()
        assert "## Title" in md
        assert "T" in md

    def test_issue_to_markdown_empty_description(self) -> None:
        """Empty description renders as (no description)."""
        issue = IssueFile(
            author="@u",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="Only title",
            description="",
        )
        md = issue.to_markdown()
        assert "(no description)" in md

    def test_issue_to_markdown_no_comments_section_when_empty(self) -> None:
        """When comments is empty, Comments section is not added."""
        issue = IssueFile(
            author="@u",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="T",
            description="D",
            comments=[],
        )
        md = issue.to_markdown()
        assert "## Comments" not in md

    def test_issue_to_markdown_uses_issue_id_in_header(self) -> None:
        """IssueFile.to_markdown() uses issue_id for header when set."""
        issue = IssueFile(
            author="@u",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            title="Direct",
            description="Body",
            issue_id=10,
        )
        md = issue.to_markdown()
        assert "# Issue 10" in md
        assert "## Title" in md
        assert "Direct" in md
        assert "## Description" in md
        assert "Body" in md


class TestPRFileSchema:
    """Tests for PRFile schema and PRFile.to_markdown()."""

    def test_pr_file_to_markdown(self) -> None:
        """PRFile.to_markdown() renders repo, status, issue_id, timestamps."""
        pr = PRFile(
            pr_id=5,
            repo="owner/repo",
            status="open",
            issue_id=3,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        )
        md = pr.to_markdown()
        assert "# PR #5" in md
        assert "**Repo:** `owner/repo`" in md
        assert "**Status:** open" in md
        assert "**Linked issue:** #3" in md
        assert "**Created:** 2024-01-01" in md
        assert "**Updated:** 2024-01-02" in md

    def test_pr_file_to_markdown_without_issue_id(self) -> None:
        """PRFile.to_markdown() works when issue_id is None."""
        pr = PRFile(
            pr_id=6,
            repo="a/b",
            status="merged",
            issue_id=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        )
        md = pr.to_markdown()
        assert "# PR #6" in md
        assert "**Linked issue:**" not in md or "None" not in md
