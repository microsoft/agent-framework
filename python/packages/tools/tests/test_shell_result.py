# Copyright (c) Microsoft. All rights reserved.

from agent_framework_tools.shell import ShellResult


def _make(
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
    truncated: bool = False,
    timed_out: bool = False,
) -> ShellResult:
    return ShellResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=1,
        truncated=truncated,
        timed_out=timed_out,
    )


def test_format_stdout_only() -> None:
    text = _make(stdout="hello").format_for_model()
    assert text == "hello\nexit_code: 0"


def test_format_stdout_truncated_appends_marker() -> None:
    text = _make(stdout="part", truncated=True).format_for_model()
    assert "[stdout truncated]" in text
    assert text.startswith("part")


def test_format_stderr_prefixed() -> None:
    text = _make(stderr="boom", exit_code=1).format_for_model()
    assert "stderr: boom" in text
    assert "exit_code: 1" in text


def test_format_timed_out_marker() -> None:
    text = _make(timed_out=True, exit_code=124).format_for_model()
    assert "[command timed out]" in text
    assert "exit_code: 124" in text


def test_format_empty_streams_still_reports_exit_code() -> None:
    text = _make().format_for_model()
    assert text == "exit_code: 0"


def test_format_combines_all_signals_in_order() -> None:
    text = _make(
        stdout="out",
        stderr="err",
        exit_code=2,
        truncated=True,
        timed_out=True,
    ).format_for_model()
    lines = text.split("\n")
    assert lines[0] == "out"
    assert lines[1] == "[stdout truncated]"
    assert lines[2] == "stderr: err"
    assert lines[3] == "[command timed out]"
    assert lines[4] == "exit_code: 2"
