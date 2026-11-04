# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the head/tail truncation helper and the reanchor quoter."""

from __future__ import annotations

import pytest

from agent_framework_tools.shell._tool import _quote_posix, _quote_powershell
from agent_framework_tools.shell._truncate import (
    _OutputBuffer,
    _TextOutputBuffer,
    truncate_head_tail,
    truncate_text_head_tail,
)


@pytest.mark.parametrize("cap", [1, 2, 5, 64])
@pytest.mark.parametrize("chunk_size", [1, 7, 1024])
def test_streaming_capture_matches_truncation_with_bounded_storage(cap: int, chunk_size: int) -> None:
    data = bytes(range(128)) * 32
    output = _OutputBuffer(cap)
    for offset in range(0, len(data), chunk_size):
        output.append(data[offset : offset + chunk_size])
        assert len(output._head) + len(output._tail) <= cap
    assert output.format() == truncate_head_tail(data, cap)


@pytest.mark.parametrize("cap", [1, 5, 64])
def test_text_capture_preserves_decoding_and_strips_unbounded_trailing_newlines(cap: int) -> None:
    data = b"head\n" + "caf\u00e9".encode() + b"\xff" + b"\r\n" * 100 + b"tail" + b"\r\n" * 100
    output = _TextOutputBuffer(cap, strip_newlines=True)
    for value in data:
        output.append(bytes([value]))
        for buffer in (output._output, output._pending_newlines):
            assert len(buffer._head) + len(buffer._tail) <= cap
    output.append(b"", final=True)
    expected = data.decode("utf-8", errors="replace").rstrip("\r\n")
    assert output.format() == truncate_text_head_tail(expected, cap)


def test_truncate_under_cap_returns_original() -> None:
    out, trunc = truncate_head_tail(b"hello", 100)
    assert out == "hello"
    assert trunc is False


def test_truncate_at_cap_returns_original() -> None:
    out, trunc = truncate_head_tail(b"abcde", 5)
    assert out == "abcde"
    assert trunc is False


def test_truncate_over_cap_marks_truncated_and_reports_bytes() -> None:
    data = b"A" * 10
    out, trunc = truncate_head_tail(data, 4)
    assert trunc is True
    assert "truncated 6 bytes" in out
    # head=2, tail=2 — total of 4 'A's plus the marker
    assert out.count("A") == 4


def test_truncate_odd_cap_keeps_extra_byte_in_tail() -> None:
    # cap=5, len=10 → head=2, tail=3, dropped=5.
    data = b"ABCDEFGHIJ"
    out, trunc = truncate_head_tail(data, 5)
    assert trunc is True
    assert out.startswith("AB\n[")
    assert out.endswith("]\nHIJ")


def test_truncate_text_uses_utf8_byte_budget() -> None:
    # Each smiley is 4 UTF-8 bytes. 10 smileys = 40 bytes; cap=20 → truncated.
    text = "😀" * 10
    out, trunc = truncate_text_head_tail(text, 20)
    assert trunc is True
    assert "truncated 20 bytes" in out


def test_truncate_zero_cap_raises() -> None:
    with pytest.raises(ValueError):
        truncate_head_tail(b"abc", 0)


def test_truncate_negative_cap_raises() -> None:
    with pytest.raises(ValueError):
        truncate_head_tail(b"abc", -1)


def test_quote_posix_blocks_dollar_expansion() -> None:
    quoted = _quote_posix("$(rm -rf /)")
    assert quoted == "'$(rm -rf /)'"


def test_quote_posix_escapes_embedded_single_quote() -> None:
    quoted = _quote_posix("it's fine")
    assert quoted == "'it'\\''s fine'"


def test_quote_powershell_blocks_dollar_expansion() -> None:
    quoted = _quote_powershell("$malicious")
    assert quoted == "'$malicious'"


def test_quote_powershell_doubles_embedded_single_quote() -> None:
    quoted = _quote_powershell("a'b")
    assert quoted == "'a''b'"
