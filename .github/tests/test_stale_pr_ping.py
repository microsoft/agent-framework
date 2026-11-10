# Copyright (c) Microsoft. All rights reserved.

"""Tests for stale_pr_ping.py."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from github import GithubException

# Ensure the script directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import stale_pr_ping
from stale_pr_ping import (
    CLOSING_COMMENT,
    CLOSING_THRESHOLD_DAYS,
    DONT_CLOSE_LABEL,
    MEMBER_ASSOCIATION,
    REQUESTED_INFO_LABEL,
    WARNING_COMMENT,
    WARNING_MARKER,
    WARNING_THRESHOLD_DAYS,
    clear_requested_info,
    close,
    get_latest_comment,
    get_latest_comment_with_retry,
    get_runtime_thresholds,
    has_warning_marker,
    is_exempt,
    main,
    restore_requested_info,
    should_close,
    should_warn,
    warn,
)

NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_comment(
    login: str | None = "external",
    body: str = "",
    author_association: str = "CONTRIBUTOR",
) -> MagicMock:
    comment = MagicMock()
    comment.user = None if login is None else MagicMock(login=login)
    comment.body = body
    comment.author_association = author_association
    return comment


def _member_comment(login: str = "member") -> MagicMock:
    return _make_comment(login, author_association=MEMBER_ASSOCIATION)


def _warning_comment() -> MagicMock:
    return _make_comment("github-actions[bot]", WARNING_MARKER)


def _make_pull_request(
    author: str = "external",
    author_association: str = "CONTRIBUTOR",
    labels: list[str] | None = None,
    comments: list[MagicMock] | None = None,
    number: int = 42,
    updated_at: datetime = NOW,
) -> MagicMock:
    pull_request = MagicMock()
    pull_request.user = MagicMock(login=author)
    pull_request.author_association = author_association
    pull_request.number = number
    pull_request.labels = [
        SimpleNamespace(name=name)
        for name in (labels or [])
    ]
    pull_request.updated_at = updated_at
    issue_comments = MagicMock()
    issue_comments.reversed = iter(reversed(comments or []))
    pull_request.get_issue_comments.return_value = issue_comments
    return pull_request


@pytest.fixture
def main_context(monkeypatch):
    github = MagicMock()
    repo = github.return_value.get_repo.return_value
    mock_datetime = MagicMock()
    mock_datetime.now.return_value = NOW
    monkeypatch.setattr(stale_pr_ping, "Github", github)
    monkeypatch.setattr(stale_pr_ping, "datetime", mock_datetime)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.delenv("DAYS_THRESHOLD", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    return SimpleNamespace(
        github=github,
        repo=repo,
        datetime=mock_datetime,
    )


class TestLatestComment:
    def test_fetches_only_newest_reversed_comment_page(self):
        latest_comment = _member_comment()
        pull_request = _make_pull_request(
            comments=[_make_comment(), latest_comment],
        )
        issue_comments = pull_request.get_issue_comments.return_value
        issue_comments.__iter__.side_effect = AssertionError(
            "forward history should not be fetched"
        )

        assert get_latest_comment(pull_request) is latest_comment
        pull_request.get_issue_comments.assert_called_once_with()

    def test_returns_none_without_comments(self):
        assert get_latest_comment(_make_pull_request()) is None

    @patch("stale_pr_ping.time.sleep")
    def test_transient_lookup_failure_succeeds_on_retry(
        self,
        mock_sleep,
        capsys,
    ):
        latest_comment = _member_comment()
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


class TestPolicy:
    @pytest.mark.parametrize(
        ("association", "labels", "expected"),
        [
            (MEMBER_ASSOCIATION, [], True),
            ("OWNER", [], False),
            ("COLLABORATOR", [], False),
            ("CONTRIBUTOR", [], False),
            ("CONTRIBUTOR", [DONT_CLOSE_LABEL], True),
        ],
    )
    def test_exemptions(self, association, labels, expected):
        pull_request = _make_pull_request(
            author_association=association,
            labels=labels,
        )

        assert is_exempt(pull_request) is expected

    @pytest.mark.parametrize(
        ("comment", "expected"),
        [
            (_warning_comment(), True),
            (_make_comment(body="regular comment"), False),
            (None, False),
        ],
    )
    def test_warning_marker(self, comment, expected):
        assert has_warning_marker(comment) is expected

    def test_warns_at_threshold_for_latest_member_comment(self):
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS),
        )

        assert should_warn(
            pull_request,
            _member_comment(),
            NOW,
            WARNING_THRESHOLD_DAYS,
        ) is True

    def test_recent_activity_resets_warning_clock(self):
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS - 1),
        )

        assert should_warn(
            pull_request,
            _member_comment(),
            NOW,
            WARNING_THRESHOLD_DAYS,
        ) is False

    def test_requested_info_pr_is_not_warned_again(self):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS),
        )

        assert should_warn(
            pull_request,
            _member_comment(),
            NOW,
            WARNING_THRESHOLD_DAYS,
        ) is False

    @pytest.mark.parametrize(
        "latest_comment",
        [
            None,
            _make_comment(author_association="OWNER"),
            _make_comment(author_association="COLLABORATOR"),
            _make_comment(author_association="CONTRIBUTOR"),
            _make_comment(None, author_association="NONE"),
        ],
    )
    def test_non_member_or_missing_latest_comment_is_skipped(
        self,
        latest_comment,
    ):
        pull_request = _make_pull_request(
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS),
        )

        assert should_warn(
            pull_request,
            latest_comment,
            NOW,
            WARNING_THRESHOLD_DAYS,
        ) is False

    def test_closes_requested_info_pr_at_threshold(self):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=CLOSING_THRESHOLD_DAYS),
        )

        assert should_close(
            pull_request,
            _warning_comment(),
            NOW,
            CLOSING_THRESHOLD_DAYS,
        ) is True

    def test_recent_activity_resets_closing_clock(self):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            updated_at=NOW - timedelta(days=CLOSING_THRESHOLD_DAYS - 1),
        )

        assert should_close(
            pull_request,
            _warning_comment(),
            NOW,
            CLOSING_THRESHOLD_DAYS,
        ) is False

    @pytest.mark.parametrize(
        ("labels", "comment"),
        [
            ([], _warning_comment()),
            ([REQUESTED_INFO_LABEL], _make_comment(body="manual comment")),
        ],
    )
    def test_closing_requires_label_and_warning_marker(self, labels, comment):
        pull_request = _make_pull_request(
            labels=labels,
            updated_at=NOW - timedelta(days=CLOSING_THRESHOLD_DAYS),
        )

        assert should_close(
            pull_request,
            comment,
            NOW,
            CLOSING_THRESHOLD_DAYS,
        ) is False


class TestThresholds:
    def test_default_constants(self):
        assert WARNING_THRESHOLD_DAYS == 4
        assert CLOSING_THRESHOLD_DAYS == 4

    @pytest.mark.parametrize(
        ("environment", "expected"),
        [
            ({}, (4, 4)),
            ({"DAYS_THRESHOLD": "7"}, (7, 7)),
            ({"DAYS_THRESHOLD": "0"}, (0, 0)),
        ],
    )
    def test_runtime_thresholds(self, environment, expected):
        with patch.dict(os.environ, environment, clear=True):
            assert get_runtime_thresholds() == expected

    @pytest.mark.parametrize("value", ["invalid", "-1"])
    def test_invalid_runtime_override_is_rejected(self, value, capsys):
        with patch.dict(
            os.environ,
            {"DAYS_THRESHOLD": value},
            clear=True,
        ), pytest.raises(SystemExit):
            get_runtime_thresholds()

        assert "non-negative integer" in capsys.readouterr().out


class TestWarn:
    def test_dry_run_mutates_nothing(self, capsys):
        pull_request = _make_pull_request()

        assert warn(pull_request, dry_run=True, closing_threshold_days=6) is True
        pull_request.create_issue_comment.assert_not_called()
        pull_request.add_to_labels.assert_not_called()
        assert REQUESTED_INFO_LABEL in capsys.readouterr().out

    def test_posts_warning_before_applying_label(self):
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
        mock_sleep.assert_called_once_with(2)

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
        mock_sleep.assert_called_once_with(2)

    @pytest.mark.parametrize("failure_stage", ["comment", "label"])
    @patch("stale_pr_ping.time.sleep")
    def test_final_failure_preserves_partial_state(
        self,
        mock_sleep,
        failure_stage,
    ):
        pull_request = _make_pull_request()
        if failure_stage == "comment":
            pull_request.create_issue_comment.side_effect = Exception("comment")
        else:
            pull_request.add_to_labels.side_effect = Exception("label")

        assert warn(pull_request, dry_run=False, closing_threshold_days=4) is False
        assert mock_sleep.call_args_list == [call(2), call(4)]
        if failure_stage == "comment":
            assert pull_request.create_issue_comment.call_count == 3
            pull_request.add_to_labels.assert_not_called()
        else:
            pull_request.create_issue_comment.assert_called_once()
            assert pull_request.add_to_labels.call_count == 3


class TestRequestedInfoRecovery:
    @pytest.mark.parametrize(
        ("function", "method_name", "label"),
        [
            (clear_requested_info, "remove_from_labels", REQUESTED_INFO_LABEL),
            (restore_requested_info, "add_to_labels", REQUESTED_INFO_LABEL),
        ],
    )
    def test_updates_requested_info(self, function, method_name, label):
        pull_request = _make_pull_request(labels=[REQUESTED_INFO_LABEL])

        assert function(pull_request, dry_run=False) is True
        getattr(pull_request, method_name).assert_called_once_with(label)

    @pytest.mark.parametrize(
        ("function", "method_name"),
        [
            (clear_requested_info, "remove_from_labels"),
            (restore_requested_info, "add_to_labels"),
        ],
    )
    def test_dry_run_mutates_nothing(
        self,
        function,
        method_name,
        capsys,
    ):
        pull_request = _make_pull_request(labels=[REQUESTED_INFO_LABEL])

        assert function(pull_request, dry_run=True) is True
        getattr(pull_request, method_name).assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("function", "method_name"),
        [
            (clear_requested_info, "remove_from_labels"),
            (restore_requested_info, "add_to_labels"),
        ],
    )
    def test_failure_is_explicit(
        self,
        function,
        method_name,
        capsys,
    ):
        pull_request = _make_pull_request(labels=[REQUESTED_INFO_LABEL])
        getattr(pull_request, method_name).side_effect = Exception("failure")

        assert function(pull_request, dry_run=False) is False
        assert "ERROR" in capsys.readouterr().out

    def test_restore_does_not_repeat_warning(self):
        pull_request = _make_pull_request()

        assert restore_requested_info(pull_request, dry_run=False) is True
        pull_request.create_issue_comment.assert_not_called()


class TestClose:
    def test_dry_run_mutates_nothing(self, capsys):
        pull_request = _make_pull_request()

        assert close(pull_request, dry_run=True) is True
        pull_request.create_issue_comment.assert_not_called()
        pull_request.edit.assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out

    def test_posts_comment_before_closing(self):
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
        mock_sleep.assert_called_once_with(2)

    @pytest.mark.parametrize("failure_stage", ["comment", "close"])
    @patch("stale_pr_ping.time.sleep")
    def test_final_failure_preserves_partial_state(
        self,
        mock_sleep,
        failure_stage,
    ):
        pull_request = _make_pull_request()
        if failure_stage == "comment":
            pull_request.create_issue_comment.side_effect = Exception("comment")
        else:
            pull_request.edit.side_effect = Exception("close")

        assert close(pull_request, dry_run=False) is False
        assert mock_sleep.call_args_list == [call(2), call(4)]
        if failure_stage == "comment":
            assert pull_request.create_issue_comment.call_count == 3
            pull_request.edit.assert_not_called()
        else:
            pull_request.create_issue_comment.assert_called_once()
            assert pull_request.edit.call_count == 3


class TestMain:
    @pytest.mark.parametrize(
        ("environment", "message"),
        [
            ({}, "GITHUB_TOKEN"),
            ({"GITHUB_TOKEN": "tok"}, "GITHUB_REPOSITORY"),
        ],
    )
    def test_required_environment(self, environment, message, capsys):
        with patch.dict(os.environ, environment, clear=True), pytest.raises(
            SystemExit
        ):
            main()

        assert message in capsys.readouterr().out

    def test_invalid_threshold_stops_before_github(
        self,
        main_context,
        monkeypatch,
        capsys,
    ):
        monkeypatch.setenv("DAYS_THRESHOLD", "invalid")

        with pytest.raises(SystemExit):
            main()

        main_context.github.assert_not_called()
        assert "non-negative integer" in capsys.readouterr().out

    def test_scans_only_open_prs_and_warns(
        self,
        main_context,
        monkeypatch,
        capsys,
    ):
        monkeypatch.setenv("DAYS_THRESHOLD", "7")
        pull_request = _make_pull_request(
            comments=[_member_comment()],
            updated_at=NOW - timedelta(days=7),
        )
        main_context.repo.get_pulls.return_value = [pull_request]

        main()

        main_context.repo.get_pulls.assert_called_once_with(state="open")
        main_context.repo.get_issues.assert_not_called()
        pull_request.create_issue_comment.assert_called_once_with(
            WARNING_COMMENT.format(author="external", closing_days=7)
        )
        pull_request.add_to_labels.assert_called_once_with(REQUESTED_INFO_LABEL)
        pull_request.edit.assert_not_called()
        assert "Scanned 1 PRs, warned 1, closed 0" in capsys.readouterr().out

    def test_materializes_prs_before_closing(
        self,
        main_context,
        monkeypatch,
        capsys,
    ):
        monkeypatch.setenv("DAYS_THRESHOLD", "7")
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            comments=[_warning_comment()],
            updated_at=NOW - timedelta(days=7),
        )
        materialized = {"complete": False}

        def pull_requests():
            yield pull_request
            materialized["complete"] = True

        def assert_materialized(**kwargs):
            assert materialized["complete"] is True
            assert kwargs == {"state": "closed"}

        main_context.repo.get_pulls.return_value = pull_requests()
        pull_request.edit.side_effect = assert_materialized

        main()

        pull_request.create_issue_comment.assert_called_once_with(CLOSING_COMMENT)
        pull_request.edit.assert_called_once_with(state="closed")
        output = capsys.readouterr().out
        assert "Scanned 1 PRs, warned 0, closed 1, failed 0" in output
        assert "Closed: #42" in output

    def test_clears_manual_or_post_warning_state(self, main_context):
        pull_request = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            comments=[_make_comment(body="author update")],
            updated_at=NOW - timedelta(days=CLOSING_THRESHOLD_DAYS),
        )
        main_context.repo.get_pulls.return_value = [pull_request]

        main()

        pull_request.remove_from_labels.assert_called_once_with(
            REQUESTED_INFO_LABEL
        )
        pull_request.create_issue_comment.assert_not_called()
        pull_request.edit.assert_not_called()

    def test_restores_missing_label_without_reposting(self, main_context):
        pull_request = _make_pull_request(
            comments=[_warning_comment()],
            updated_at=NOW - timedelta(days=CLOSING_THRESHOLD_DAYS),
        )
        main_context.repo.get_pulls.return_value = [pull_request]

        main()

        pull_request.add_to_labels.assert_called_once_with(REQUESTED_INFO_LABEL)
        pull_request.create_issue_comment.assert_not_called()
        pull_request.edit.assert_not_called()

    def test_recovery_dry_run_mutates_nothing(
        self,
        main_context,
        monkeypatch,
    ):
        monkeypatch.setenv("DRY_RUN", "true")
        manual_label = _make_pull_request(
            labels=[REQUESTED_INFO_LABEL],
            comments=[_make_comment(body="author update")],
            number=41,
        )
        missing_label = _make_pull_request(
            comments=[_warning_comment()],
            number=42,
        )
        main_context.repo.get_pulls.return_value = [
            manual_label,
            missing_label,
        ]

        main()

        manual_label.remove_from_labels.assert_not_called()
        missing_label.add_to_labels.assert_not_called()
        manual_label.edit.assert_not_called()
        missing_label.edit.assert_not_called()

    def test_failed_warning_is_reported_and_exits(
        self,
        main_context,
        monkeypatch,
        capsys,
    ):
        pull_request = _make_pull_request(
            comments=[_member_comment()],
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS),
        )
        main_context.repo.get_pulls.return_value = [pull_request]
        mock_warn = MagicMock(return_value=False)
        monkeypatch.setattr(stale_pr_ping, "warn", mock_warn)

        with pytest.raises(SystemExit):
            main()

        mock_warn.assert_called_once_with(
            pull_request,
            False,
            CLOSING_THRESHOLD_DAYS,
        )
        output = capsys.readouterr().out
        assert "Scanned 1 PRs, warned 0, closed 0, failed 1" in output
        assert "Failed: #42" in output

    def test_lookup_failure_does_not_block_later_pr(
        self,
        main_context,
        monkeypatch,
        capsys,
    ):
        failed_pull_request = _make_pull_request(number=41)
        failed_pull_request.get_issue_comments.side_effect = GithubException(
            502,
            {"message": "Bad Gateway"},
            None,
        )
        later_pull_request = _make_pull_request(
            comments=[_member_comment()],
            number=42,
            updated_at=NOW - timedelta(days=WARNING_THRESHOLD_DAYS),
        )
        main_context.repo.get_pulls.return_value = [
            failed_pull_request,
            later_pull_request,
        ]
        mock_sleep = MagicMock()
        monkeypatch.setattr(stale_pr_ping.time, "sleep", mock_sleep)

        with pytest.raises(SystemExit):
            main()

        assert failed_pull_request.get_issue_comments.call_count == 3
        assert mock_sleep.call_args_list == [call(2), call(4)]
        later_pull_request.create_issue_comment.assert_called_once()
        later_pull_request.add_to_labels.assert_called_once_with(
            REQUESTED_INFO_LABEL
        )
        output = capsys.readouterr().out
        assert "Scanned 2 PRs, warned 1, closed 0, failed 1" in output
        assert "Warned: #42" in output
        assert "Failed: #41" in output
