# Copyright (c) Microsoft. All rights reserved.

"""Tests for stale_pr_ping.py."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from github import GithubException

# Ensure the script directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from stale_pr_ping import (
    CLOSING_COMMENT,
    CLOSING_THRESHOLD_DAYS,
    DONT_CLOSE_LABEL,
    REQUESTED_INFO_LABEL,
    WARNING_COMMENT,
    WARNING_MARKER,
    WARNING_THRESHOLD_DAYS,
    clear_requested_info,
    close,
    get_latest_comment,
    get_latest_comment_with_retry,
    get_maintainers,
    get_runtime_thresholds,
    has_warning_marker,
    main,
    restore_requested_info,
    should_close,
    should_warn,
    warn,
)

MAINTAINERS = {"alice", "bob"}
NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_comment(login: str | None, body: str = "") -> MagicMock:
    comment = MagicMock()
    if login is None:
        comment.user = None
    else:
        comment.user = MagicMock()
        comment.user.login = login
    comment.body = body
    return comment


def _make_label(name: str) -> MagicMock:
    label = MagicMock()
    label.name = name
    return label


def _make_pull_request(
    author: str = "external",
    labels: list[str] | None = None,
    comments: list[MagicMock] | None = None,
    number: int = 42,
    updated_at: datetime = NOW,
) -> MagicMock:
    pull_request = MagicMock()
    pull_request.user = MagicMock()
    pull_request.user.login = author
    pull_request.number = number
    pull_request.labels = [
        _make_label(name)
        for name in (labels or [])
    ]
    pull_request.updated_at = updated_at
    issue_comments = MagicMock()
    issue_comments.reversed = iter(reversed(comments or []))
    pull_request.get_issue_comments.return_value = issue_comments
    return pull_request


def _make_warning_comment() -> MagicMock:
    return _make_comment("github-actions[bot]", WARNING_MARKER)


class TestLatestComment:
    def test_fetches_only_newest_reversed_comment_page(self):
        older_comment = _make_comment("external")
        latest_comment = _make_comment("alice")
        pull_request = _make_pull_request(
            comments=[older_comment, latest_comment],
        )
        issue_comments = pull_request.get_issue_comments.return_value
        issue_comments.__iter__.side_effect = AssertionError(
            "forward history should not be fetched"
        )

        assert get_latest_comment(pull_request) is latest_comment
        pull_request.get_issue_comments.assert_called_once_with()

    def test_returns_none_without_comments(self):
        pull_request = _make_pull_request()

        assert get_latest_comment(pull_request) is None

    @patch("stale_pr_ping.time.sleep")
    def test_transient_lookup_failure_succeeds_on_retry(
        self,
        mock_sleep,
        capsys,
    ):
        latest_comment = _make_comment("alice")
        pull_request = _make_pull_request(comments=[latest_comment])
        issue_comments = pull_request.get_issue_comments.return_value
        pull_request.get_issue_comments.side_effect = [
            GithubException(502, {"message": "Bad Gateway"}, None),
            issue_comments,
        ]

        assert get_latest_comment_with_retry(pull_request) == (
            True,
            latest_comment,
        )
        assert pull_request.get_issue_comments.call_count == 2
        mock_sleep.assert_called_once_with(2)
        assert "lookup attempt 1/3 failed for PR #42" in capsys.readouterr().out

    @patch("stale_pr_ping.time.sleep")
    def test_final_lookup_failure_is_reported(
        self,
        mock_sleep,
        capsys,
    ):
        pull_request = _make_pull_request()
        pull_request.get_issue_comments.side_effect = GithubException(
            502,
            {"message": "Bad Gateway"},
            None,
        )

        assert get_latest_comment_with_retry(pull_request) == (False, None)
        assert pull_request.get_issue_comments.call_count == 3
        assert mock_sleep.call_args_list == [call(2), call(4)]
        assert (
            "Failed to fetch the latest comment for PR #42 after 3 attempts"
            in capsys.readouterr().out
        )


class TestWarningMarker:
    def test_detects_warning_marker(self):
        assert has_warning_marker(_make_warning_comment()) is True

    def test_rejects_regular_or_missing_comment(self):
        assert has_warning_marker(_make_comment("alice", "regular comment")) is False
        assert has_warning_marker(None) is False


class TestPolicyThresholds:
    def test_default_constants(self):
        assert WARNING_THRESHOLD_DAYS == 4
        assert CLOSING_THRESHOLD_DAYS == 4

    @patch.dict(os.environ, {}, clear=True)
    def test_runtime_defaults(self):
        assert get_runtime_thresholds() == (4, 4)

    @patch.dict(os.environ, {"DAYS_THRESHOLD": "7"}, clear=True)
    def test_runtime_override_applies_to_both_stages(self):
        assert get_runtime_thresholds() == (7, 7)

    @patch.dict(os.environ, {"DAYS_THRESHOLD": "0"}, clear=True)
    def test_zero_threshold_is_valid(self):
        assert get_runtime_thresholds() == (0, 0)

    @patch.dict(os.environ, {"DAYS_THRESHOLD": "invalid"}, clear=True)
    def test_invalid_runtime_override_is_rejected(self, capsys):
        with pytest.raises(SystemExit):
            get_runtime_thresholds()

        assert "non-negative integer" in capsys.readouterr().out

    @patch.dict(os.environ, {"DAYS_THRESHOLD": "-1"}, clear=True)
    def test_negative_runtime_override_is_rejected(self, capsys):
        with pytest.raises(SystemExit):
            get_runtime_thresholds()

        assert "non-negative integer" in capsys.readouterr().out


class TestShouldWarn:
    def test_warns_at_threshold_for_latest_maintainer_comment(self):
        latest_comment = _make_comment("alice")
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=4),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            MAINTAINERS,
            NOW,
            4,
        ) is True

    def test_recent_activity_resets_warning_clock(self):
        latest_comment = _make_comment("alice")
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=3),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_maintainer_authored_pr_is_exempt(self):
        latest_comment = _make_comment("bob")
        pull_request = _make_pull_request(
            author="Alice",
            updated_at=NOW - timedelta(days=4),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_requested_info_pr_is_not_warned_again(self):
        latest_comment = _make_comment("alice")
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=4),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_dont_close_pr_is_not_warned(self):
        latest_comment = _make_comment("alice")
        pull_request = _make_pull_request(
            labels=[DONT_CLOSE_LABEL],
            updated_at=NOW - timedelta(days=4),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_pr_without_regular_conversation_comments_is_skipped(self):
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=4),
        )

        assert should_warn(
            pull_request,
            None,
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_latest_external_comment_is_skipped(self):
        latest_comment = _make_comment("external")
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=4),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_deleted_latest_comment_author_is_skipped(self):
        latest_comment = _make_comment(None)
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=4),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            MAINTAINERS,
            NOW,
            4,
        ) is False


class TestWarn:
    def test_dry_run_mutates_nothing(self, capsys):
        pull_request = _make_pull_request()

        assert warn(pull_request, dry_run=True, closing_threshold_days=6) is True
        pull_request.create_issue_comment.assert_not_called()
        pull_request.add_to_labels.assert_not_called()
        output = capsys.readouterr().out
        assert "DRY RUN" in output
        assert REQUESTED_INFO_LABEL in output

    def test_posts_warning_then_applies_requested_info(self):
        pull_request = _make_pull_request()

        assert warn(pull_request, dry_run=False, closing_threshold_days=6) is True
        assert pull_request.method_calls == [
            call.create_issue_comment(
                WARNING_COMMENT.format(
                    author="external",
                    closing_days=6,
                )
            ),
            call.add_to_labels(REQUESTED_INFO_LABEL),
        ]

    @patch("stale_pr_ping.time.sleep")
    def test_comment_retry_succeeds(self, mock_sleep):
        pull_request = _make_pull_request()
        pull_request.create_issue_comment.side_effect = [
            Exception("network error"),
            None,
        ]

        assert warn(pull_request, dry_run=False, closing_threshold_days=4) is True
        assert pull_request.create_issue_comment.call_count == 2
        pull_request.add_to_labels.assert_called_once_with(REQUESTED_INFO_LABEL)
        mock_sleep.assert_called_once()

    @patch("stale_pr_ping.time.sleep")
    def test_label_retry_does_not_repeat_warning(self, mock_sleep):
        pull_request = _make_pull_request()
        pull_request.add_to_labels.side_effect = [
            Exception("label error"),
            None,
        ]

        assert warn(pull_request, dry_run=False, closing_threshold_days=4) is True
        pull_request.create_issue_comment.assert_called_once()
        assert pull_request.add_to_labels.call_count == 2
        mock_sleep.assert_called_once()

    @patch("stale_pr_ping.time.sleep")
    def test_warning_failure_never_applies_label(self, mock_sleep):
        pull_request = _make_pull_request()
        pull_request.create_issue_comment.side_effect = Exception("comment error")

        assert warn(pull_request, dry_run=False, closing_threshold_days=4) is False
        assert pull_request.create_issue_comment.call_count == 3
        pull_request.add_to_labels.assert_not_called()

    @patch("stale_pr_ping.time.sleep")
    def test_final_label_failure_reports_failure_without_repeating_warning(
        self,
        mock_sleep,
    ):
        pull_request = _make_pull_request()
        pull_request.add_to_labels.side_effect = Exception("label error")

        assert warn(pull_request, dry_run=False, closing_threshold_days=4) is False
        pull_request.create_issue_comment.assert_called_once()
        assert pull_request.add_to_labels.call_count == 3
        assert mock_sleep.call_count == 2


class TestShouldClose:
    def test_closes_requested_info_pr_at_threshold(self):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=4),
        )

        assert should_close(
            pull_request,
            _make_warning_comment(),
            MAINTAINERS,
            NOW,
            4,
        ) is True

    def test_recent_activity_resets_closing_clock(self):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=3),
        )

        assert should_close(
            pull_request,
            _make_warning_comment(),
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_maintainer_authored_pr_is_exempt(self):
        pull_request = _make_pull_request(
            author="Alice",
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=4),
        )

        assert should_close(
            pull_request,
            _make_warning_comment(),
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_unlabeled_pr_is_not_closed(self):
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=4),
        )

        assert should_close(
            pull_request,
            _make_warning_comment(),
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_dont_close_pr_is_not_closed(self):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL, DONT_CLOSE_LABEL],
            updated_at=NOW - timedelta(days=4),
        )

        assert should_close(
            pull_request,
            _make_warning_comment(),
            MAINTAINERS,
            NOW,
            4,
        ) is False

    def test_manual_requested_info_without_marker_is_not_closed(self):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=4),
        )

        assert should_close(
            pull_request,
            _make_comment("alice", "manual comment"),
            MAINTAINERS,
            NOW,
            4,
        ) is False


class TestRequestedInfoRecovery:
    def test_clear_requested_info(self):
        pull_request = _make_pull_request(labels=[REQUESTED_INFO_LABEL])

        assert clear_requested_info(pull_request, dry_run=False) is True
        pull_request.remove_from_labels.assert_called_once_with(
            REQUESTED_INFO_LABEL
        )

    def test_clear_requested_info_dry_run_mutates_nothing(self, capsys):
        pull_request = _make_pull_request(labels=[REQUESTED_INFO_LABEL])

        assert clear_requested_info(pull_request, dry_run=True) is True
        pull_request.remove_from_labels.assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out

    def test_clear_requested_info_failure_is_explicit(self, capsys):
        pull_request = _make_pull_request(labels=[REQUESTED_INFO_LABEL])
        pull_request.remove_from_labels.side_effect = Exception("remove error")

        assert clear_requested_info(pull_request, dry_run=False) is False
        assert "ERROR" in capsys.readouterr().out

    def test_restore_requested_info_without_reposting_warning(self):
        pull_request = _make_pull_request()

        assert restore_requested_info(pull_request, dry_run=False) is True
        pull_request.add_to_labels.assert_called_once_with(REQUESTED_INFO_LABEL)
        pull_request.create_issue_comment.assert_not_called()

    def test_restore_requested_info_dry_run_mutates_nothing(self, capsys):
        pull_request = _make_pull_request()

        assert restore_requested_info(pull_request, dry_run=True) is True
        pull_request.add_to_labels.assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out

    def test_restore_requested_info_failure_is_explicit(self, capsys):
        pull_request = _make_pull_request()
        pull_request.add_to_labels.side_effect = Exception("label error")

        assert restore_requested_info(pull_request, dry_run=False) is False
        assert "ERROR" in capsys.readouterr().out


class TestClose:
    def test_dry_run_mutates_nothing(self, capsys):
        pull_request = _make_pull_request()

        assert close(pull_request, dry_run=True) is True
        pull_request.create_issue_comment.assert_not_called()
        pull_request.edit.assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out

    def test_posts_closing_comment_then_closes_pr(self):
        pull_request = _make_pull_request()

        assert close(pull_request, dry_run=False) is True
        assert pull_request.method_calls == [
            call.create_issue_comment(CLOSING_COMMENT),
            call.edit(state="closed"),
        ]

    @patch("stale_pr_ping.time.sleep")
    def test_close_retry_does_not_repeat_comment(self, mock_sleep):
        pull_request = _make_pull_request()
        pull_request.edit.side_effect = [Exception("close error"), None]

        assert close(pull_request, dry_run=False) is True
        pull_request.create_issue_comment.assert_called_once_with(CLOSING_COMMENT)
        assert pull_request.edit.call_count == 2
        mock_sleep.assert_called_once()

    @patch("stale_pr_ping.time.sleep")
    def test_comment_failure_never_closes_pr(self, mock_sleep):
        pull_request = _make_pull_request()
        pull_request.create_issue_comment.side_effect = Exception("comment error")

        assert close(pull_request, dry_run=False) is False
        assert pull_request.create_issue_comment.call_count == 3
        pull_request.edit.assert_not_called()

    @patch("stale_pr_ping.time.sleep")
    def test_final_close_failure_reports_failure_without_repeating_comment(
        self,
        mock_sleep,
    ):
        pull_request = _make_pull_request()
        pull_request.edit.side_effect = Exception("close error")

        assert close(pull_request, dry_run=False) is False
        pull_request.create_issue_comment.assert_called_once_with(CLOSING_COMMENT)
        assert pull_request.edit.call_count == 3
        assert mock_sleep.call_count == 2


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

    def test_propagates_codeowners_fetch_failure(self):
        repo = MagicMock()
        error = GithubException(404, {"message": "Not Found"}, None)
        repo.get_contents.side_effect = error

        with pytest.raises(GithubException) as exc_info:
            get_maintainers(repo)

        assert exc_info.value is error


class TestMain:
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_github_token(self, capsys):
        with pytest.raises(SystemExit):
            main()

        assert "GITHUB_TOKEN" in capsys.readouterr().out

    @patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}, clear=True)
    def test_missing_github_repository(self, capsys):
        with pytest.raises(SystemExit):
            main()

        assert "GITHUB_REPOSITORY" in capsys.readouterr().out

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
            "DAYS_THRESHOLD": "invalid",
        },
        clear=True,
    )
    @patch("stale_pr_ping.Github")
    def test_invalid_days_threshold_stops_before_github(self, mock_github, capsys):
        with pytest.raises(SystemExit):
            main()

        mock_github.assert_not_called()
        assert "non-negative integer" in capsys.readouterr().out

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
            "DAYS_THRESHOLD": "7",
        },
        clear=True,
    )
    @patch("stale_pr_ping.datetime")
    @patch("stale_pr_ping.get_maintainers", return_value=MAINTAINERS)
    @patch("stale_pr_ping.Github")
    def test_scans_only_open_prs_and_defers_new_warning(
        self,
        mock_github,
        mock_get_maintainers,
        mock_datetime,
        capsys,
    ):
        pull_request = _make_pull_request(
            comments=[_make_comment("alice")],
            updated_at=NOW - timedelta(days=7),
        )
        repo = mock_github.return_value.get_repo.return_value
        repo.get_pulls.return_value = [pull_request]
        mock_datetime.now.return_value = NOW

        main()

        mock_get_maintainers.assert_called_once_with(repo)
        repo.get_pulls.assert_called_once_with(state="open")
        repo.get_issues.assert_not_called()
        pull_request.create_issue_comment.assert_called_once_with(
            WARNING_COMMENT.format(
                author="external",
                closing_days=7,
            )
        )
        pull_request.add_to_labels.assert_called_once_with(REQUESTED_INFO_LABEL)
        pull_request.edit.assert_not_called()
        assert "Scanned 1 PRs, warned 1, closed 0" in capsys.readouterr().out

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
            "DAYS_THRESHOLD": "7",
        },
        clear=True,
    )
    @patch("stale_pr_ping.datetime")
    @patch("stale_pr_ping.get_maintainers", return_value=MAINTAINERS)
    @patch("stale_pr_ping.Github")
    def test_existing_requested_info_pr_closes_before_warning_check(
        self,
        mock_github,
        mock_get_maintainers,
        mock_datetime,
        capsys,
    ):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            comments=[_make_warning_comment()],
            updated_at=NOW - timedelta(days=7),
        )
        repo = mock_github.return_value.get_repo.return_value
        materialized = {"complete": False}

        def pull_requests():
            yield pull_request
            materialized["complete"] = True

        def assert_materialized(**kwargs):
            assert materialized["complete"] is True
            assert kwargs == {"state": "closed"}

        repo.get_pulls.return_value = pull_requests()
        pull_request.edit.side_effect = assert_materialized
        mock_datetime.now.return_value = NOW

        main()

        mock_get_maintainers.assert_called_once_with(repo)
        pull_request.get_issue_comments.assert_called_once_with()
        pull_request.create_issue_comment.assert_called_once_with(CLOSING_COMMENT)
        pull_request.edit.assert_called_once_with(state="closed")
        output = capsys.readouterr().out
        assert "Scanned 1 PRs, warned 0, closed 1, failed 0" in output
        assert "Closed: #42" in output

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
        },
        clear=True,
    )
    @patch("stale_pr_ping.datetime")
    @patch("stale_pr_ping.get_maintainers", return_value=MAINTAINERS)
    @patch("stale_pr_ping.Github")
    def test_manual_requested_info_is_cleared_instead_of_closed(
        self,
        mock_github,
        mock_get_maintainers,
        mock_datetime,
    ):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            comments=[_make_comment("external", "author update")],
            updated_at=NOW - timedelta(days=CLOSING_THRESHOLD_DAYS),
        )
        repo = mock_github.return_value.get_repo.return_value
        repo.get_pulls.return_value = [pull_request]
        mock_datetime.now.return_value = NOW

        main()

        mock_get_maintainers.assert_called_once_with(repo)
        pull_request.remove_from_labels.assert_called_once_with(
            REQUESTED_INFO_LABEL
        )
        pull_request.create_issue_comment.assert_not_called()
        pull_request.edit.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
        },
        clear=True,
    )
    @patch("stale_pr_ping.datetime")
    @patch("stale_pr_ping.get_maintainers", return_value=MAINTAINERS)
    @patch("stale_pr_ping.Github")
    def test_warning_marker_restores_missing_label_without_reposting(
        self,
        mock_github,
        mock_get_maintainers,
        mock_datetime,
    ):
        pull_request = _make_pull_request(
            comments=[_make_warning_comment()],
            updated_at=NOW - timedelta(days=CLOSING_THRESHOLD_DAYS),
        )
        repo = mock_github.return_value.get_repo.return_value
        repo.get_pulls.return_value = [pull_request]
        mock_datetime.now.return_value = NOW

        main()

        mock_get_maintainers.assert_called_once_with(repo)
        pull_request.add_to_labels.assert_called_once_with(REQUESTED_INFO_LABEL)
        pull_request.create_issue_comment.assert_not_called()
        pull_request.edit.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
            "DRY_RUN": "true",
        },
        clear=True,
    )
    @patch("stale_pr_ping.datetime")
    @patch("stale_pr_ping.get_maintainers", return_value=MAINTAINERS)
    @patch("stale_pr_ping.Github")
    def test_recovery_dry_run_mutates_nothing(
        self,
        mock_github,
        mock_get_maintainers,
        mock_datetime,
    ):
        manual_label = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            comments=[_make_comment("external", "author update")],
            number=41,
        )
        missing_label = _make_pull_request(
            comments=[_make_warning_comment()],
            number=42,
        )
        repo = mock_github.return_value.get_repo.return_value
        repo.get_pulls.return_value = [manual_label, missing_label]
        mock_datetime.now.return_value = NOW

        main()

        mock_get_maintainers.assert_called_once_with(repo)
        manual_label.remove_from_labels.assert_not_called()
        missing_label.add_to_labels.assert_not_called()
        manual_label.edit.assert_not_called()
        missing_label.edit.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
        },
        clear=True,
    )
    @patch("stale_pr_ping.datetime")
    @patch("stale_pr_ping.warn", return_value=False)
    @patch("stale_pr_ping.get_maintainers", return_value=MAINTAINERS)
    @patch("stale_pr_ping.Github")
    def test_failed_warning_is_reported_and_exits(
        self,
        mock_github,
        mock_get_maintainers,
        mock_warn,
        mock_datetime,
        capsys,
    ):
        pull_request = _make_pull_request(
            comments=[_make_comment("alice")],
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS),
        )
        repo = mock_github.return_value.get_repo.return_value
        repo.get_pulls.return_value = [pull_request]
        mock_datetime.now.return_value = NOW

        with pytest.raises(SystemExit):
            main()

        mock_get_maintainers.assert_called_once_with(repo)
        mock_warn.assert_called_once_with(
            pull_request,
            False,
            CLOSING_THRESHOLD_DAYS,
        )
        output = capsys.readouterr().out
        assert "Scanned 1 PRs, warned 0, closed 0, failed 1" in output
        assert "Failed: #42" in output

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "tok",
            "GITHUB_REPOSITORY": "org/repo",
        },
        clear=True,
    )
    @patch("stale_pr_ping.time.sleep")
    @patch("stale_pr_ping.datetime")
    @patch("stale_pr_ping.get_maintainers", return_value=MAINTAINERS)
    @patch("stale_pr_ping.Github")
    def test_lookup_failure_is_recorded_and_later_pr_is_processed(
        self,
        mock_github,
        mock_get_maintainers,
        mock_datetime,
        mock_sleep,
        capsys,
    ):
        failed_pull_request = _make_pull_request(number=41)
        failed_pull_request.get_issue_comments.side_effect = GithubException(
            502,
            {"message": "Bad Gateway"},
            None,
        )
        later_pull_request = _make_pull_request(
            comments=[_make_comment("alice")],
            number=42,
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS),
        )
        repo = mock_github.return_value.get_repo.return_value
        repo.get_pulls.return_value = [
            failed_pull_request,
            later_pull_request,
        ]
        mock_datetime.now.return_value = NOW

        with pytest.raises(SystemExit):
            main()

        mock_get_maintainers.assert_called_once_with(repo)
        assert failed_pull_request.get_issue_comments.call_count == 3
        assert mock_sleep.call_args_list == [call(2), call(4)]
        later_pull_request.create_issue_comment.assert_called_once_with(
            WARNING_COMMENT.format(
                author="external",
                closing_days=CLOSING_THRESHOLD_DAYS,
            )
        )
        later_pull_request.add_to_labels.assert_called_once_with(
            REQUESTED_INFO_LABEL
        )
        output = capsys.readouterr().out
        assert "Scanned 2 PRs, warned 1, closed 0, failed 1" in output
        assert "Warned: #42" in output
        assert "Failed: #41" in output
