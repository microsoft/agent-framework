# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the head/tail truncation helper and the reanchor quoter."""

from __future__ import annotations

from agent_framework_tools.shell._tool import _quote_posix, _quote_powershell
from agent_framework_tools.shell._truncate import truncate_head_tail, truncate_text_head_tail


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
