# Copyright (c) Microsoft. All rights reserved.

"""Tests for stale_issue_pr_ping.py."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Ensure the script directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from stale_issue_pr_ping import (
    LABEL,
    PING_COMMENT,
    author_replied_after,
    find_last_team_comment,
    get_team_members,
    main,
    ping,
    should_ping,
)

TEAM = {"alice", "bob"}
NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_comment(login: str | None, created_at: datetime) -> MagicMock:
    """Create a mock IssueComment."""
    c = MagicMock()
    if login is None:
        c.user = None
    else:
        c.user = MagicMock()
        c.user.login = login
    c.created_at = created_at
    return c


def _make_label(name: str) -> MagicMock:
    lbl = MagicMock()
    lbl.name = name
    return lbl


def _make_issue(
    author: str = "external",
    labels: list[str] | None = None,
    comment_count: int = 1,
    comments: list[MagicMock] | None = None,
    pull_request: bool = False,
    number: int = 42,
) -> MagicMock:
    issue = MagicMock()
    issue.user = MagicMock()
    issue.user.login = author
    issue.number = number
    issue.labels = [_make_label(n) for n in (labels or [])]
    issue.comments = comment_count
    issue.pull_request = MagicMock() if pull_request else None
    if comments is not None:
        issue.get_comments.return_value = comments
    return issue


# ---------------------------------------------------------------------------
# find_last_team_comment
# ---------------------------------------------------------------------------

class TestFindLastTeamComment:
    def test_returns_last_team_comment(self):
        c1 = _make_comment("alice", datetime(2026, 3, 1, tzinfo=timezone.utc))
        c2 = _make_comment("external", datetime(2026, 3, 2, tzinfo=timezone.utc))
        c3 = _make_comment("bob", datetime(2026, 3, 3, tzinfo=timezone.utc))
        assert find_last_team_comment([c1, c2, c3], TEAM) is c3

    def test_returns_none_when_no_team_comments(self):
        c1 = _make_comment("external", datetime(2026, 3, 1, tzinfo=timezone.utc))
        assert find_last_team_comment([c1], TEAM) is None

    def test_returns_none_for_empty_list(self):
        assert find_last_team_comment([], TEAM) is None

    def test_skips_deleted_user(self):
        c1 = _make_comment(None, datetime(2026, 3, 1, tzinfo=timezone.utc))
        c2 = _make_comment("alice", datetime(2026, 3, 2, tzinfo=timezone.utc))
        assert find_last_team_comment([c1, c2], TEAM) is c2

    def test_only_deleted_users(self):
        c1 = _make_comment(None, datetime(2026, 3, 1, tzinfo=timezone.utc))
        assert find_last_team_comment([c1], TEAM) is None


# ---------------------------------------------------------------------------
# author_replied_after
# ---------------------------------------------------------------------------

class TestAuthorRepliedAfter:
    def test_author_replied(self):
        after = datetime(2026, 3, 1, tzinfo=timezone.utc)
        c1 = _make_comment("external", datetime(2026, 3, 2, tzinfo=timezone.utc))
        assert author_replied_after([c1], "external", after) is True

    def test_author_not_replied(self):
        after = datetime(2026, 3, 5, tzinfo=timezone.utc)
        c1 = _make_comment("external", datetime(2026, 3, 2, tzinfo=timezone.utc))
        assert author_replied_after([c1], "external", after) is False

    def test_different_user_replied(self):
        after = datetime(2026, 3, 1, tzinfo=timezone.utc)
        c1 = _make_comment("someone_else", datetime(2026, 3, 2, tzinfo=timezone.utc))
        assert author_replied_after([c1], "external", after) is False

    def test_deleted_user_comment(self):
        after = datetime(2026, 3, 1, tzinfo=timezone.utc)
        c1 = _make_comment(None, datetime(2026, 3, 2, tzinfo=timezone.utc))
        assert author_replied_after([c1], "external", after) is False


# ---------------------------------------------------------------------------
# should_ping
# ---------------------------------------------------------------------------

class TestShouldPing:
    def test_should_ping_stale_issue(self):
        team_comment = _make_comment("alice", NOW - timedelta(days=5))
        issue = _make_issue(comments=[team_comment], comment_count=1)
        assert should_ping(issue, TEAM, 4, NOW) is True

    def test_skip_team_member_author(self):
        issue = _make_issue(author="alice", comment_count=1)
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_skip_already_labeled(self):
        issue = _make_issue(labels=[LABEL], comment_count=1)
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_skip_no_comments(self):
        issue = _make_issue(comment_count=0)
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_skip_no_team_comment(self):
        c = _make_comment("external", NOW - timedelta(days=5))
        issue = _make_issue(comments=[c], comment_count=1)
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_skip_author_replied(self):
        team_c = _make_comment("alice", NOW - timedelta(days=5))
        author_c = _make_comment("external", NOW - timedelta(days=3))
        issue = _make_issue(comments=[team_c, author_c], comment_count=2)
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_skip_not_enough_days(self):
        team_comment = _make_comment("alice", NOW - timedelta(days=2))
        issue = _make_issue(comments=[team_comment], comment_count=1)
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_aware_datetime_handled(self):
        """Timezone-aware datetimes should not be mangled by astimezone."""
        aware_dt = (NOW - timedelta(days=5)).replace(tzinfo=timezone.utc)
        team_comment = _make_comment("alice", aware_dt)
        issue = _make_issue(comments=[team_comment], comment_count=1)
        assert should_ping(issue, TEAM, 4, NOW) is True

    def test_naive_datetime_handled(self):
        """Naive datetimes (pre-PyGithub 2.x) should be handled by astimezone."""
        naive_dt = (NOW - timedelta(days=5)).replace(tzinfo=None)
        team_comment = _make_comment("alice", naive_dt)
        issue = _make_issue(comments=[team_comment], comment_count=1)
        # astimezone on naive datetime treats it as local time; just verify no crash
        should_ping(issue, TEAM, 4, NOW)


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------

class TestPing:
    def test_dry_run(self, capsys):
        issue = _make_issue()
        assert ping(issue, dry_run=True) is True
        issue.create_comment.assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out

    def test_success(self, capsys):
        issue = _make_issue()
        assert ping(issue, dry_run=False) is True
        issue.create_comment.assert_called_once()
        issue.add_to_labels.assert_called_once_with(LABEL)

    @patch("stale_issue_pr_ping.time.sleep")
    def test_retry_on_failure(self, mock_sleep):
        issue = _make_issue()
        issue.create_comment.side_effect = [Exception("net error"), None]
        assert ping(issue, dry_run=False) is True
        assert issue.create_comment.call_count == 2
        mock_sleep.assert_called_once()

    @patch("stale_issue_pr_ping.time.sleep")
    def test_idempotent_retry_skips_comment_on_label_failure(self, mock_sleep):
        """If create_comment succeeds but add_to_labels fails, retry should not re-comment."""
        issue = _make_issue()
        issue.add_to_labels.side_effect = [Exception("label error"), None]
        assert ping(issue, dry_run=False) is True
        # Comment should only be created once even though there were 2 attempts
        assert issue.create_comment.call_count == 1
        assert issue.add_to_labels.call_count == 2

    @patch("stale_issue_pr_ping.time.sleep")
    def test_all_retries_fail(self, mock_sleep):
        issue = _make_issue()
        issue.create_comment.side_effect = Exception("permanent error")
        assert ping(issue, dry_run=False) is False
        assert issue.create_comment.call_count == 3


# ---------------------------------------------------------------------------
# get_team_members
# ---------------------------------------------------------------------------

class TestGetTeamMembers:
    def test_success(self):
        g = MagicMock()
        member = MagicMock()
        member.login = "alice"
        g.get_organization.return_value.get_team_by_slug.return_value.get_members.return_value = [member]
        assert get_team_members(g, "org", "my-team") == {"alice"}

    def test_403_error_message(self, capsys):
        from github import GithubException

        g = MagicMock()
        g.get_organization.return_value.get_team_by_slug.side_effect = GithubException(
            403, {"message": "Forbidden"}, None
        )
        with pytest.raises(SystemExit):
            get_team_members(g, "org", "my-team")
        out = capsys.readouterr().out
        assert "read:org" in out
        assert "403" in out

    def test_404_error_message(self, capsys):
        from github import GithubException

        g = MagicMock()
        g.get_organization.return_value.get_team_by_slug.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )
        with pytest.raises(SystemExit):
            get_team_members(g, "org", "bad-slug")
        out = capsys.readouterr().out
        assert "read:org" in out
        assert "bad-slug" in out

    def test_generic_error(self, capsys):
        g = MagicMock()
        g.get_organization.side_effect = RuntimeError("boom")
        with pytest.raises(SystemExit):
            get_team_members(g, "org", "team")


# ---------------------------------------------------------------------------
# main – env var validation
# ---------------------------------------------------------------------------

class TestMain:
    @patch.dict(os.environ, {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
        "TEAM_SLUG": "my-team",
        "DAYS_THRESHOLD": "abc",
    }, clear=True)
    def test_invalid_days_threshold(self, capsys):
        with pytest.raises(SystemExit):
            main()
        assert "numeric" in capsys.readouterr().out

    @patch.dict(os.environ, {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
    }, clear=True)
    def test_missing_team_slug(self, capsys):
        with pytest.raises(SystemExit):
            main()
        assert "TEAM_SLUG" in capsys.readouterr().out
