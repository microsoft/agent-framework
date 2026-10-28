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
    PINGED_LABEL,
    PING_COMMENT,
    TRIGGER_LABEL,
    author_replied_after,
    find_last_team_comment,
    get_maintainers,
    main,
    mark_waiting,
    ping,
    should_mark_waiting,
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
    updated_at: datetime = NOW,
) -> MagicMock:
    issue = MagicMock()
    issue.user = MagicMock()
    issue.user.login = author
    issue.number = number
    # Default to having the trigger label, since the API query pre-filters.
    if labels is None:
        labels = [TRIGGER_LABEL]
    issue.labels = [_make_label(n) for n in labels]
    issue.comments = comment_count
    issue.pull_request = MagicMock() if pull_request else None
    issue.updated_at = updated_at
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
# should_mark_waiting
# ---------------------------------------------------------------------------

class TestShouldMarkWaiting:
    def test_mark_when_latest_comment_is_from_maintainer(self):
        comments = [
            _make_comment("external", NOW - timedelta(days=2)),
            _make_comment("alice", NOW - timedelta(days=1)),
        ]
        issue = _make_issue(labels=[], comments=comments, comment_count=2)

        assert should_mark_waiting(issue, TEAM) is True

    def test_skip_maintainer_author(self):
        issue = _make_issue(
            author="alice",
            labels=[],
            comments=[_make_comment("bob", NOW)],
        )

        assert should_mark_waiting(issue, TEAM) is False
        issue.get_comments.assert_not_called()

    def test_skip_already_waiting_item(self):
        issue = _make_issue(
            comments=[_make_comment("alice", NOW)],
        )

        assert should_mark_waiting(issue, TEAM) is False
        issue.get_comments.assert_not_called()

    def test_skip_item_without_comments(self):
        issue = _make_issue(labels=[], comment_count=0)

        assert should_mark_waiting(issue, TEAM) is False
        issue.get_comments.assert_not_called()

    def test_skip_when_latest_comment_is_not_from_maintainer(self):
        comments = [
            _make_comment("alice", NOW - timedelta(days=2)),
            _make_comment("external", NOW - timedelta(days=1)),
        ]
        issue = _make_issue(labels=[], comments=comments, comment_count=2)

        assert should_mark_waiting(issue, TEAM) is False


# ---------------------------------------------------------------------------
# should_ping
# ---------------------------------------------------------------------------

class TestShouldPing:
    def test_skip_recently_updated_issue(self):
        issue = _make_issue(updated_at=NOW - timedelta(days=3))
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_ping_issue_updated_at_threshold(self):
        issue = _make_issue(updated_at=NOW - timedelta(days=4))
        assert should_ping(issue, TEAM, 4, NOW) is True

    def test_skip_maintainer_author(self):
        issue = _make_issue(author="alice", updated_at=NOW - timedelta(days=4))
        assert should_ping(issue, TEAM, 4, NOW) is False

    def test_skip_already_warned_issue(self):
        issue = _make_issue(
            labels=[TRIGGER_LABEL, PINGED_LABEL],
            updated_at=NOW - timedelta(days=4),
        )
        assert should_ping(issue, TEAM, 4, NOW) is False


# ---------------------------------------------------------------------------
# mark_waiting
# ---------------------------------------------------------------------------

class TestMarkWaiting:
    def test_dry_run_does_not_apply_label(self, capsys):
        issue = _make_issue(labels=[])

        assert mark_waiting(issue, dry_run=True) is True
        issue.add_to_labels.assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out


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
        issue.add_to_labels.assert_called_once_with(PINGED_LABEL)

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
# get_maintainers
# ---------------------------------------------------------------------------

class TestGetMaintainers:
    def test_fetches_and_parses_unique_python_and_dotnet_owners(self):
        repo = MagicMock()
        repo.default_branch = "feature-branch"
        codeowners = MagicMock()
        codeowners.decoded_content = b"""
/python/ @Alice @shared
/dotnet/ @BOB @Shared
/docs/ @ignored
        """
        repo.get_contents.return_value = codeowners

        assert get_maintainers(repo) == {"alice", "bob", "shared"}
        repo.get_contents.assert_called_once_with(
            ".github/CODEOWNERS",
            ref="feature-branch",
        )

    def test_rejects_directory_response(self):
        repo = MagicMock()
        repo.get_contents.return_value = [MagicMock()]

        with pytest.raises(RuntimeError, match="Expected CODEOWNERS to be a file"):
            get_maintainers(repo)

    def test_rejects_codeowners_without_matching_owners(self):
        repo = MagicMock()
        codeowners = MagicMock()
        codeowners.decoded_content = b"""
/docs/ @docs-owner
/python/** @python-owner
        """
        repo.get_contents.return_value = codeowners

        with pytest.raises(RuntimeError, match="No maintainers found in CODEOWNERS"):
            get_maintainers(repo)


# ---------------------------------------------------------------------------
# main – env var validation
# ---------------------------------------------------------------------------

class TestMain:
    @patch.dict(os.environ, {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
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
    @patch("stale_issue_pr_ping.get_maintainers", return_value=TEAM)
    @patch("stale_issue_pr_ping.Github")
    def test_scans_all_open_items_and_defers_newly_marked(
        self,
        mock_github,
        mock_get_maintainers,
        capsys,
    ):
        issue = _make_issue(
            labels=[],
            comments=[_make_comment("alice", NOW)],
        )
        repo = mock_github.return_value.get_repo.return_value
        repo.get_issues.return_value = [issue]

        main()

        mock_get_maintainers.assert_called_once_with(repo)
        repo.get_issues.assert_called_once_with(state="open")
        issue.add_to_labels.assert_called_once_with(TRIGGER_LABEL)
        issue.create_comment.assert_not_called()
        assert "marked 1, pinged 0" in capsys.readouterr().out

    @patch.dict(os.environ, {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
    }, clear=True)
    @patch("stale_issue_pr_ping.datetime")
    @patch("stale_issue_pr_ping.ping", return_value=True)
    @patch("stale_issue_pr_ping.get_maintainers", return_value=TEAM)
    @patch("stale_issue_pr_ping.Github")
    def test_existing_waiting_item_continues_to_ping_check(
        self,
        mock_github,
        mock_get_maintainers,
        mock_ping,
        mock_datetime,
    ):
        issue = _make_issue(updated_at=NOW - timedelta(days=4))
        repo = mock_github.return_value.get_repo.return_value
        repo.get_issues.return_value = [issue]
        mock_datetime.now.return_value = NOW

        main()

        mock_get_maintainers.assert_called_once_with(repo)
        issue.get_comments.assert_not_called()
        mock_ping.assert_called_once_with(issue, False)
