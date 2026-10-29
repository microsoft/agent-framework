# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the persistent-shell sentinel exit-code parser.

A bug here would silently return -1 for every persistent-mode command's
exit code, masking real failures, so the edge cases are exercised
explicitly even though `_parse_rc` is a private helper.
"""

from __future__ import annotations

import pytest

from agent_framework_tools.shell._session import _CommandOutput, _parse_rc


@pytest.mark.parametrize("split", range(1, 21))
def test_completion_marker_survives_read_boundaries_with_tiny_allowance(split: int) -> None:
    sentinel = b"__AF_END_test_tag__"
    output = _CommandOutput(sentinel, max_stdout_bytes=1, max_stderr_bytes=8)
    data = b"prefix\r\n" + sentinel + b"_42\r\nignored"
    for offset in range(0, len(data), split):
        output.read_stdout(data[offset : offset + split])
        assert len(output._pending) <= len(sentinel) + 32
    assert output.exit_code == 42
    assert output.stdout.format() == ("\n[... truncated 5 bytes ...]\nx", True)


def test_completion_parser_bounds_output_before_and_after_marker() -> None:
    sentinel = b"__AF_END_test__"
    output = _CommandOutput(sentinel, max_stdout_bytes=16, max_stderr_bytes=8)
    for _ in range(1000):
        output.read_stdout(b"not-a-marker" * 100)
        assert len(output._pending) < len(sentinel)
        assert len(output.stdout._output._head) + len(output.stdout._output._tail) <= 16
    output.read_stdout(sentinel + b"_-7\n" + b"discard" * 1000)
    assert output.exit_code == -7
    assert not output._pending


def test_completion_parser_rejects_unbounded_exit_status() -> None:
    output = _CommandOutput(b"marker", max_stdout_bytes=1, max_stderr_bytes=8)
    with pytest.raises(RuntimeError, match="oversized exit status"):
        output.read_stdout(b"marker_" + b"1" * 1000)


def test_completion_parser_finishes_partial_exit_status() -> None:
    output = _CommandOutput(b"marker", max_stdout_bytes=8, max_stderr_bytes=1)
    output.read_stdout(b"hello\nmarker_12")
    output.finish_stdout()
    assert output.exit_code == 12
    assert output.stdout.format() == ("hello", False)


def test_partial_completion_marker_does_not_count_toward_output_overflow() -> None:
    sentinel = b"__AF_END_test_tag__"
    output = _CommandOutput(sentinel, max_stdout_bytes=1, max_stderr_bytes=8)
    for value in sentinel:
        output.read_stdout(bytes([value]))
        assert output.stdout_bytes == 0
    output.read_stdout(b"_0\n")
    assert output.exit_code == 0


def test_parse_rc_zero() -> None:
    assert _parse_rc(b"_0\n") == 0


def test_parse_rc_positive() -> None:
    assert _parse_rc(b"_127\n") == 127


def test_parse_rc_negative() -> None:
    assert _parse_rc(b"_-1\n") == -1


def test_parse_rc_crlf() -> None:
    assert _parse_rc(b"_42\r\n") == 42


def test_parse_rc_no_trailing_newline() -> None:
    assert _parse_rc(b"_5") == 5


def test_parse_rc_missing_underscore_returns_minus_one() -> None:
    assert _parse_rc(b"42\n") == -1


def test_parse_rc_empty_returns_minus_one() -> None:
    assert _parse_rc(b"") == -1


def test_parse_rc_only_underscore_returns_minus_one() -> None:
    assert _parse_rc(b"_\n") == -1


def test_parse_rc_non_digit_returns_minus_one() -> None:
    assert _parse_rc(b"_abc\n") == -1


def test_parse_rc_stops_at_first_non_digit() -> None:
    # Trailing garbage after the digits should not corrupt the parse.
    assert _parse_rc(b"_7 extra junk\n") == 7


def test_parse_rc_partial_digits_then_garbage() -> None:
    assert _parse_rc(b"_12x34\n") == 12
